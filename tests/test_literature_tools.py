import json
import xml.etree.ElementTree as ET

import pytest

from tools import arxiv_tools
from tools.arxiv_tools import ArxivSearchTool, _build_query_variants
from tools.crossref_tools import CrossrefFetchByDoiTool, CrossrefSearchTool
from tools.semantic_scholar_tools import SemanticScholarFetchTool, SemanticScholarSearchTool


ATOM_NS = "{http://www.w3.org/2005/Atom}"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ARXIV_API_BASE", raising=False)
    monkeypatch.delenv("ARXIV_USER_AGENT", raising=False)
    monkeypatch.delenv("ARXIV_SEARCH_RETRY_LIMIT", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_BASE", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)


def _make_arxiv_entry(paper_id: str, title: str, published: str) -> ET.Element:
    entry = ET.Element(f"{ATOM_NS}entry")
    id_el = ET.SubElement(entry, f"{ATOM_NS}id")
    id_el.text = f"http://arxiv.org/abs/{paper_id}"
    title_el = ET.SubElement(entry, f"{ATOM_NS}title")
    title_el.text = title
    published_el = ET.SubElement(entry, f"{ATOM_NS}published")
    published_el.text = published
    return entry


def test_build_query_variants_relaxes_query():
    variants = _build_query_variants("LLM Agent Memory (framework)")

    assert variants[0] == "LLM Agent Memory (framework)"
    assert any("framework" not in variant.lower() for variant in variants)
    assert any("LLM Agent Memory" in variant for variant in variants)


def test_arxiv_search_tool_retries_with_relaxed_query(monkeypatch):
    attempts = []

    def fake_fetch_arxiv_entries(query, max_results, base_url, user_agent):
        attempts.append(query)
        if len(attempts) == 1:
            return [], query
        return [_make_arxiv_entry("2401.12345", "Relaxed Query Paper", "2024-01-01T00:00:00Z")], query

    monkeypatch.setenv("ARXIV_SEARCH_RETRY_LIMIT", "3")
    monkeypatch.setattr(arxiv_tools, "_fetch_arxiv_entries", fake_fetch_arxiv_entries)

    result = ArxivSearchTool().execute(query="LLM Agent Memory (framework)", max_results=5)

    assert attempts[0] == "LLM Agent Memory (framework)"
    assert len(attempts) >= 2
    assert "原始关键词 'LLM Agent Memory (framework)' 未直接命中" in result
    assert "ID: 2401.12345" in result
    assert "Title: Relaxed Query Paper" in result


def test_arxiv_search_tool_returns_clear_message_when_all_variants_empty(monkeypatch):
    attempts = []

    def fake_fetch_arxiv_entries(query, max_results, base_url, user_agent):
        attempts.append(query)
        return [], query

    monkeypatch.setenv("ARXIV_SEARCH_RETRY_LIMIT", "2")
    monkeypatch.setattr(arxiv_tools, "_fetch_arxiv_entries", fake_fetch_arxiv_entries)

    result = ArxivSearchTool().execute(query="UltraSpecific Agent Topic", max_results=5)

    assert len(attempts) == 2
    assert "未找到关于 'UltraSpecific Agent Topic' 的论文" in result


def test_semantic_scholar_search_tool_parses_response(monkeypatch):
    payload = {
        "data": [
            {
                "paperId": "abc123",
                "title": "Semantic Scholar Paper",
                "authors": [{"name": "Alice"}, {"name": "Bob"}],
                "year": 2024,
                "venue": "ICLR",
                "abstract": "This is a concise abstract.",
                "url": "https://example.com/paper",
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "citationCount": 42,
            }
        ]
    }

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = SemanticScholarSearchTool().execute(query="LLM Agent Memory", limit=1)

    assert "Semantic Scholar Paper" in result
    assert "Authors: Alice, Bob" in result
    assert "OpenAccessPDF: https://example.com/paper.pdf" in result
    assert "paper/search" in captured["url"]


def test_semantic_scholar_fetch_tool_parses_response(monkeypatch):
    payload = {
        "paperId": "abc123",
        "title": "Detailed Semantic Scholar Paper",
        "authors": [{"name": "Alice"}],
        "year": 2024,
        "venue": "NeurIPS",
        "abstract": "A detailed abstract for the paper.",
        "url": "https://example.com/detail",
        "openAccessPdf": {"url": "https://example.com/detail.pdf"},
        "externalIds": {"DOI": "10.1000/example"},
        "citationCount": 12,
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(request):
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = SemanticScholarFetchTool().execute(paper_id="abc123")

    assert "Detailed Semantic Scholar Paper" in result
    assert "Authors: Alice" in result
    assert "OpenAccessPDF: https://example.com/detail.pdf" in result
    assert "ExternalIds" in result


def test_crossref_search_tool_parses_response(monkeypatch):
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/example",
                    "title": ["Crossref Paper"],
                    "author": [{"given": "Alice", "family": "Smith"}],
                    "container-title": ["Journal of Agents"],
                    "published-online": {"date-parts": [[2024, 1, 10]]},
                    "publisher": "Test Publisher",
                    "URL": "https://doi.org/10.1000/example",
                }
            ]
        }
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda request: FakeResponse())

    result = CrossrefSearchTool().execute(query="Crossref Paper", rows=1)

    assert "DOI: 10.1000/example" in result
    assert "Title: Crossref Paper" in result
    assert "Journal: Journal of Agents" in result
    assert "Published: 2024-1-10" in result


def test_crossref_search_rejects_arxiv_id_like_query():
    result = CrossrefSearchTool().execute(query="2409.01907v1", rows=1)
    assert "更像 arXiv ID" in result
    assert "不建议直接用于 Crossref 关键词检索" in result


def test_crossref_search_skips_low_relevance_results(monkeypatch):
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/example",
                    "title": ["Completely Unrelated Entry"],
                    "author": [{"given": "Alice", "family": "Smith"}],
                    "container-title": ["Journal of Agents"],
                    "published-online": {"date-parts": [[2024, 1, 10]]},
                    "publisher": "Test Publisher",
                    "URL": "https://doi.org/10.1000/example",
                }
            ]
        }
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda request: FakeResponse())

    result = CrossrefSearchTool().execute(query="LLM Agent Memory", rows=1)
    assert "关键词重合度偏低" in result
    assert "已跳过 1 条低相关记录" in result


def test_crossref_fetch_doi_tool_parses_response(monkeypatch):
    payload = {
        "message": {
            "DOI": "10.1000/example",
            "title": ["Crossref Detailed Paper"],
            "author": [{"given": "Bob", "family": "Lee"}],
            "container-title": ["Conference on Agents"],
            "issued": {"date-parts": [[2023, 12, 1]]},
            "publisher": "Conf Publisher",
            "type": "proceedings-article",
            "URL": "https://doi.org/10.1000/example",
        }
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda request: FakeResponse())

    result = CrossrefFetchByDoiTool().execute(doi="10.1000/example")

    assert "Title: Crossref Detailed Paper" in result
    assert "Authors: Bob Lee" in result
    assert "Type: proceedings-article" in result

