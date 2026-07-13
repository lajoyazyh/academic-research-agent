import hashlib
import io
from pathlib import Path

import fitz
import pytest
from fastapi import HTTPException, UploadFile

from backend.routes import pages as pages_routes
from backend.routes import session as session_routes
from backend.session_manager import SessionManager


def _sample_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Authenticated PDF preview test")
    payload = document.tobytes()
    document.close()
    return payload


def test_pdf_endpoint_returns_file_and_explicit_404(tmp_path, monkeypatch):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("PDF delivery")
    paper_dir = tmp_path / session["session_id"] / "papers"
    paper_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = paper_dir / "paper-123.pdf"
    pdf_path.write_bytes(_sample_pdf())

    monkeypatch.setattr(pages_routes, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(pages_routes, "session_mgr", manager)

    response = pages_routes.get_pdf(session["session_id"], pdf_path.name)
    assert Path(response.path) == pdf_path
    assert response.media_type == "application/pdf"

    with pytest.raises(HTTPException) as exc_info:
        pages_routes.get_pdf(session["session_id"], "missing.pdf")
    assert exc_info.value.status_code == 404


def test_pdf_endpoint_supports_legacy_uploaded_filename(tmp_path, monkeypatch):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Legacy upload")
    paper_dir = tmp_path / session["session_id"] / "papers"
    paper_dir.mkdir(parents=True, exist_ok=True)
    legacy_path = paper_dir / "original upload.pdf"
    legacy_path.write_bytes(_sample_pdf())
    manager.save_papers_list(session["session_id"], [{
        "paper_id": "paper-legacy",
        "title": "Original paper title",
        "original_filename": legacy_path.name,
    }])

    monkeypatch.setattr(pages_routes, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(pages_routes, "session_mgr", manager)

    response = pages_routes.get_pdf(session["session_id"], "paper-legacy.pdf")
    assert Path(response.path) == legacy_path


@pytest.mark.asyncio
async def test_uploaded_pdf_uses_stable_safe_filename(tmp_path, monkeypatch):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Safe upload")
    monkeypatch.setattr(session_routes, "session_mgr", manager)

    import llms.client

    class FakeLLMClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, *args, **kwargs):
            return '{"title":"Uploaded paper","authors":"Test Author"}'

    monkeypatch.setattr(llms.client, "LLMClient", FakeLLMClient)

    upload = UploadFile(filename="../unsafe-name.pdf", file=io.BytesIO(_sample_pdf()))
    result = await session_routes.upload_paper(session["session_id"], upload)

    clean_id = "paper_" + hashlib.md5(b"unsafe-name.pdf").hexdigest()[:8]
    stored_path = tmp_path / session["session_id"] / "papers" / f"{clean_id}.pdf"
    assert result["message"] == "Success"
    assert stored_path.exists()
    assert not (tmp_path / session["session_id"] / "unsafe-name.pdf").exists()
    paper = manager.get_papers(session["session_id"])[0]
    assert paper["paper_id"] == clean_id
    assert paper["original_filename"] == "unsafe-name.pdf"
    assert paper["pdf_filename"] == f"{clean_id}.pdf"
