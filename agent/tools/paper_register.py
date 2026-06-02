"""
register_paper 工具 — 迭代三：下载 + 收录一体化

Agent 审核摘要后判断值得收录 → 调用此工具一次性完成：
  1. 下载 PDF 到 session papers 目录
  2. 登记到 papers_list.json

解决之前"下载了论文但未收录"的问题。
"""

import os
import json
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
        "输入参数："
        "  - paper_id: arXiv ID（如 2308.11432）"
        "  - title: 论文标题（从搜索结果中获取）"
        "  - authors: 作者（可选，从搜索结果中获取）"
        "  - abstract: 摘要文本（可选，从搜索结果中获取）"
    )
    parameters = {
        "paper_id": "论文的 arXiv ID。必填。",
        "title": "论文标题。必填。",
        "authors": "作者列表，逗号分隔。可选。",
        "abstract": "摘要全文。可选。",
    }

    def __init__(self, session_id: str = "", papers_dir: str = ""):
        """
        Args:
            session_id: 当前 Session ID（用于更新 papers_list.json）
            papers_dir: PDF 下载目录
        """
        self.session_id = session_id
        self.papers_dir = papers_dir

    def execute(self, **kwargs) -> Any:
        paper_id = str(kwargs.get("paper_id", "")).strip()
        title = str(kwargs.get("title", "")).strip()
        authors = str(kwargs.get("authors", "")).strip()
        abstract = str(kwargs.get("abstract", "")).strip()

        if not paper_id:
            return "❌ paper_register 失败：缺少 paper_id"
        if not title:
            title = paper_id  # 兜底

        # Step 1: 下载 PDF
        clean_id = paper_id.split("v")[0] if "v" in paper_id else paper_id
        pdf_downloaded = False
        pdf_msg = ""

        if self.papers_dir:
            os.makedirs(self.papers_dir, exist_ok=True)
            pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(
                    pdf_url,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, context=ctx) as resp:
                    pdf_bytes = resp.read()
                pdf_path = os.path.join(self.papers_dir, f"{clean_id}.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)
                pdf_downloaded = True
                pdf_msg = f"✅ PDF 已下载 ({len(pdf_bytes) / 1024:.0f} KB)"
            except Exception as e:
                pdf_msg = f"⚠️ PDF 下载失败: {str(e)}"

        # Step 2: 登记到 papers_list.json
        registered = False
        reg_msg = ""

        if self.session_id:
            try:
                from backend.session_manager import SessionManager
                sessions_root = Path(self.papers_dir).parent.parent if self.papers_dir else ""
                if sessions_root:
                    mgr = SessionManager(str(sessions_root))
                    paper_entry = {
                        "paper_id": clean_id,
                        "title": title,
                        "authors": authors,
                        "source": "agent_search",
                        "source_type": "arxiv",
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

        summary = f"📄 论文收录: {title} (ID: {clean_id})\n"
        summary += f"   {pdf_msg}\n" if pdf_msg else ""
        summary += f"   {reg_msg}" if reg_msg else ""
        summary += f"\n   摘要前 200 字: {abstract[:200]}..." if abstract else ""
        return summary
