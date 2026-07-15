import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import os
import re
import time
import random
from typing import Any

from core.tools import BaseTool

# ━━━ 全局 arXiv API 限流器（所有 arXiv 工具共享）━━━
_ARXIV_LAST_CALL_TS = 0.0
_ARXIV_MIN_INTERVAL_SEC = float(os.getenv("ARXIV_MIN_INTERVAL_SEC", "5.0"))


def _arxiv_rate_limit_wait():
    """确保任意两次 arXiv API 调用之间至少有 _ARXIV_MIN_INTERVAL_SEC 秒间隔"""
    global _ARXIV_LAST_CALL_TS
    elapsed = time.time() - _ARXIV_LAST_CALL_TS
    if elapsed < _ARXIV_MIN_INTERVAL_SEC:
        wait = _ARXIV_MIN_INTERVAL_SEC - elapsed + random.uniform(0, 1)
        time.sleep(wait)
    _ARXIV_LAST_CALL_TS = time.time()


def _deduplicate_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _build_query_variants(query: str) -> list[str]:
    normalized = re.sub(r"[（）()\[\]{}<>\"'“”‘’、,，;；:：/\\|]+", " ", query)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    english_terms = re.findall(r"[A-Za-z][A-Za-z0-9\-\+\.]*", normalized)
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)

    variants = [query]
    if normalized and normalized != query:
        variants.append(normalized)
    if english_terms:
        variants.append(" ".join(english_terms))
        if len(english_terms) >= 2:
            for size in range(min(len(english_terms), 4), 1, -1):
                variants.append(" ".join(english_terms[:size]))
                variants.append(" ".join(english_terms[-size:]))
    if chinese_terms:
        variants.append(" ".join(chinese_terms))

    return _deduplicate_preserve_order(variants)


def _fetch_arxiv_entries(query: str, max_results: int, base_url: str, user_agent: str,
                         start: int = 0) -> tuple[list[ET.Element], str]:
    encoded_query = urllib.parse.quote(query)
    url = f"{base_url}?search_query=all:{encoded_query}&start={max(0, start)}&max_results={max_results}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})

    _arxiv_rate_limit_wait()
    with urllib.request.urlopen(req) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('atom:entry', ns)
    return entries, query

class ArxivSearchTool(BaseTool):
    name = "arxiv_search"
    description = "用于在 arXiv 上搜索学术论文，返回论文的 ID、标题和发布时间。当找不到时会提醒更换搜索词。"
    parameters = {
        "query": "搜索关键词，例如 'LLM Agent Evaluation'",
        "max_results": "最大返回数，默认为5（可选）",
        "start": "结果起始偏移量；增量检索时可设为 5、10 等（可选）",
    }

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        if not query:
            raise ValueError("ArxivSearchTool 缺少必要的参数: 'query'")
        
        max_results = kwargs.get("max_results", 5)
        try:
            start = max(0, int(kwargs.get("start", 0)))
        except (TypeError, ValueError):
            start = 0
        base_url = os.getenv("ARXIV_API_BASE", "http://export.arxiv.org/api/query")
        user_agent = os.getenv("ARXIV_USER_AGENT", "AcademicResearchAgent/1.0")
        try:
            retry_limit = max(1, int(os.getenv("ARXIV_SEARCH_RETRY_LIMIT", "3")))
        except ValueError:
            retry_limit = 3

        query_variants = _build_query_variants(query)[:retry_limit]
        
        try:
            last_candidate = query
            last_error = ""
            for candidate in query_variants:
                last_candidate = candidate
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        _arxiv_rate_limit_wait()
                        if start:
                            entries, _ = _fetch_arxiv_entries(candidate, max_results, base_url, user_agent, start)
                        else:
                            entries, _ = _fetch_arxiv_entries(candidate, max_results, base_url, user_agent)
                        last_error = ""
                        break
                    except urllib.error.HTTPError as cand_http_err:
                        last_error = f"HTTP Error {cand_http_err.code}: {cand_http_err.reason}"
                        if cand_http_err.code == 429 and attempt < max_retries - 1:
                            time.sleep(5 * (attempt + 1))
                            continue
                        break
                    except Exception as candidate_error:
                        last_error = str(candidate_error)
                        break
                
                if last_error:
                    continue  # If fetch failed after retries, try next variant

                if entries:
                    results = []
                    for entry in entries:
                        atom_ns = {'atom': 'http://www.w3.org/2005/Atom'}
                        id_element = entry.find('atom:id', atom_ns)
                        title_element = entry.find('atom:title', atom_ns)
                        published_element = entry.find('atom:published', atom_ns)
                        summary_element = entry.find('atom:summary', atom_ns)
                        
                        # 提取所有作者
                        authors = []
                        for author in entry.findall('atom:author', atom_ns):
                            name_el = author.find('atom:name', atom_ns)
                            if name_el is not None:
                                authors.append(name_el.text.strip())

                        # 提取纯净 ID
                        paper_id = id_element.text.split('/')[-1] if id_element is not None else "Unknown"
                        title = title_element.text.strip().replace('\n', ' ') if title_element is not None else "Unknown"
                        published = published_element.text if published_element is not None else "Unknown"
                        summary = summary_element.text.strip().replace('\n', ' ') if summary_element is not None else "No abstract"
                        authors_str = ", ".join(authors) if authors else "Unknown"

                        # ⚠️ 限制摘要长度防止 token 爆炸
                        if len(summary) > 800:
                            summary = summary[:800] + "..."

                        results.append(
                            f"ID: {paper_id}\n"
                            f"Title: {title}\n"
                            f"Authors: {authors_str}\n"
                            f"Published: {published}\n"
                            f"Summary: {summary}"
                        )

                    if candidate != query:
                        header = f"原始关键词 '{query}' 未直接命中，已自动切换为 '{candidate}' 进行检索。"
                        return header + "\n" + "\n---\n".join(results)

                    return "\n---\n".join(results)

            if last_error:
                return f"Arxiv 搜索请求失败: {last_error}"
            return f"未找到关于 '{query}' 的论文，已尝试自动放宽为 '{last_candidate}'，请进一步更换检索关键词。"
            
        except Exception as e:
            return f"Arxiv 搜索请求失败: {str(e)}"


