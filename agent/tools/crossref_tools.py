import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error
import time
from typing import Any

from core.tools import BaseTool


def _safe_join_authors(authors: list[dict]) -> str:
    if not authors:
        return "Unknown"
    names = []
    for author in authors[:8]:
        given = author.get("given", "").strip()
        family = author.get("family", "").strip()
        full = (given + " " + family).strip()
        if full:
            names.append(full)
    return ", ".join(names) if names else "Unknown"


def _extract_published_date(item: dict) -> str:
    for key in ("published-print", "published-online", "issued"):
        date_parts = (item.get(key) or {}).get("date-parts")
        if date_parts and date_parts[0]:
            return "-".join(str(part) for part in date_parts[0])
    return "Unknown"


def _looks_like_arxiv_id(query: str) -> bool:
    value = (query or "").strip().lower()
    if not value:
        return False
    if value.startswith("arxiv:"):
        value = value.split(":", 1)[1].strip()

    old_style = r"^[a-z\-]+(?:\.[a-z\-]+)?\/\d{7}(?:v\d+)?$"
    new_style = r"^\d{4}\.\d{4,5}(?:v\d+)?$"
    return bool(re.match(old_style, value) or re.match(new_style, value))


def _tokenize_for_relevance(text: str) -> set[str]:
    lowered = (text or "").lower()
    english_tokens = {tok for tok in re.findall(r"[a-z][a-z0-9\-]{2,}", lowered)}
    chinese_tokens = {tok for tok in re.findall(r"[\u4e00-\u9fff]{2,}", lowered)}
    return english_tokens | chinese_tokens


def _relevance_score(query: str, title: str) -> float:
    query_tokens = _tokenize_for_relevance(query)
    if not query_tokens:
        return 1.0
    title_tokens = _tokenize_for_relevance(title)
    if not title_tokens:
        return 0.0
    overlap = query_tokens & title_tokens
    return len(overlap) / len(query_tokens)


class CrossrefSearchTool(BaseTool):
    name = "crossref_search"
    description = "在 Crossref 中按关键词检索文献元数据，返回 DOI、题目、作者、刊物和发表时间。"
    parameters = {
        "query": "检索关键词，例如 'LLM Agent Memory'",
        "rows": "最大返回数量，默认 5（可选）",
    }

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        if not query:
            raise ValueError("CrossrefSearchTool 缺少必要参数: 'query'")

        if _looks_like_arxiv_id(str(query)):
            return (
                f"CrossrefSearchTool 检测到 query='{query}' 更像 arXiv ID，"
                "不建议直接用于 Crossref 关键词检索。"
                "请改用论文标题/作者作为 query，或在已知 DOI 时调用 crossref_fetch_doi。"
            )

        try:
            rows = max(1, int(kwargs.get("rows", 5)))
        except (TypeError, ValueError):
            rows = 5

        base_url = os.getenv("CROSSREF_API_BASE", "https://api.crossref.org")
        mailto = os.getenv("CROSSREF_MAILTO", "")
        encoded_query = urllib.parse.quote(query)

        url = (
            f"{base_url}/works?query.bibliographic={encoded_query}&rows={rows}"
            "&select=DOI,title,author,container-title,published-print,published-online,type,publisher,URL"
        )
        if mailto:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}mailto={urllib.parse.quote(mailto)}"

        headers = {
            "User-Agent": "AcademicResearchAgent/1.0",
            "Accept": "application/json",
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return f"Crossref 检索请求失败: HTTP Error {exc.code}"
            except Exception as exc:
                return f"Crossref 检索请求失败: {str(exc)}"

        items = ((payload.get("message") or {}).get("items")) or []
        if not items:
            return f"Crossref 未找到关于 '{query}' 的元数据结果。"

        results = []
        skipped_low_relevance = 0
        for item in items:
            doi = item.get("DOI", "Unknown")
            title_list = item.get("title") or []
            title = title_list[0].strip() if title_list else "Unknown"
            score = _relevance_score(str(query), title)
            if score < 0.2:
                skipped_low_relevance += 1
                continue

            authors = _safe_join_authors(item.get("author") or [])
            journal = (item.get("container-title") or ["Unknown"])[0]
            published = _extract_published_date(item)
            publisher = item.get("publisher", "Unknown")
            entry_url = item.get("URL", "")

            block = [
                f"DOI: {doi}",
                f"Title: {title}",
                f"Authors: {authors}",
                f"Journal: {journal}",
                f"Published: {published}",
                f"Publisher: {publisher}",
            ]
            if entry_url:
                block.append(f"URL: {entry_url}")
            results.append("\n".join(block))

        if not results:
            return (
                f"Crossref 返回了结果，但与 query='{query}' 的关键词重合度偏低。"
                f"已跳过 {skipped_low_relevance} 条低相关记录，请改用更具体的论文标题或作者关键词重试。"
            )

        return "\n---\n".join(results)


class CrossrefFetchByDoiTool(BaseTool):
    name = "crossref_fetch_doi"
    description = "按 DOI 精确拉取 Crossref 文献元数据，用于补全引用信息。"
    parameters = {
        "doi": "DOI 字符串，例如 '10.48550/arXiv.2308.11432'",
    }

    def execute(self, **kwargs) -> Any:
        doi = kwargs.get("doi")
        if not doi:
            raise ValueError("CrossrefFetchByDoiTool 缺少必要参数: 'doi'")

        base_url = os.getenv("CROSSREF_API_BASE", "https://api.crossref.org")
        mailto = os.getenv("CROSSREF_MAILTO", "")
        encoded_doi = urllib.parse.quote(doi, safe="")
        url = f"{base_url}/works/{encoded_doi}"
        if mailto:
            url = f"{url}?mailto={urllib.parse.quote(mailto)}"

        headers = {
            "User-Agent": "AcademicResearchAgent/1.0",
            "Accept": "application/json",
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return f"Crossref 拉取请求失败: HTTP Error {exc.code}"
            except Exception as exc:
                return f"Crossref 拉取请求失败: {str(exc)}"

        item = (payload.get("message") or {})
        if not item:
            return f"Crossref 未找到 DOI '{doi}' 的元数据。"

        title = ((item.get("title") or ["Unknown"])[0]).strip()
        authors = _safe_join_authors(item.get("author") or [])
        journal = (item.get("container-title") or ["Unknown"])[0]
        published = _extract_published_date(item)
        publisher = item.get("publisher", "Unknown")
        entry_url = item.get("URL", "")
        type_name = item.get("type", "Unknown")

        lines = [
            f"DOI: {item.get('DOI', doi)}",
            f"Title: {title}",
            f"Authors: {authors}",
            f"Journal: {journal}",
            f"Published: {published}",
            f"Publisher: {publisher}",
            f"Type: {type_name}",
        ]
        if entry_url:
            lines.append(f"URL: {entry_url}")

        return "\n".join(lines)


