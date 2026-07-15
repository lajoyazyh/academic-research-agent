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
        "  - abstract: 摘要全文（必填，用于主题相关性审核）"
    )
    parameters = {
        "paper_id": "论文的 arXiv ID（如 2308.11432）或 DOI（如 10.1177/xxx）。",
        "title": "论文标题。必填。",
        "authors": "作者列表，逗号分隔。可选。",
        "abstract": "摘要全文。必填；必须从搜索结果或详情工具中获取。",
    }

    def __init__(self, session_id: str = "", papers_dir: str = "", provider_config: dict | None = None,
                 sessions_root: str = ""):
        self.session_id = session_id
        self.papers_dir = papers_dir
        self.provider_config = provider_config
        self.sessions_root = sessions_root
        self.registered_paper_ids: set[str] = set()

    def _session_manager(self):
        from backend.session_manager import SessionManager
        root = self.sessions_root or (str(Path(self.papers_dir).parent.parent) if self.papers_dir else "")
        return SessionManager(root) if root else None

    def _is_doi(self, paper_id: str) -> bool:
        """判断 paper_id 是否为 DOI 格式（支持纯 DOI 和 https://doi.org/ 前缀）"""
        return bool(re.match(r'(https?://doi\.org/)?10\.\d{4,}/', paper_id))

    def get_registered_count(self) -> int:
        """Return the number of papers durably added by this tool instance."""
        return len(self.registered_paper_ids)

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
            return "❌ paper_register 失败：缺少 title"
        if not self.session_id:
            return "❌ 论文登记失败：未绑定研究项目 Session，不能把下载文件视为已收录论文。"

        is_doi = self._is_doi(paper_id)
        clean_id = paper_id.replace("https://doi.org/", "") if is_doi else re.sub(r"v\d+$", "", paper_id)

        # Validate the durable destination before downloading anything.  A PDF
        # file is not a collected paper until its metadata exists in Session.
        try:
            mgr = self._session_manager()
            session = mgr.load_session(self.session_id) if mgr else None
        except Exception as exc:
            return f"❌ 论文登记失败：无法访问研究项目 Session：{exc}"
        if not session:
            return f"❌ 论文登记失败：Session {self.session_id} 不存在，已停止下载。"

        # Check canonical identifiers before downloading.  The same work may be
        # returned as an arXiv id, DOI or provider-specific URL on later runs.
        duplicate = mgr.find_duplicate_paper(
            self.session_id,
            {"paper_id": clean_id, "title": title, "doi": clean_id if is_doi else ""},
        )
        if duplicate:
            return (
                "ℹ️ 论文已存在，未新增："
                f"{duplicate.get('title') or title} (ID: {duplicate.get('paper_id') or clean_id})"
            )
        if not abstract:
            return "❌ paper_register 失败：缺少 abstract。请先用搜索或详情工具获取摘要，再判断相关性并收录。"

        # ━━━ 主题相关性审核 ━━━
        topic = session.get("topic", "")
        if topic:
            try:
                from llms.client import LLMClient
                llm = LLMClient(self.provider_config)
                answer = llm.chat(
                    "你只回答 yes 或 no。",
                    f"研究主题：{topic}\n论文标题：{title[:150]}\n摘要前 500 字：{abstract[:500]}\n\n这篇论文与上述研究主题直接相关吗？",
                    [],
                ).strip().lower()
            except Exception as exc:
                return f"❌ 相关性审核失败：{exc}。本轮未登记该论文，请重试或选择其他论文。"
            if not answer.startswith(("yes", "是")):
                return f"❌ 审核未通过：摘要与当前研究主题「{topic}」不直接相关。请继续搜索主题匹配的论文。"

        # Persist and verify metadata first.  Only this transition is allowed to
        # produce the success marker consumed by the Agent and UI.
        safe_id = re.sub(r'[\\/:*?"<>|]', '_', clean_id)
        paper_entry = {
            "paper_id": safe_id,
            "title": title,
            "authors": authors,
            "source": "agent_search",
            "source_type": "doi" if is_doi else "arxiv",
            "status": "accepted",
            "abstract": abstract[:1500],
            "notes": "",
            "has_notes": False,
            "added_at": datetime.datetime.now().isoformat(),
        }
        try:
            mgr.add_paper(self.session_id, paper_entry)
            registered_paper = mgr.find_duplicate_paper(self.session_id, paper_entry)
        except Exception as exc:
            return f"❌ 论文登记失败：{title} (ID: {clean_id})\n   原因: {exc}"
        if not registered_paper:
            return f"❌ 论文登记失败：{title} (ID: {clean_id})\n   原因: 写入后无法从 Session 读取该论文"

        self.registered_paper_ids.add(str(registered_paper.get("paper_id") or safe_id))
        pdf_downloaded, pdf_msg, _pdf_path = self._try_download_pdf(clean_id, is_doi)
        delivery = pdf_msg if pdf_downloaded else f"{pdf_msg}\n   元数据已保存，后续可手动上传 PDF。"
        summary = f"✅ 论文新增成功: {title}\n   ID: {clean_id} ({'DOI' if is_doi else 'arXiv'})\n   ✅ 已登记到论文列表\n   {delivery}"
        if abstract:
            summary += f"\n   摘要前 200 字: {abstract[:200]}..."
        return summary

