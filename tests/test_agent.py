from core.tools import CalculatorTool
from llms import client as llm_client_module
from llms.client import LLMClient
from main import _build_fallback_notes_from_traces


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
