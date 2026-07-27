import io
import json
import zipfile

from backend.cloud_persistence import SupabaseWorkspaceStore
from backend.session_manager import SessionManager
from backend.tenant import reset_current_user, set_current_user, tenant_path


def _create_tenant_session(root, user_id="user-123"):
    token = set_current_user(user_id)
    try:
        manager = SessionManager(str(root))
        session = manager.create_session("Queryable research session")
        session_dir = tenant_path(root, user_id) / session["session_id"]
        manager.save_papers_list(session["session_id"], [{
            "paper_id": "paper-1",
            "title": "A paper",
            "status": "accepted",
            "notes": "Evidence note",
            "api_key": "must-not-leak",
        }])
        (session_dir / "papers" / "paper-1.pdf").write_bytes(b"%PDF-test")
        return session_dir
    finally:
        reset_current_user(token)


def test_relational_snapshot_is_queryable_and_strips_credentials(tmp_path):
    session_dir = _create_tenant_session(tmp_path)
    store = SupabaseWorkspaceStore(tmp_path)

    snapshot, summary = store._snapshot_from_dir(session_dir)
    raw = json.dumps(snapshot)

    assert summary["topic"] == "Queryable research session"
    assert summary["paper_count"] == 1
    assert summary["total_notes"] == 1
    assert "must-not-leak" not in raw
    assert "api_key" not in raw


def test_compatibility_archive_excludes_large_paper_files(tmp_path):
    session_dir = _create_tenant_session(tmp_path)
    store = SupabaseWorkspaceStore(tmp_path)

    archive = store._session_archive(session_dir)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = bundle.namelist()

    assert "metadata.json" in names
    assert "papers/papers_list.json" in names
    assert "papers/paper-1.pdf" not in names


def test_existing_relational_index_does_not_download_legacy_workspace(tmp_path, monkeypatch):
    store = SupabaseWorkspaceStore(tmp_path)
    store.url = "https://example.supabase.co"
    store.service_key = "service-role"
    row = {
        "session_id": "sess_database",
        "topic": "Loaded from Postgres",
        "state": "planning",
        "updated_at": "2026-07-27T00:00:00+00:00",
        "paper_count": 0,
        "note_size": 0,
        "total_notes": 0,
        "review_count": 0,
        "review_version": 0,
    }
    monkeypatch.setattr(store, "_select_session_rows", lambda _user_id: [row])

    def legacy_should_not_run(_user_id):
        raise AssertionError("legacy workspace should not be downloaded")

    monkeypatch.setattr(store, "_legacy_workspace", legacy_should_not_run)

    assert store.list_sessions("user-123") == [row]


def test_relational_migration_declares_all_workspace_tables():
    migration = (
        __import__("pathlib").Path(__file__).parents[1]
        / "supabase"
        / "migrations"
        / "002_relational_research.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "research_sessions",
        "research_papers",
        "research_artifacts",
        "research_conversations",
        "research_messages",
        "research_runs",
        "research_files",
    ):
        assert f"public.{table}" in migration
