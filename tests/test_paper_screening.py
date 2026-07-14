import pytest

from backend.session_manager import SessionManager
from tools.paper_register import PaperRegisterTool


def test_paper_status_update_is_persisted_and_validated(tmp_path):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Screening topic")
    session_id = session["session_id"]
    manager.add_paper(session_id, {"paper_id": "paper-1", "title": "Paper one"})

    updated = manager.update_paper_status(session_id, "paper-1", "accepted")
    assert updated["papers"][0]["status"] == "accepted"

    with pytest.raises(ValueError, match="不支持的论文状态"):
        manager.update_paper_status(session_id, "paper-1", "unknown")
    with pytest.raises(ValueError, match="不存在"):
        manager.update_paper_status(session_id, "missing", "accepted")


def test_agent_screened_paper_is_registered_as_accepted(tmp_path, monkeypatch):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Agent topic")
    session_id = session["session_id"]
    papers_dir = tmp_path / session_id / "papers"
    tool = PaperRegisterTool(session_id=session_id, papers_dir=str(papers_dir))
    monkeypatch.setattr(tool, "_try_download_pdf", lambda *_args, **_kwargs: (False, "not available", ""))

    tool.execute(paper_id="2401.00001", title="Relevant agent-screened paper")

    papers = manager.get_papers(session_id)
    assert len(papers) == 1
    assert papers[0]["status"] == "accepted"
