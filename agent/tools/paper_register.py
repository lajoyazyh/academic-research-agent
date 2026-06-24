"""
register_paper 工具 — 下载 + 收录一体化

Agent 审核摘要后判断值得收录 → 调用此工具一次性完成：
  1. 下载 PDF 到 session papers 目录
  2. 登记到 papers_list.json

解决之前"下载了论文但未收录"的问题。
"""

import os
import json
import re
import datetime
import urllib.request
import ssl
from typing import Any
from pathlib import Path

from core.tools import BaseTool


class PaperRegisterTool(BaseTool):
    """
    Agent 端使用的论文收录工具：下载 PDF 并登记到 session。
    由 Agent 根据 arxiv_search 返回的摘要自行判断是否值得收录。
    """
    name = "paper_register"
    description = (
        "收录一篇论文到当前研究项目：下载 PDF 并记录元数据。"
        "在确认论文相关且有价值后调用此工具。"
        "支持 arXiv ID（如 2308.11432）和 DOI（如 10.1177/xxx）。"
        "输入参数："
        "  - paper_id: arXiv ID 或 DOI"
        "  - title: 论文标题（从搜索结果中获取）"
        "  - authors: 作者（可选）"
        "  - abstract: 摘要文本（可选）"
    )
    parameters = {
        "paper_id": "论文的 arXiv ID（如 2308.11432）或 DOI（如 10.1177/xxx）。",
        "title": "论文标题。必填。",
        "authors": "作者列表，逗号分隔。可选。",
        "abstract": "摘要全文。可选。",
    }

    def __init__(self, session_id: str = "", papers_dir: str = "", provider_config: dict | None = None):
        self.session_id = session_id
        self.papers_dir = papers_dir
        self.provider_config = provider_config

    def _is_doi(self, paper_id: str) -> bool:
        """判断 paper_id 是否为 DOI 格式（支持纯 DOI 和 https://doi.org/ 前缀）"""
        return bool(re.match(r'(https?://doi\.org/)?10\.\d{4,}/', paper_id))

    def _doi_to_url(self, doi: str) -> str:
        """DOI 转 PDF 下载 URL（优先 Unpaywall，回退 Sci-Hub）"""
        doi_clean = doi.strip()
        if doi_clean.startswith("https://doi.org/"):
            doi_clean = doi_clean.replace("https://doi.org/", "")
        # 尝试通过 doi.org 解析
        return f"https://doi.org/{doi_clean}"

    def _try_download_pdf(self, clean_id: str, is_doi: bool = False) -> tuple[bool, str, str]:
        """尝试多种方式下载 PDF，返回 (成功, 消息, 文件路径)"""
        if not self.papers_dir:
            return False, "未配置 papers_dir", ""
        os.makedirs(self.papers_dir, exist_ok=True)

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AcademicAgent/1.0)"}

        safe_id = re.sub(r'[\\/:*?"<>|]', '_', clean_id)
        pdf_path = os.path.join(self.papers_dir, f"{safe_id}.pdf")

        if is_doi:
            doi_clean = clean_id.replace("https://doi.org/", "")
            urls_to_try = [
                ("Unpaywall", f"https://api.unpaywall.org/v2/{doi_clean}?email=academic-agent@example.com"),
            ]
        else:
            clean_arxiv = clean_id.split("v")[0] if "v" in clean_id else clean_id
            urls_to_try = [
                ("arXiv", f"https://arxiv.org/pdf/{clean_arxiv}.pdf"),
            ]

        last_error = ""
        for source, url in urls_to_try:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    content = resp.read()

                if source == "Unpaywall":
                    data = json.loads(content.decode('utf-8'))
                    best = data.get("best_oa_location") or {}
                    pdf_url = best.get("url_for_pdf") or best.get("url") or ""
                    if not pdf_url:
                        is_oa = data.get("is_oa", False)
                        last_error = "Unpaywall: not Open Access" if not is_oa else "Unpaywall: no PDF URL found"
                        continue
                    req2 = urllib.request.Request(pdf_url, headers=headers)
                    with urllib.request.urlopen(req2, context=ctx, timeout=30) as resp2:
                        content = resp2.read()

                if len(content) < 100:
                    last_error = f"{source}: response too small ({len(content)} bytes)"
                    continue
                if content[:4] == b'%PDF':
                    with open(pdf_path, "wb") as f:
                        f.write(content)
                    return True, f"✅ PDF 已下载 ({len(content) / 1024:.0f} KB, via {source})", pdf_path
                else:
                    last_error = f"{source}: not a PDF"
                    continue
            except Exception as e:
                last_error = f"{source}: {str(e)}"
                continue

        return False, f"❌ PDF 下载失败: {last_error}", ""

    def execute(self, **kwargs) -> Any:
        import re
        paper_id = str(kwargs.get("paper_id", "")).strip()
        title = str(kwargs.get("title", "")).strip()
        authors = str(kwargs.get("authors", "")).strip()
        abstract = str(kwargs.get("abstract", "")).strip()

        if not paper_id:
            return "❌ paper_register 失败：缺少 paper_id"
        if not title:
            title = paper_id

        is_doi = self._is_doi(paper_id)
        clean_id = paper_id.split("v")[0] if "v" in paper_id else paper_id

        # ━━━ 主题相关性审核 ━━━
        if abstract and self.session_id:
            try:
                from backend.session_manager import SessionManager
                sessions_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")
                mgr = SessionManager(sessions_root)
                session = mgr.load_session(self.session_id)
                topic = session.get("topic", "") if session else ""
                if topic:
                    from llms.client import LLMClient
                    llm = LLMClient(self.provider_config)
                    answer = llm.chat(
                        "你只回答 yes 或 no。",
                        f"研究主题：{topic}\n论文标题：{title[:150]}\n摘要前 300 字：{abstract[:300]}\n\n这篇论文与上述研究主题相关吗？",
                        []
                    ).strip().lower()
                    if answer.startswith("no"):
                        return f"❌ 审核未通过：摘要与当前研究主题「{topic}」不相关。请继续搜索与主题匹配的论文。"
            except Exception:
                pass

        # Step 1: 下载 PDF
        pdf_downloaded, pdf_msg, pdf_path = self._try_download_pdf(clean_id, is_doi)

        if not pdf_downloaded:
            # PDF 下载失败，但仍然登记元数据（至少摘要可用）
            if self.session_id and title:
                try:
                    safe_id = re.sub(r'[\\/:*?"<>|]', '_', clean_id)
                    from backend.session_manager import SessionManager
                    sessions_root = str(Path(self.papers_dir).parent.parent) if self.papers_dir else ""
                    if sessions_root:
                        mgr = SessionManager(sessions_root)
                        paper_entry = {
                            "paper_id": safe_id,
                            "title": title,
                            "authors": authors,
                            "source": "agent_search",
                            "source_type": "doi" if is_doi else "arxiv",
                            "status": "pending",
                            "abstract": abstract[:1500] if abstract else "",
                            "notes": "",
                            "has_notes": False,
                            "added_at": datetime.datetime.now().isoformat(),
                        }
                        mgr.add_paper(self.session_id, paper_entry)
                        return (
                            f"⚠️ 论文已登记（PDF 下载失败）: {title}\n"
                            f"   ID: {clean_id}\n"
                            f"   {pdf_msg}\n"
                            f"   元数据已保存，后续可手动上传 PDF。"
                        )
                except Exception as e:
                    pass

            return f"❌ 论文收录失败: {title} (ID: {clean_id})\n   原因: {pdf_msg}"

        # Step 2: 登记到 papers_list.json
        registered = False
        reg_msg = ""
        if self.session_id:
            try:
                safe_id = re.sub(r'[\\/:*?"<>|]', '_', clean_id)
                from backend.session_manager import SessionManager
                sessions_root = str(Path(self.papers_dir).parent.parent) if self.papers_dir else ""
                if sessions_root:
                    mgr = SessionManager(sessions_root)
                    paper_entry = {
                        "paper_id": safe_id,
                        "title": title,
                        "authors": authors,
                        "source": "agent_search",
                        "source_type": "doi" if is_doi else "arxiv",
                        "status": "pending",
                        "abstract": abstract[:1500] if abstract else "",
                        "notes": "",
                        "has_notes": False,
                        "added_at": datetime.datetime.now().isoformat(),
                    }
                    mgr.add_paper(self.session_id, paper_entry)
                    registered = True
                    reg_msg = "✅ 已登记到论文列表"
            except Exception as e:
                reg_msg = f"⚠️ 论文登记失败: {str(e)}"

        summary = f"✅ 论文收录成功: {title}\n   ID: {clean_id} ({'DOI' if is_doi else 'arXiv'})\n   {pdf_msg}"
        if reg_msg:
            summary += f"\n   {reg_msg}"
        if abstract:
            summary += f"\n   摘要前 200 字: {abstract[:200]}..."
        return summary

