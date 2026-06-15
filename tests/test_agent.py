from core.tools import CalculatorTool
from llms import client as llm_client_module
from llms.client import LLMClient
from main import _build_fallback_notes_from_traces
from backend.session_manager import STATE_LABELS
from backend.routes.models import ChatMessageRequest
from backend.routes.chat import chat_message


def test_calculator_tool():
    calc = CalculatorTool()
    assert "2" in calc.execute(expression="1 + 1")
    assert "14" in calc.execute(expression="2 * (3 + 4)")


def test_client_init_without_key_uses_defaults(monkeypatch):
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_BASE_URL", raising=False)
    monkeypatch.delenv("ZHIPU_MODEL", raising=False)

    monkeypatch.setattr(llm_client_module, "find_dotenv", lambda **kwargs: "")
    monkeypatch.setattr(llm_client_module, "load_dotenv", lambda *args, **kwargs: None)

    captured = {}

    class DummyHttpClient:
        pass

    class DummyOpenAI:
        def __init__(self, api_key, base_url, http_client):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["http_client"] = http_client
            self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": lambda *a, **k: None})()})()

    monkeypatch.setattr(llm_client_module.httpx, "Client", lambda **kwargs: DummyHttpClient())
    monkeypatch.setattr(llm_client_module, "OpenAI", DummyOpenAI)

    cli = LLMClient()

    assert cli.api_key == "your-api-key-here"
    assert cli.base_url == "https://open.bigmodel.cn/api/paas/v4/"
    assert cli.model == "glm-4-flash"
    assert captured["api_key"] == "your-api-key-here"
    assert captured["base_url"] == "https://open.bigmodel.cn/api/paas/v4/"
    assert isinstance(captured["http_client"], DummyHttpClient)


def test_client_chat_builds_messages(monkeypatch):
    monkeypatch.setattr(llm_client_module, "find_dotenv", lambda **kwargs: "")
    monkeypatch.setattr(llm_client_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_client_module.httpx, "Client", lambda **kwargs: object())

    captured = {}

    class DummyResponse:
        def __init__(self):
            self.choices = [type("Choice", (), {"message": type("Message", (), {"content": "ok"})()})()]

    class DummyCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return DummyResponse()

    class DummyOpenAI:
        def __init__(self, api_key, base_url, http_client):
            self.chat = type("Chat", (), {"completions": DummyCompletions()})()

    monkeypatch.setattr(llm_client_module, "OpenAI", DummyOpenAI)

    cli = LLMClient()
    content = cli.chat("sys", "usr", [{"role": "assistant", "content": "hist"}])

    assert content == "ok"
    assert captured["model"] == cli.model
    assert captured["temperature"] == 0.1
    assert captured["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "hist"},
        {"role": "user", "content": "usr"},
    ]


def test_build_fallback_notes_from_traces_returns_empty_when_no_observations():
    assert _build_fallback_notes_from_traces("topic", []) == ""


def test_build_fallback_notes_from_traces_extracts_supported_actions():
    traces = [
        {"action": "arxiv_search", "observation": "ID: 123\nTitle: Paper A"},
        {"action": "unknown_action", "observation": "should be ignored"},
        {"action": "crossref_search", "observation": "DOI: 10.1000/test"},
    ]

    notes = _build_fallback_notes_from_traces("Agent Memory", traces)

    assert notes.startswith("# 自动兜底笔记")
    assert "主题：Agent Memory" in notes
    assert "线索 1（arxiv_search）" in notes
    assert "线索 2（crossref_search）" in notes
    assert "should be ignored" not in notes


class _FakeSessionManager:
    def __init__(self, session: dict):
        self.session = session
        self.saved_feedback = None
        self.updated_state = None

    def load_session(self, session_id: str):
        return self.session

    def save_feedback(self, session_id: str, feedback: str):
        self.saved_feedback = feedback
        return {"feedback": feedback}

    def update_session_state(self, session_id: str, state: str):
        self.updated_state = state
        self.session["state"] = state
        return self.session

    def create_conversation(self, session_id: str, title: str = ""):
        return {"conv_id": "default"}

    def get_conversation_messages(self, session_id: str, conv_id: str):
        return []


