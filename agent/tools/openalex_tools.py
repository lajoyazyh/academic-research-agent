import json
import urllib.parse
import urllib.request
import urllib.error
from typing import Any
from core.tools import BaseTool

class OpenAlexSearchTool(BaseTool):
    name = "openalex_search"
    description = "用于在 OpenAlex 上检索综合领域论文（包含社科、医学、交叉学科等），返回标题、作者、年份、摘要、引用数及相关概念。"
    parameters = {
        "query": "搜索关键词，例如 'sociology of artificial intelligence'",
        "limit": "最大返回数，默认为5（可选）"
    }

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        limit = kwargs.get("limit", 5)
        if not query:
            return {"error": "Missing parameter 'query'"}
            
        encoded_query = urllib.parse.quote(query)
        # OpenAlex API documentation recommends using a polite pool by adding email but it's optional.
        url = f"https://api.openalex.org/works?search={encoded_query}&per-page={limit}&sort=relevance_score:desc"
        
        headers = {
            "User-Agent": "OpenAlexSearchTool/1.0 (mailto:your_email@example.com)"
        }
        
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
                        
                        parsed_results.append({
                            "title": title,
                            "authors": ", ".join(authors),
                            "publication_year": work.get("publication_year", "Unknown"),
                            "abstract": abstract,
                            "cited_by_count": work.get("cited_by_count", 0),
                            "concepts": concepts,
                            "doi": work.get("doi", ""),
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
