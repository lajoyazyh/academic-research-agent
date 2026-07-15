import pytest
from fastapi import HTTPException

from backend.session_manager import SessionManager
from backend.routes import agent as agent_routes
from backend.routes.models import RunPhaseRequest
from main import _build_research_query
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


def test_cross_provider_duplicate_does_not_create_second_paper(tmp_path, monkeypatch):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Deduplication topic")
    session_id = session["session_id"]
    manager.add_paper(session_id, {
        "paper_id": "2401.00001",
        "title": "A Canonical Research Paper",
        "status": "accepted",
    })

    tool = PaperRegisterTool(session_id=session_id, papers_dir=str(tmp_path / session_id / "papers"))
    monkeypatch.setattr(tool, "_try_download_pdf", lambda *_args, **_kwargs: (False, "not available", ""))
    result = tool.execute(
        paper_id="10.48550/arXiv.2401.00001",
        title="A Canonical Research Paper",
    )

    assert "已存在，未新增" in result
    assert len(manager.get_papers(session_id)) == 1


def test_review_staleness_tracks_exact_accepted_snapshot(tmp_path):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Snapshot topic")
    session_id = session["session_id"]
    manager.add_paper(session_id, {"paper_id": "p1", "title": "Paper one", "status": "accepted"})
    manager.add_paper(session_id, {"paper_id": "p2", "title": "Paper two", "status": "pending"})
    manager.save_review(session_id, "# Review", referenced_papers=["p1"])

    assert manager.load_session(session_id)["review_is_stale"] is False
    manager.update_paper_status(session_id, "p2", "accepted")
    assert manager.load_session(session_id)["review_is_stale"] is True


def test_write_phase_uses_only_explicitly_accepted_papers(tmp_path, monkeypatch):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Selection topic")
    session_id = session["session_id"]
    manager.add_paper(session_id, {
        "paper_id": "included", "title": "Included", "status": "accepted", "notes": "included evidence",
    })
    manager.add_paper(session_id, {
        "paper_id": "excluded", "title": "Excluded", "status": "rejected", "notes": "excluded evidence",
    })
    captured = {}

    def fake_writer(**kwargs):
        captured.update(kwargs)
        return {"review": "## Review\n\nSupported [P1]", "quality": {}, "can_rewrite": True, "traces": []}

    monkeypatch.setattr(agent_routes, "session_mgr", manager)
    monkeypatch.setattr(agent_routes, "ensure_provider_available", lambda _provider: {})
    monkeypatch.setattr("main.run_write_from_notes", fake_writer)

    agent_routes.run_write_phase(
        session_id,
        RunPhaseRequest(topic="Selection topic", start_phase="write", paper_ids=["included"]),
    )

    assert [paper["paper_id"] for paper in captured["papers_list"]] == ["included"]
    assert "included evidence" in captured["notes_content"]
    assert "excluded evidence" not in captured["notes_content"]
    saved = manager.load_session(session_id)
    assert saved["review_referenced_papers"] == ["included"]


def test_write_phase_rejects_empty_selection(tmp_path, monkeypatch):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("No selection")
    manager.add_paper(
        session["session_id"],
        {"paper_id": "accepted-but-not-selected", "title": "Accepted", "status": "accepted", "notes": "evidence"},
    )
    monkeypatch.setattr(agent_routes, "session_mgr", manager)
    monkeypatch.setattr(agent_routes, "ensure_provider_available", lambda _provider: {})

    with pytest.raises(HTTPException, match="至少纳入一篇论文"):
        agent_routes.run_write_phase(
            session["session_id"],
            RunPhaseRequest(topic="No selection", start_phase="write", paper_ids=[]),
        )


def test_incremental_search_prompt_excludes_existing_papers_and_targets_real_additions():
    prompt = _build_research_query(
        "Agent memory",
        "Search plan",
        [{"original": "memory", "english": "agent memory", "synonyms": "long-term memory"}],
        existing_papers=[{"paper_id": "2401.00001", "title": "Existing Memory Paper"}],
        target_new_papers=4,
        search_mode="incremental",
    )

    assert "实际新增 4 篇" in prompt
    assert "2401.00001 | Existing Memory Paper" in prompt
    assert "禁止重复登记" in prompt
