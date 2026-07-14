import io
import json
import zipfile

import pytest

from backend.artifact_export import collect_artifacts, render_export
from backend.github_client import GitHubClient, validate_repo
from main import _append_verified_references, assess_review_quality


@pytest.fixture
def sample_session():
    return {
        "session_id": "sess_demo",
        "topic": "Retrieval-Augmented Generation",
        "review": "## 摘要\n\n现有研究展示了不同检索策略。[P1]\n\n## 结论\n\n证据仍有限。[P1]",
        "notes": "## Paper A\n\nMethod and result notes.",
        "initial_plan": "Search arXiv and OpenAlex.",
        "papers": [{"paper_id": "2401.00001", "title": "Paper A", "authors": "A. Author", "url": "https://arxiv.org/abs/2401.00001"}],
        "repositories": [{"full_name": "owner/repo", "html_url": "https://github.com/owner/repo", "report": "Repository report"}],
        "analysis": {"document": "## Comparison\n\nComparison text."},
    }


@pytest.mark.parametrize("export_format,magic", [
    ("md", b"# Retrieval"),
    ("html", b"<!doctype html>"),
    ("txt", b"Retrieval"),
    ("json", b"{"),
    ("pdf", b"%PDF"),
])
def test_render_common_export_formats(sample_session, export_format, magic):
    payload, media_type, filename = render_export(collect_artifacts(sample_session), export_format)
    assert payload.startswith(magic)
    assert media_type
    assert filename.endswith("." + export_format)


def test_render_docx_is_valid_office_zip(sample_session):
    payload, _, filename = render_export(collect_artifacts(sample_session), "docx")
    assert filename.endswith(".docx")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert "word/document.xml" in archive.namelist()
        assert "Retrieval-Augmented Generation" in archive.read("word/document.xml").decode("utf-8")


def test_zip_contains_portable_research_package(sample_session):
    payload, _, _ = render_export(collect_artifacts(sample_session), "zip")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        assert any(name.endswith(".md") for name in names)
        assert any(name.endswith(".html") for name in names)
        assert any(name.endswith(".json") for name in names)


def test_review_references_are_deterministic_and_quality_flags_invalid_ids():
    sources = [{"id": "P1", "title": "Paper A", "authors": "A", "year": "2024", "identifier": "doi:1", "url": "https://example.com"}]
    review = "## 摘要\n\n结果得到支持。[P1][P9]\n\n## 参考来源\n\n- fabricated"
    final = _append_verified_references(review, sources)
    assert "fabricated" not in final
    assert "[P1] Paper A" in final
    quality = assess_review_quality(final, sources)
    assert quality["invalid_citations"] == ["P9"]
    assert quality["status"] == "needs_review"


def test_repository_identifier_validation():
    assert validate_repo("owner/repository") == ("owner", "repository")
    assert validate_repo("https://github.com/owner/repository.git") == ("owner", "repository")
    with pytest.raises(ValueError):
        validate_repo("https://example.com/owner/repository")


def test_github_put_file_updates_existing_content(monkeypatch):
    calls = []

    def fake_request(self, method, path, data=None, accept="application/vnd.github+json"):
        calls.append((method, path, data))
        if method == "GET" and "/contents/" in path:
            return {"sha": "existing-sha"}
        if method == "PUT":
            return {"content": {"html_url": "https://github.com/o/r/blob/main/review.md"}, "commit": {"html_url": "https://github.com/o/r/commit/1"}}
        return {"default_branch": "main"}

    monkeypatch.setattr(GitHubClient, "_request", fake_request)
    result = GitHubClient("token").put_file("o", "r", "review.md", b"hello", "export", branch="main")
    put_call = next(call for call in calls if call[0] == "PUT")
    assert put_call[2]["sha"] == "existing-sha"
    assert put_call[2]["branch"] == "main"
    assert result["branch"] == "main"