class _FakeChatLLM:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = []

    def chat(self, system_prompt: str, user_prompt: str, history: list):
        self.calls.append((system_prompt, user_prompt, history))
        if not self.responses:
            raise AssertionError("unexpected extra LLM call")
        return self.responses.pop(0)


def test_chat_message_uses_ai_answer_for_normal_question(monkeypatch):
    session = {
        "session_id": "sess_test",
        "topic": "多智能体记忆机制",
        "state": "reviewing_notes",
        "papers": [
            {
                "paper_id": "p1",
                "title": "A Survey of Multi-Agent Deep Reinforcement Learning with Communication",
                "abstract": "This paper surveys communication in MADRL.",
                "status": "accepted",
            }
        ],
        "notes": "## 核心方法\n...",
        "draft": "## 引言\n...",
    }
    fake_llm = _FakeChatLLM([
        '这篇论文系统综述了多智能体深度强化学习中的通信方法。',
    ])
    monkeypatch.setattr("backend.routes.chat.session_mgr", _FakeSessionManager(session))
    monkeypatch.setattr("backend.routes.chat._get_chat_intent_llm", lambda: fake_llm)

    result = chat_message(
        "sess_test",
        ChatMessageRequest(message="介绍一下该论文", view_mode="report", chat_mode="agent", current_paper_id="p1"),
    )

    assert result["action"] == "chat"
    assert result["confirmation_required"] is False
    assert "系统综述了多智能体深度强化学习中的通信方法" in result["reply"]
    assert result["note"] == "基于当前论文上下文生成回答"
    assert len(fake_llm.calls) == 1


def test_chat_message_ai_revision_returns_confirmation(monkeypatch):
    session = {
        "session_id": "sess_test",
        "topic": "多智能体记忆机制",
        "state": "reviewing_notes",
        "papers": [
            {
                "paper_id": "p1",
                "title": "A Survey of Multi-Agent Deep Reinforcement Learning with Communication",
                "abstract": "This paper surveys communication in MADRL.",
                "status": "accepted",
            }
        ],
        "notes": "## 核心方法\n...",
        "draft": "## 引言\n...",
    }
    fake_llm = _FakeChatLLM([
        '{"intent":"revise","target":"report","confidence":0.95,"reason":"用户明确要求删除章节","feedback":"删除亮点与不足部分"}',
    ])
    monkeypatch.setattr("backend.routes.chat.session_mgr", _FakeSessionManager(session))
    monkeypatch.setattr("backend.routes.chat._get_chat_intent_llm", lambda: fake_llm)

    result = chat_message(
        "sess_test",
        ChatMessageRequest(message="请删除论文中的亮点与不足部分", view_mode="report", chat_mode="agent", current_paper_id="p1"),
    )

    assert result["action"] == "confirm_revision"
    assert result["confirmation_required"] is True
    assert result["pending_revision"] == {
        "target": "report",
        "feedback": "删除亮点与不足部分",
    }
    assert result["session_state_label"] == STATE_LABELS["reviewing_notes"]


def test_chat_message_explicit_revision_still_direct(monkeypatch):
    session = {
        "session_id": "sess_test",
        "topic": "多智能体记忆机制",
        "state": "reviewing_notes",
        "papers": [],
        "notes": "",
        "draft": "",
    }
    fake_manager = _FakeSessionManager(session)
    monkeypatch.setattr("backend.routes.chat.session_mgr", fake_manager)
    monkeypatch.setattr("backend.routes.agent.session_mgr", fake_manager)
    monkeypatch.setattr("backend.routes.chat.revise_notes_phase", lambda *args, **kwargs: {"notes": "更新后的笔记"})

    result = chat_message(
        "sess_test",
        ChatMessageRequest(message="/修订 删除亮点与不足部分", view_mode="report", chat_mode="agent", current_paper_id=None),
    )

    assert result["action"] == "revise_notes"
    assert result["action_taken"] is True
    assert result["notes"] == "更新后的笔记"
    assert fake_manager.updated_state == "reviewing_notes"


