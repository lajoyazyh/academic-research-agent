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
import difflib
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
import ssl
import xml.etree.ElementTree as ET
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
        "  - arxiv_id: 搜索结果中存在 arXiv ID 时必须传入，便于优先下载开放 PDF"
        "  - pdf_url: 数据源明确返回的 OpenAccessPDF/pdf_url（可选）"
    )
    parameters = {
        "paper_id": "论文的 arXiv ID（如 2308.11432）或 DOI（如 10.1177/xxx）。",
        "title": "论文标题。必填。",
        "authors": "作者列表，逗号分隔。可选。",
        "abstract": "摘要全文。必填；必须从搜索结果或详情工具中获取。",
        "arxiv_id": "可选的 arXiv ID；论文同时有 DOI 与 arXiv 版本时必须传入。",
        "pdf_url": "数据源明确给出的开放 PDF URL。可选，禁止臆造。",
    }

    def __init__(self, session_id: str = "", papers_dir: str = "", provider_config: dict | None = None,
                 sessions_root: str = "", session_manager=None):
        self.session_id = session_id
        self.papers_dir = papers_dir
        self.provider_config = provider_config
        self.sessions_root = sessions_root
        self.session_manager = session_manager
        self.registered_paper_ids: set[str] = set()

    def _session_manager(self):
        if self.session_manager is not None:
            return self.session_manager
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

    @staticmethod
    def _normalized_title(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    @staticmethod
    def _is_public_http_url(value: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return False
            if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
                return False
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
            return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
        except Exception:
            return False

    @staticmethod
    def _content_tokens(value: str) -> set[str]:
        stop = {
            "and", "the", "for", "are", "was", "were", "this", "that", "these", "those",
            "with", "from", "into", "using", "based", "study", "paper", "approach",
            "method", "methods", "analysis", "results", "towards", "through", "between",
        }
        tokens = set()
        for token in re.findall(r"[a-z][a-z0-9-]{2,}", (value or "").lower()):
            token = token.replace("-", "")
            for suffix in ("ing", "ed", "es", "s"):
                if token.endswith(suffix) and len(token) - len(suffix) >= 5:
                    token = token[:-len(suffix)]
                    break
            if token not in stop:
                tokens.add(token)
        return tokens

    def _passes_lexical_relevance(self, topic: str, title: str, abstract: str) -> bool:
        """Reject obvious one-word drift before spending another LLM request."""
        topic_tokens = self._content_tokens(topic)
        if len(topic_tokens) < 3:
            return True
        candidate_tokens = self._content_tokens(f"{title} {abstract}")
        overlap = topic_tokens & candidate_tokens
        normalized_topic = self._normalized_title(topic)
        normalized_title = self._normalized_title(title)
        if normalized_topic and (normalized_topic in normalized_title or normalized_title in normalized_topic):
            return True
        return len(overlap) >= 2

    def _semantic_scholar_sources(self, doi: str, title: str) -> list[tuple[str, str]]:
        """Resolve an OA URL or arXiv id without requiring a provider API key."""
        base = os.getenv("SEMANTIC_SCHOLAR_API_BASE", "https://api.semanticscholar.org/graph/v1")
        fields = urllib.parse.quote("title,openAccessPdf,externalIds")
        urls = []
        if doi:
            urls.append(f"{base}/paper/DOI:{urllib.parse.quote(doi, safe='')}?fields={fields}")
        if title:
            urls.append(
                f"{base}/paper/search?query={urllib.parse.quote(title)}&limit=3&fields={fields}"
            )
        headers = {"User-Agent": "AcademicResearchAgent/1.0", "Accept": "application/json"}
        for url in urls:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=12) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                continue
            items = payload.get("data", []) if isinstance(payload, dict) and "data" in payload else [payload]
            for item in items:
                if not isinstance(item, dict):
                    continue
                if title:
                    score = difflib.SequenceMatcher(
                        None,
                        self._normalized_title(title),
                        self._normalized_title(item.get("title", "")),
                    ).ratio()
                    if score < 0.82:
                        continue
                external_ids = item.get("externalIds") or {}
                arxiv_id = str(external_ids.get("ArXiv") or "").strip()
                if arxiv_id:
                    return [("Semantic Scholar → arXiv", f"https://arxiv.org/pdf/{arxiv_id}.pdf")]
                oa_url = str((item.get("openAccessPdf") or {}).get("url") or "").strip()
                if oa_url:
                    return [("Semantic Scholar OA", oa_url)]
        return []

    def _arxiv_title_sources(self, title: str) -> list[tuple[str, str]]:
        if not title:
            return []
        query = urllib.parse.quote(f'ti:"{title}"')
        url = f"https://export.arxiv.org/api/query?search_query={query}&start=0&max_results=5"
        headers = {"User-Agent": os.getenv("ARXIV_USER_AGENT", "AcademicResearchAgent/1.0")}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
                root = ET.fromstring(response.read())
        except Exception:
            return []
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        wanted = self._normalized_title(title)
        for entry in root.findall("atom:entry", namespace):
            entry_title = " ".join((entry.findtext("atom:title", "", namespace) or "").split())
            score = difflib.SequenceMatcher(None, wanted, self._normalized_title(entry_title)).ratio()
            if score < 0.82:
                continue
            entry_id = entry.findtext("atom:id", "", namespace).rstrip("/").split("/")[-1]
            arxiv_id = re.sub(r"v\d+$", "", entry_id)
            if arxiv_id:
                return [("arXiv title match", f"https://arxiv.org/pdf/{arxiv_id}.pdf")]
        return []

    def _unpaywall_sources(self, doi: str) -> list[tuple[str, str]]:
        contact = (
            os.getenv("UNPAYWALL_EMAIL", "").strip()
            or os.getenv("SCHOLAR_CONTACT_EMAIL", "").strip()
            or os.getenv("CROSSREF_MAILTO", "").strip()
        )
        if not doi or not contact:
            return []
        url = (
            f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='/')}"
            f"?email={urllib.parse.quote(contact)}"
        )
        try:
            with urllib.request.urlopen(url, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
            best = payload.get("best_oa_location") or {}
            pdf_url = str(best.get("url_for_pdf") or best.get("url") or "").strip()
            return [("Unpaywall", pdf_url)] if pdf_url else []
        except Exception:
            return []

    def _crossref_sources(self, doi: str) -> list[tuple[str, str]]:
        if not doi:
            return []
        url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
        headers = {"User-Agent": "AcademicResearchAgent/1.0", "Accept": "application/json"}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=12) as response:
                message = (json.loads(response.read().decode("utf-8")) or {}).get("message") or {}
        except Exception:
            return []
        sources = []
        # PVLDB exposes official open PDFs under a stable volume/page/author
        # convention even though the generic ACM DOI endpoint blocks bots.
        container = " ".join(message.get("container-title") or [])
        page = str(message.get("page") or "").split("-")[0].strip()
        volume = str(message.get("volume") or "").strip()
        authors = message.get("author") or []
        family = re.sub(r"[^a-z0-9]+", "", str((authors[0] if authors else {}).get("family") or "").lower())
        if doi.startswith("10.14778/") and "VLDB" in container.upper() and page and volume and family:
            sources.append(("PVLDB official", f"https://www.vldb.org/pvldb/vol{volume}/p{page}-{family}.pdf"))
        for link in message.get("link") or []:
            candidate = str(link.get("URL") or "").strip()
            content_type = str(link.get("content-type") or "").lower()
            if candidate and ("pdf" in content_type or ".pdf" in candidate.lower() or "doi/pdf" in candidate.lower()):
                sources.append(("Crossref full text", candidate))
        return sources

    def _try_download_pdf(
        self,
        clean_id: str,
        is_doi: bool = False,
        *,
        title: str = "",
        arxiv_id: str = "",
        pdf_url: str = "",
        destination_id: str = "",
    ) -> tuple[bool, str, str]:
        """尝试多种方式下载 PDF，返回 (成功, 消息, 文件路径)"""
        if not self.papers_dir:
            return False, "未配置 papers_dir", ""
        os.makedirs(self.papers_dir, exist_ok=True)

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AcademicAgent/1.0)"}

        safe_id = re.sub(r'[\\/:*?"<>|]', '_', destination_id or clean_id)
        pdf_path = os.path.join(self.papers_dir, f"{safe_id}.pdf")

        urls_to_try: list[tuple[str, str]] = []
        if pdf_url:
            urls_to_try.append(("数据源开放全文", pdf_url))
        clean_arxiv = re.sub(r"v\d+$", "", arxiv_id.strip()) if arxiv_id else ""
        if clean_arxiv:
            urls_to_try.append(("arXiv", f"https://arxiv.org/pdf/{clean_arxiv}.pdf"))
        if is_doi:
            doi_clean = clean_id.replace("https://doi.org/", "")
            urls_to_try.extend(self._arxiv_title_sources(title))
            urls_to_try.extend(self._semantic_scholar_sources(doi_clean, title))
            urls_to_try.extend(self._unpaywall_sources(doi_clean))
            urls_to_try.extend(self._crossref_sources(doi_clean))
        else:
            clean_arxiv = re.sub(r"v\d+$", "", clean_id)
            urls_to_try.append(("arXiv", f"https://arxiv.org/pdf/{clean_arxiv}.pdf"))

        seen_urls = set()
        errors = []
        for source, url in urls_to_try:
            if not url or url in seen_urls or not self._is_public_http_url(url):
                if url:
                    errors.append(f"{source}: blocked non-public URL")
                continue
            seen_urls.add(url)
            try:
                request_headers = {**headers, "Accept": "application/pdf"}
                req = urllib.request.Request(url, headers=request_headers)
                with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                    content = resp.read(50 * 1024 * 1024 + 1)
                if len(content) > 50 * 1024 * 1024:
                    errors.append(f"{source}: file exceeds 50 MB")
                    continue
                if len(content) < 100:
                    errors.append(f"{source}: response too small ({len(content)} bytes)")
                    continue
                if content[:4] == b'%PDF':
                    with open(pdf_path, "wb") as f:
                        f.write(content)
                    return True, f"✅ PDF 已下载 ({len(content) / 1024:.0f} KB, via {source})", pdf_path
                else:
                    errors.append(f"{source}: returned {resp.headers.get('Content-Type', 'non-PDF content')}")
                    continue
            except Exception as e:
                errors.append(f"{source}: {str(e)}")
                continue

        if not urls_to_try:
            errors.append("未找到开放全文地址；该论文可能不是开放获取")
        return False, f"❌ PDF 下载失败: {'; '.join(errors[-4:])}", ""

    def _save_delivery_status(self, mgr, paper: dict, downloaded: bool, message: str, path: str, **ids) -> None:
        papers = mgr.get_papers(self.session_id)
        for current in papers:
            if current.get("paper_id") == paper.get("paper_id"):
                current["pdf_status"] = "available" if downloaded else "unavailable"
                current["pdf_error"] = "" if downloaded else message.replace("❌ PDF 下载失败: ", "")
                if path:
                    current["pdf_filename"] = os.path.basename(path)
                for key, value in ids.items():
                    if value:
                        current[key] = value
                break
        mgr.save_papers_list(self.session_id, papers)

    def retry_pdf(self, paper: dict) -> tuple[bool, str, str]:
        """Retry PDF delivery for a previously persisted metadata-only paper."""
        mgr = self._session_manager()
        paper_id = str(paper.get("paper_id") or "").strip()
        doi = str(paper.get("doi") or "").strip()
        arxiv_id = str(paper.get("arxiv_id") or "").strip()
        if not doi and re.match(r"^10\.\d{4,9}_", paper_id):
            doi = paper_id.replace("_", "/", 1)
        source_id = doi or arxiv_id or paper_id
        is_doi = bool(doi) or self._is_doi(source_id)
        downloaded, message, path = self._try_download_pdf(
            source_id,
            is_doi,
            title=str(paper.get("title") or ""),
            arxiv_id=arxiv_id,
            pdf_url=str(paper.get("source_url") or ""),
            destination_id=paper_id,
        )
        self._save_delivery_status(
            mgr,
            paper,
            downloaded,
            message,
            path,
            doi=doi,
            arxiv_id=arxiv_id,
            source_url=str(paper.get("source_url") or ""),
        )
        return downloaded, message, path

    def execute(self, **kwargs) -> Any:
        import re
        paper_id = str(kwargs.get("paper_id", "")).strip()
        title = str(kwargs.get("title", "")).strip()
        authors = str(kwargs.get("authors", "")).strip()
        abstract = str(kwargs.get("abstract", "")).strip()
        arxiv_id = re.sub(r"v\d+$", "", str(kwargs.get("arxiv_id", "")).strip())
        pdf_url = str(kwargs.get("pdf_url", "")).strip()

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
            existing_path = os.path.join(self.papers_dir, f"{duplicate.get('paper_id')}.pdf")
            if os.path.exists(existing_path):
                return (
                    "ℹ️ 论文已存在且 PDF 可用，未新增："
                    f"{duplicate.get('title') or title} (ID: {duplicate.get('paper_id') or clean_id})"
                )
            downloaded, pdf_msg, pdf_path = self._try_download_pdf(
                clean_id,
                is_doi,
                title=title,
                arxiv_id=arxiv_id,
                pdf_url=pdf_url,
                destination_id=str(duplicate.get("paper_id") or clean_id),
            )
            self._save_delivery_status(
                mgr,
                duplicate,
                downloaded,
                pdf_msg,
                pdf_path,
                doi=clean_id if is_doi else "",
                arxiv_id=arxiv_id or (clean_id if not is_doi else ""),
                source_url=pdf_url,
            )
            return (
                "ℹ️ 论文已存在，未新增；已尝试补全 PDF："
                f"{duplicate.get('title') or title}\n   {pdf_msg}"
            )
        if not abstract:
            return "❌ paper_register 失败：缺少 abstract。请先用搜索或详情工具获取摘要，再判断相关性并收录。"

        # ━━━ 主题相关性审核 ━━━
        topic = session.get("topic", "")
        if topic:
            if not self._passes_lexical_relevance(topic, title, abstract):
                return (
                    f"❌ 审核未通过：论文与研究主题「{topic}」只有单一宽泛词重合，"
                    "不足以视为直接相关。请回到上一批结果选择更贴近主题的候选。"
                )
            try:
                from llms.client import LLMClient
                llm = LLMClient(self.provider_config)
                if llm.language == "en":
                    relevance_system = "Judge topical relevance conservatively. Answer only yes or no."
                    relevance_prompt = (
                        f"Research topic: {topic}\nPaper title: {title[:150]}\n"
                        f"First 500 characters of the abstract: {abstract[:500]}\n\n"
                        "Is this paper directly relevant to the research topic?"
                    )
                else:
                    relevance_system = "你只回答 yes 或 no。"
                    relevance_prompt = f"研究主题：{topic}\n论文标题：{title[:150]}\n摘要前 500 字：{abstract[:500]}\n\n这篇论文与上述研究主题直接相关吗？"
                answer = llm.chat(relevance_system, relevance_prompt, []).strip().lower()
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
            "doi": clean_id if is_doi else "",
            "arxiv_id": arxiv_id or (clean_id if not is_doi else ""),
            "source_url": pdf_url,
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
        pdf_downloaded, pdf_msg, pdf_path = self._try_download_pdf(
            clean_id,
            is_doi,
            title=title,
            arxiv_id=arxiv_id,
            pdf_url=pdf_url,
            destination_id=str(registered_paper.get("paper_id") or safe_id),
        )
        self._save_delivery_status(
            mgr,
            registered_paper,
            pdf_downloaded,
            pdf_msg,
            pdf_path,
            doi=clean_id if is_doi else "",
            arxiv_id=arxiv_id or (clean_id if not is_doi else ""),
            source_url=pdf_url,
        )
        delivery = pdf_msg if pdf_downloaded else f"{pdf_msg}\n   元数据已保存，后续可手动上传 PDF。"
        summary = f"✅ 论文新增成功: {title}\n   ID: {clean_id} ({'DOI' if is_doi else 'arXiv'})\n   ✅ 已登记到论文列表\n   {delivery}"
        if abstract:
            summary += f"\n   摘要前 200 字: {abstract[:200]}..."
        return summary

