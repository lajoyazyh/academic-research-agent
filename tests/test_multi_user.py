from backend.copilot_session_manager import CopilotSessionManager
from backend.session_manager import SessionManager
from backend.skill_manager import SkillManager
from backend.tenant import reset_current_user, set_current_user, tenant_key


def _as_user(user_id: str, callback):
    token = set_current_user(user_id)
    try:
        return callback()
    finally:
        reset_current_user(token)


def test_session_data_is_isolated_between_authenticated_users(tmp_path):
    manager = SessionManager(str(tmp_path))
    alice = _as_user("alice-user", lambda: manager.create_session("Alice topic"))

    assert _as_user("alice-user", lambda: manager.load_session(alice["session_id"])) is not None
    assert _as_user("bob-user", lambda: manager.load_session(alice["session_id"])) is None
    assert (tmp_path / ".users" / tenant_key("alice-user")).exists()


def test_copilot_and_skills_are_user_scoped(tmp_path):
    copilot = CopilotSessionManager(str(tmp_path))
    skills = SkillManager(str(tmp_path))
    conversation = _as_user("alice-user", lambda: copilot.create_session("Alice chat"))
    skill = _as_user(
        "alice-user",
        lambda: skills.create_skill("Alice search", "search", "Only Alice can read this"),
    )

    assert _as_user("bob-user", lambda: copilot.get_session(conversation["session_id"])) is None
    assert _as_user("bob-user", lambda: skills.get_skill(skill["skill_id"])) is None


def test_local_mode_keeps_legacy_workspace_layout(tmp_path):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session("Local topic")

    assert (tmp_path / session["session_id"] / "metadata.json").exists()
    assert not (tmp_path / ".users").exists()
