import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
import random
from typing import Any

from core.tools import BaseTool


def _semantic_scholar_rate_limit_wait(attempt: int, has_api_key: bool):
    """Semantic Scholar 限流等待：无 API Key 时需要极长退避"""
    if has_api_key:
        base_sleep = 3 * (attempt + 1)
    else:
        # 无 API Key 时极其激进，需要 30s+ 退避
        base_sleep = max(30, 15 * (attempt + 1))
    jitter = random.uniform(0, 5)
    time.sleep(base_sleep + jitter)


class SemanticScholarSearchTool(BaseTool):
    name = "semantic_scholar_search"
    description = "用于在 Semantic Scholar 上搜索论文，返回标题、作者、年份、摘要和开放获取链接。"
    parameters = {
        "query": "搜索关键词，例如 'LLM Agent Memory'",
        "limit": "最大返回数，默认为5（可选）",
    }

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        if not query:
            raise ValueError("SemanticScholarSearchTool 缺少必要的参数: 'query'")

        try:
            limit = int(kwargs.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5

        base_url = os.getenv("SEMANTIC_SCHOLAR_API_BASE", "https://api.semanticscholar.org/graph/v1")
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        has_api_key = bool(api_key)

        fields = "paperId,title,authors,year,venue,abstract,url,openAccessPdf,externalIds,citationCount"
        encoded_query = urllib.parse.quote(query)
        url = f"{base_url}/paper/search?query={encoded_query}&limit={limit}&fields={urllib.parse.quote(fields)}"

        headers = {
            "User-Agent": "AcademicResearchAgent/1.0",
            "Accept": "application/json",
        }
        if api_key:
            headers["x-api-key"] = api_key

        max_retries = 5 if not has_api_key else 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries - 1:
                    _semantic_scholar_rate_limit_wait(attempt, has_api_key)
                    continue
                return f"Semantic Scholar 搜索请求失败: HTTP Error {exc.code}"
            except Exception as exc:
                return f"Semantic Scholar 搜索请求失败: {str(exc)}"

        items = payload.get("data", [])
        if not items:
            return f"Semantic Scholar 未找到关于 '{query}' 的论文，请尝试更换检索关键词。"

        results = []
        for item in items:
            authors = item.get("authors") or []
            author_names = ", ".join(author.get("name", "Unknown") for author in authors[:5]) or "Unknown"
            abstract = (item.get("abstract") or "").strip().replace("\n", " ")
            if len(abstract) > 600:
                abstract = abstract[:600] + "..."

            paper_id = item.get("paperId", "Unknown")
            title = (item.get("title") or "Unknown").strip().replace("\n", " ")
            year = item.get("year", "Unknown")
            venue = item.get("venue", "Unknown")
            citation_count = item.get("citationCount", "Unknown")
            url_text = item.get("url") or ""
            oa_pdf = (item.get("openAccessPdf") or {}).get("url", "")

            block = [
                f"PaperID: {paper_id}",
                f"Title: {title}",
                f"Authors: {author_names}",
                f"Year: {year}",
                f"Venue: {venue}",
                f"CitationCount: {citation_count}",
            ]
            if abstract:
                block.append(f"Abstract: {abstract}")
            if url_text:
                block.append(f"URL: {url_text}")
            if oa_pdf:
                block.append(f"OpenAccessPDF: {oa_pdf}")

            results.append("\n".join(block))

        return "\n---\n".join(results)


class SemanticScholarFetchTool(BaseTool):
    name = "semantic_scholar_fetch"
    description = "通过 Semantic Scholar 的 paperId 拉取论文详情、摘要和开放获取链接。"
    parameters = {
        "paper_id": "Semantic Scholar paperId，通常由 semantic_scholar_search 返回",
    }

    def execute(self, **kwargs) -> Any:
        paper_id = kwargs.get("paper_id")
        if not paper_id:
            raise ValueError("SemanticScholarFetchTool 缺少必要的参数: 'paper_id'")

        base_url = os.getenv("SEMANTIC_SCHOLAR_API_BASE", "https://api.semanticscholar.org/graph/v1")
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        has_api_key = bool(api_key)
        fields = "paperId,title,authors,year,venue,abstract,url,openAccessPdf,externalIds,citationCount"
        encoded_paper_id = urllib.parse.quote(paper_id, safe="")
        url = f"{base_url}/paper/{encoded_paper_id}?fields={urllib.parse.quote(fields)}"

        headers = {
            "User-Agent": "AcademicResearchAgent/1.0",
            "Accept": "application/json",
        }
        if api_key:
            headers["x-api-key"] = api_key

        max_retries = 5 if not has_api_key else 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries - 1:
                    _semantic_scholar_rate_limit_wait(attempt, has_api_key)
                    continue
                return f"Semantic Scholar 拉取详情失败: HTTP Error {exc.code}"
            except Exception as exc:
                return f"Semantic Scholar 拉取详情失败: {str(exc)}"

        authors = payload.get("authors") or []
        author_names = ", ".join(author.get("name", "Unknown") for author in authors[:10]) or "Unknown"
        abstract = (payload.get("abstract") or "No abstract available").strip().replace("\n", " ")
        if len(abstract) > 1200:
            abstract = abstract[:1200] + "..."

        title = (payload.get("title") or "Unknown").strip().replace("\n", " ")
        year = payload.get("year", "Unknown")
        venue = payload.get("venue", "Unknown")
        citation_count = payload.get("citationCount", "Unknown")
        url_text = payload.get("url") or ""
        oa_pdf = (payload.get("openAccessPdf") or {}).get("url", "")
        external_ids = payload.get("externalIds") or {}

        lines = [
            f"PaperID: {payload.get('paperId', paper_id)}",
            f"Title: {title}",
            f"Authors: {author_names}",
            f"Year: {year}",
            f"Venue: {venue}",
            f"CitationCount: {citation_count}",
            f"Abstract: {abstract}",
        ]
        if url_text:
            lines.append(f"URL: {url_text}")
        if oa_pdf:
            lines.append(f"OpenAccessPDF: {oa_pdf}")
        if external_ids:
            lines.append(f"ExternalIds: {json.dumps(external_ids, ensure_ascii=False)}")

        return "\n".join(lines)


