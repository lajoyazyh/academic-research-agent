import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.session_manager import SessionManager
from backend.routes import agent as agent_routes
from backend.routes.models import AutoRunRequest, RunPhaseRequest
from core.agent import BaseAgent
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
    session = manager.create_session("")
    session_id = session["session_id"]
    papers_dir = tmp_path / session_id / "papers"
    tool = PaperRegisterTool(session_id=session_id, papers_dir=str(papers_dir))
    monkeypatch.setattr(tool, "_try_download_pdf", lambda *_args, **_kwargs: (False, "not available", ""))

    result = tool.execute(
        paper_id="2401.00001",
        title="Relevant agent-screened paper",
        abstract="This paper presents a directly relevant method.",
    )

    papers = manager.get_papers(session_id)
    assert "论文新增成功" in result
    assert tool.get_registered_count() == 1
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


def test_search_target_accepts_up_to_fifteen_papers():
    request = RunPhaseRequest(topic="Configurable search", target_new_papers=15)
    assert request.target_new_papers == 15


@pytest.mark.parametrize("target", [0, 16, -1])
def test_search_target_rejects_values_outside_supported_range(target):
    with pytest.raises(ValidationError):
        RunPhaseRequest(topic="Invalid search target", target_new_papers=target)


def test_auto_search_target_uses_same_supported_range():
    assert AutoRunRequest(topic="Auto", min_papers=15).min_papers == 15
    with pytest.raises(ValidationError):
        AutoRunRequest(topic="Auto", min_papers=16)


def test_register_rejects_missing_session_before_downloading(tmp_path, monkeypatch):
    tool = PaperRegisterTool(
        session_id="missing-session",
        papers_dir=str(tmp_path / "missing-session" / "papers"),
        sessions_root=str(tmp_path),
    )
    downloaded = []
    monkeypatch.setattr(tool, "_try_download_pdf", lambda *_args: downloaded.append(True))

    result = tool.execute(
        paper_id="2401.00001",
        title="Paper",
        abstract="Relevant abstract",
    )

    assert "Session missing-session 不存在" in result
    assert "论文新增成功" not in result
    assert downloaded == []
    assert tool.get_registered_count() == 0


def test_register_failure_cannot_emit_success_marker(tmp_path, monkeypatch):
    class FailingManager:
        def load_session(self, _session_id):
            return {"topic": ""}

        def find_duplicate_paper(self, _session_id, _paper):
            return None

        def add_paper(self, _session_id, _paper):
            raise ValueError("durable write failed")

    tool = PaperRegisterTool(session_id="session", papers_dir=str(tmp_path / "papers"))
    monkeypatch.setattr(tool, "_session_manager", lambda: FailingManager())
    downloaded = []
    monkeypatch.setattr(tool, "_try_download_pdf", lambda *_args: downloaded.append(True))

    result = tool.execute(
        paper_id="2401.00002",
        title="Paper",
        abstract="Relevant abstract",
    )

    assert "论文登记失败" in result
    assert "论文新增成功" not in result
    assert downloaded == []


def test_quality_gate_progress_ignores_misleading_observation_text(monkeypatch):
    class NoopLLM:
        pass

    monkeypatch.setattr("core.agent.LLMClient", lambda *_args, **_kwargs: NoopLLM())
    agent = BaseAgent(tools=[], min_new_papers=6, paper_progress_getter=lambda: 0)
    agent.traces.append({"action": "paper_register", "observation": "✅ 论文新增成功"})

    assert agent.get_registered_paper_count() == 0


@pytest.mark.parametrize(
    ("new_count", "target", "expected"),
    [
        (6, 6, ("complete", "search_complete")),
        (3, 6, ("partial", "search_partial")),
        (0, 6, ("failed", "search_failed")),
    ],
)
def test_search_outcome_uses_real_session_delta(new_count, target, expected):
    assert agent_routes.classify_search_outcome(new_count, target) == expected


@pytest.mark.parametrize("outcome_state", ["search_complete", "search_partial", "search_failed"])
def test_searching_can_finish_with_explicit_outcome_state(tmp_path, outcome_state):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Outcome", keywords=[{"original": "outcome"}])
    manager.update_session_state(session["session_id"], "searching")

    updated = manager.update_session_state(session["session_id"], outcome_state)

    assert updated["state"] == outcome_state


def test_research_prompt_only_advertises_enabled_tools():
    prompt = _build_research_query(
        "Niche title",
        "Plan",
        target_new_papers=6,
        available_tool_names=["arxiv_search", "arxiv_fetch", "paper_register"],
    )

    allowed_section = prompt.split("## 🛠 本轮真实可用工具（唯一允许列表）", 1)[1].split("## ⚠️", 1)[0]
    assert "arxiv_search" in allowed_section
    assert "openalex_search" not in allowed_section
    assert "至少 6 篇" in prompt
