"""DBLP publication search for computer-science review protocols."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.tools import BaseTool


class DblpSearchTool(BaseTool):
    name = "dblp_search"
    description = (
        "Search DBLP computer-science publications by English keywords. Returns title, "
        "authors, venue, year, DOI and source URL. DBLP usually has no abstract, so use "
        "the DOI/title with Crossref, OpenAlex or Semantic Scholar before paper_register."
    )
    parameters = {
        "query": "English title or computer-science keywords",
        "rows": "Number of records, 1 to 20 (default 5)",
        "offset": "Result offset for pagination (default 0)",
    }

    def execute(self, **kwargs) -> Any:
        query = str(kwargs.get("query") or "").strip()
        if not query:
            raise ValueError("dblp_search requires query")
        try:
            rows = max(1, min(20, int(kwargs.get("rows", 5))))
        except (TypeError, ValueError):
            rows = 5
        try:
            offset = max(0, int(kwargs.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0
        url = "https://dblp.org/search/publ/api?" + urllib.parse.urlencode({
            "q": query,
            "h": rows,
            "f": offset,
            "format": "json",
        })
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "AcademicResearchAgent/2.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return f"DBLP search failed: HTTP Error {exc.code}"
        except Exception as exc:
            return f"DBLP search failed: {exc}"

        raw_hits = (((payload.get("result") or {}).get("hits") or {}).get("hit")) or []
        if isinstance(raw_hits, dict):
            raw_hits = [raw_hits]
        results = []
        for hit in raw_hits:
            info = hit.get("info") or {}
            author_data = ((info.get("authors") or {}).get("author")) or []
            if isinstance(author_data, dict):
                author_data = [author_data]
            authors = ", ".join(
                str(item.get("text") if isinstance(item, dict) else item)
                for item in author_data
            )
            lines = [
                f"Title: {info.get('title', 'Unknown')}",
                f"Authors: {authors or 'Unknown'}",
                f"Year: {info.get('year', 'Unknown')}",
                f"Venue: {info.get('venue', 'Unknown')}",
                f"DOI: {info.get('doi', '') or 'Not provided'}",
                f"URL: {info.get('ee') or info.get('url') or ''}",
                "Abstract: Not provided by DBLP; fetch from another source before screening.",
            ]
            results.append("\n".join(lines))
        return "\n---\n".join(results) if results else f"DBLP found no publications for '{query}'."
