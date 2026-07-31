import json
import urllib.parse
import urllib.request
import urllib.error
import os
from typing import Any
from core.tools import BaseTool

class OpenAlexSearchTool(BaseTool):
    name = "openalex_search"
    description = "用于在 OpenAlex 上检索综合领域论文（包含社科、医学、交叉学科等），返回标题、作者、年份、摘要、引用数及相关概念。⚠️ 仅支持英文关键词，中文关键词无法检索到结果。"
    parameters = {
        "query": "英文搜索关键词，例如 'sociology of artificial intelligence'（请勿使用中文）",
        "limit": "最大返回数，默认为5（可选）",
        "page": "结果页码；增量检索时可设为 2、3 等（可选）",
    }

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        limit = kwargs.get("limit", 5)
        try:
            page = max(1, int(kwargs.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        if not query:
            return {"error": "Missing parameter 'query'"}
            
        encoded_query = urllib.parse.quote(query)
        # OpenAlex API documentation recommends using a polite pool by adding email but it's optional.
        contact = os.getenv("OPENALEX_EMAIL", "").strip() or os.getenv("SCHOLAR_CONTACT_EMAIL", "").strip()
        url = f"https://api.openalex.org/works?search={encoded_query}&per-page={limit}&page={page}&sort=relevance_score:desc"
        if contact:
            url += f"&mailto={urllib.parse.quote(contact)}"
        
        user_agent = "AcademicResearchAgent/1.0"
        if contact:
            user_agent += f" (mailto:{contact})"
        headers = {"User-Agent": user_agent, "Accept": "application/json"}
        
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    results = data.get("results", [])
                    
                    parsed_results = []
                    for work in results:
                        # Extract title
                        title = work.get("title", "")
                        
                        # Extract authors
                        authors = []
                        for authorship in work.get("authorships", []):
                            author = authorship.get("author", {})
                            authors.append(author.get("display_name", ""))
                            
                        # Extract abstract (OpenAlex returns abstract_inverted_index)
                        abstract_inverted = work.get("abstract_inverted_index", {})
                        abstract = self._reconstruct_abstract(abstract_inverted)
                        
                        # Extract ideas/concepts
                        concepts = [c.get("display_name", "") for c in work.get("concepts", [])[:3]]
                        
                        # Extract PDF URL if open access
                        oa = work.get("open_access", {})
                        pdf_url = oa.get("oa_url", "") if isinstance(oa, dict) else ""
                        work_ids = work.get("ids") or {}
                        
                        parsed_results.append({
                            "openalex_id": str(work.get("id") or "").rsplit("/", 1)[-1],
                            "title": title,
                            "authors": ", ".join(authors),
                            "publication_year": work.get("publication_year", "Unknown"),
                            "abstract": abstract,
                            "cited_by_count": work.get("cited_by_count", 0),
                            "concepts": concepts,
                            "doi": work.get("doi", ""),
                            "arxiv_id": str(work_ids.get("arxiv") or "").replace("https://arxiv.org/abs/", ""),
                            "pdf_url": pdf_url
                        })
                    
                    if not parsed_results:
                        return f"在 OpenAlex 中未找到相关论文，请尝试更换关键词: {query}"
                        
                    return json.dumps(parsed_results, ensure_ascii=False, indent=2)
                else:
                    return f"OpenAlex API Error: {response.status}"
        except Exception as e:
            return f"Error executing OpenAlex search: {str(e)}"
            
    def _reconstruct_abstract(self, inverted_index: dict) -> str:
        if not inverted_index:
            return "No abstract available."
            
        # OpenAlex provides an inverted index. We need to reconstruct the string.
        # Format: {"Word": [0, 5], "Another": [1]}
        # Find the max index to create a list of proper length
        max_idx = 0
        for positions in inverted_index.values():
            if positions:
                max_idx = max(max_idx, max(positions))
                
        words = [""] * (max_idx + 1)
        for word, positions in inverted_index.items():
            for pos in positions:
                if pos <= max_idx:
                    words[pos] = word
                    
        # Filter out empty strings and join
        return " ".join([w for w in words if w])


class OpenAlexCitationTool(OpenAlexSearchTool):
    name = "openalex_citations"
    description = (
        "Expand an OpenAlex work through its citation network. direction may be "
        "'cited_by' (forward citations), 'references' (backward citations), or "
        "'related'. Returns metadata and abstracts for screening."
    )
    parameters = {
        "work_id": "OpenAlex work id such as W2741809807, or a DOI",
        "direction": "cited_by, references, or related",
        "limit": "maximum records, 1 to 20 (default 5)",
    }

    def _get_json(self, url: str) -> dict:
        contact = os.getenv("OPENALEX_EMAIL", "").strip() or os.getenv("SCHOLAR_CONTACT_EMAIL", "").strip()
        if contact:
            url += ("&" if "?" in url else "?") + "mailto=" + urllib.parse.quote(contact)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AcademicResearchAgent/2.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _compact(self, work: dict) -> dict:
        ids = work.get("ids") or {}
        authors = [
            ((item.get("author") or {}).get("display_name") or "")
            for item in work.get("authorships") or []
        ]
        best_location = work.get("best_oa_location") or {}
        return {
            "openalex_id": str(work.get("id") or "").rsplit("/", 1)[-1],
            "title": work.get("title") or "",
            "authors": ", ".join(item for item in authors if item),
            "publication_year": work.get("publication_year"),
            "abstract": self._reconstruct_abstract(work.get("abstract_inverted_index") or {}),
            "doi": str(ids.get("doi") or work.get("doi") or "").replace("https://doi.org/", ""),
            "arxiv_id": str(ids.get("arxiv") or "").replace("https://arxiv.org/abs/", ""),
            "pdf_url": best_location.get("pdf_url") or "",
            "cited_by_count": work.get("cited_by_count", 0),
        }

    def execute(self, **kwargs) -> Any:
        work_id = str(kwargs.get("work_id") or "").strip()
        direction = str(kwargs.get("direction") or "cited_by").strip()
        if not work_id:
            return {"error": "Missing parameter 'work_id'"}
        if direction not in {"cited_by", "references", "related"}:
            return {"error": "direction must be cited_by, references, or related"}
        try:
            limit = max(1, min(20, int(kwargs.get("limit", 5))))
        except (TypeError, ValueError):
            limit = 5
        identifier = work_id if work_id.upper().startswith("W") else "https://doi.org/" + work_id.replace("https://doi.org/", "")
        try:
            target = self._get_json("https://api.openalex.org/works/" + urllib.parse.quote(identifier, safe=":/"))
            target_id = str(target.get("id") or "").rsplit("/", 1)[-1]
            if direction == "cited_by":
                payload = self._get_json(
                    f"https://api.openalex.org/works?filter=cites:{target_id}&per-page={limit}&sort=cited_by_count:desc"
                )
                works = payload.get("results") or []
            else:
                ids = target.get("referenced_works") if direction == "references" else target.get("related_works")
                works = []
                for item in (ids or [])[:limit]:
                    try:
                        works.append(self._get_json(str(item)))
                    except Exception:
                        continue
            return json.dumps([self._compact(work) for work in works], ensure_ascii=False, indent=2)
        except urllib.error.HTTPError as exc:
            return f"OpenAlex citation expansion failed: HTTP Error {exc.code}"
        except Exception as exc:
            return f"OpenAlex citation expansion failed: {exc}"