def test_chat_message_ai_revision_low_confidence_requests_clarification(monkeypatch):
    session = {
        "session_id": "sess_test",
        "topic": "多智能体记忆机制",
        "state": "reviewing_notes",
        "papers": [],
        "notes": "",
        "draft": "",
    }
    fake_llm = _FakeChatLLM([
        '{"intent":"revise","target":"report","confidence":0.4,"reason":"语义不够明确","feedback":""}',
    ])
    monkeypatch.setattr("backend.routes.chat.session_mgr", _FakeSessionManager(session))
    monkeypatch.setattr("backend.routes.chat._get_chat_intent_llm", lambda: fake_llm)

    result = chat_message(
        "sess_test",
        ChatMessageRequest(message="把它改一下", view_mode="report", chat_mode="agent", current_paper_id=None),
    )

    assert result["action"] == "clarify_revision"
    assert result["confirmation_required"] is False
    assert "还不能确定" in result["reply"]
    assert "语义不够明确" in result["note"]


def test_chat_message_explicit_review_revision_rewrites_draft(monkeypatch):
    session = {
        "session_id": "sess_test",
        "topic": "多智能体记忆机制",
        "state": "reviewing_draft",
        "papers": [],
        "notes": "",
        "draft": "旧草稿",
    }
    fake_manager = _FakeSessionManager(session)

    def fake_run_write_phase(session_id, payload):
        assert session_id == "sess_test"
        assert payload.topic == "多智能体记忆机制"
        assert payload.start_phase == "write"
        return {"draft": "更新后的综述草稿", "review": "更新后的综述草稿"}

    monkeypatch.setattr("backend.routes.chat.session_mgr", fake_manager)
    monkeypatch.setattr("backend.routes.agent.session_mgr", fake_manager)
    # monkeypatch chat.py 中导入的 run_write_phase（from .agent import）
    import backend.routes.chat as chat_mod
    monkeypatch.setattr(chat_mod, "run_write_phase", fake_run_write_phase)

    result = chat_message(
        "sess_test",
        ChatMessageRequest(message="/修订 请重写引言并删除重复段落", view_mode="review", chat_mode="agent", current_paper_id=None),
    )

    assert result["action"] == "revise_review"
    assert result["action_taken"] is True
    assert result["draft"] == "更新后的综述草稿"
    assert fake_manager.saved_feedback == "请重写引言并删除重复段落"


def test_chat_message_falls_back_to_template_when_answer_llm_fails(monkeypatch):
    session = {
        "session_id": "sess_test",
        "topic": "多智能体记忆机制",
        "state": "reviewing_notes",
        "papers": [
            {
                "paper_id": "p1",
                "title": "A Survey of Multi-Agent Deep Reinforcement Learning with Communication",
                "abstract": "This paper surveys communication in MADRL.",
                "status": "accepted",
            }
        ],
        "notes": "## 核心方法\n...",
        "draft": "## 引言\n...",
    }

    class _FailingAnswerLLM:
        def chat(self, system_prompt: str, user_prompt: str, history: list):
            raise RuntimeError("LLM unavailable")

    monkeypatch.setattr("backend.routes.chat.session_mgr", _FakeSessionManager(session))
    monkeypatch.setattr("backend.routes.chat._get_chat_intent_llm", lambda: _FailingAnswerLLM())

    result = chat_message(
        "sess_test",
        ChatMessageRequest(message="介绍一下该论文", view_mode="summary", chat_mode="agent", current_paper_id="p1"),
    )

    assert result["action"] == "chat"
    assert result["confirmation_required"] is False
    assert "摘要内容" in result["reply"]