class ArxivFetchTool(BaseTool):
    name = "arxiv_fetch"
    description = "通过 arXiv 论文的 ID 精确获取该学术论文的详细标题、作者和完整摘要(Summary)。"
    parameters = {
        "paper_id": "论文的纯净 arXiv ID，例如 '2308.11432'"
    }

    def execute(self, **kwargs) -> Any:
        paper_id = kwargs.get("paper_id")
        if not paper_id:
            raise ValueError("ArxivFetchTool 缺少必要的参数: 'paper_id'")
        
        # 去掉版本后缀（如 v3），避免部分 ID 被 arXiv 限流更严格地对待
        clean_id = re.sub(r'v\d+$', '', str(paper_id).strip())
            
        base_url = os.getenv("ARXIV_API_BASE", "http://export.arxiv.org/api/query")
        user_agent = os.getenv("ARXIV_USER_AGENT", "AcademicResearchAgent/1.0")
        url = f"{base_url}?id_list={clean_id}"
        
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent})
            max_retries = 4
            xml_data = None
            for attempt in range(max_retries):
                try:
                    _arxiv_rate_limit_wait()
                    with urllib.request.urlopen(req) as response:
                        xml_data = response.read()
                    break
                except urllib.error.HTTPError as cand_http_err:
                    if cand_http_err.code == 429 and attempt < max_retries - 1:
                        # arXiv id_list 端点非常敏感，需要更长的退避时间
                        time.sleep(10 * (attempt + 1) + random.uniform(0, 3))
                        continue
                    raise cand_http_err
                    
            root = ET.fromstring(xml_data)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)
            
            if not entries:
                return f"未能在 arXiv 上找到 ID 为 '{paper_id}' 的这篇论文摘要。"
                
            entry = entries[0]
            title_element = entry.find('atom:title', ns)
            summary_element = entry.find('atom:summary', ns)
            
            authors = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]
            
            title = title_element.text.strip().replace('\n', ' ') if title_element is not None else "Unknown"
            summary = summary_element.text.strip().replace('\n', ' ') if summary_element is not None else "No summary available"
            authors_str = ", ".join(authors) if authors else "Unknown"
            
            return f"Title: {title}\nAuthors: {authors_str}\nSummary: {summary}"
            
        except Exception as e:
            return f"Arxiv 获取摘要请求失败: {str(e)}"
