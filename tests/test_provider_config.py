from backend import provider
from backend.routes import pages


def test_provider_catalog_contains_supported_presets():
    catalog = provider.public_provider_catalog()
    ids = {item["id"] for item in catalog["providers"]}
    assert catalog["default_provider_id"] == "zhipu"
    assert {"zhipu", "openai", "custom"}.issubset(ids)
    zhipu = next(item for item in catalog["providers"] if item["id"] == "zhipu")
    assert zhipu["default_embedding_model"] == "embedding-3"
    assert zhipu["embedding_models"] == ["embedding-3", "embedding-2"]


def test_provider_config_keeps_model_alias_compatible():
    config = provider.sanitize_provider_config({
        "provider_id": "openai",
        "api_key": "secret",
        "model": "gpt-4.1-mini",
    })
    assert config["chat_model"] == "gpt-4.1-mini"
    assert config["model"] == "gpt-4.1-mini"
    assert config["embedding_model"] == "text-embedding-3-small"
    assert config["base_url"] == "https://api.openai.com/v1/"


def test_custom_provider_does_not_invent_embedding_model():
    config = provider.sanitize_provider_config({
        "provider_id": "custom",
        "api_key": "secret",
        "base_url": "https://models.example.com/v1/",
        "chat_model": "research-chat",
    })
    assert config["chat_model"] == "research-chat"
    assert "embedding_model" not in config


def test_preset_provider_allows_embeddings_to_be_explicitly_disabled():
    config = provider.sanitize_provider_config({
        "provider_id": "zhipu",
        "api_key": "secret",
        "embedding_model": "",
    })
    assert "embedding_model" not in config


def test_provider_connection_test_never_returns_api_key(monkeypatch):
    class FakeCompletions:
        def create(self, **_kwargs):
            return object()

    class FakeEmbeddings:
        def create(self, **_kwargs):
            return object()

    class FakeClient:
        def __init__(self, config):
            self.model = config["chat_model"]
            self.embedding_model = config["embedding_model"]
            self.client = type("SDK", (), {})()
            self.client.chat = type("Chat", (), {"completions": FakeCompletions()})()
            self.client.embeddings = FakeEmbeddings()

    monkeypatch.setattr("llms.client.LLMClient", FakeClient)
    result = pages.test_provider(pages.ProviderTestRequest(
        provider_id="zhipu",
        api_key="do-not-return-this",
        chat_model="glm-4-flash",
        embedding_model="embedding-2",
    ))

    assert result["ok"] is True
    assert result["capabilities"] == {"chat": True, "embedding": True}
    assert "do-not-return-this" not in repr(result)


def test_provider_connection_test_explains_embedding_quota(monkeypatch):
    class FakeCompletions:
        def create(self, **_kwargs):
            return object()

    class FakeQuotaError(Exception):
        status_code = 429

    class FakeEmbeddings:
        def create(self, **_kwargs):
            raise FakeQuotaError("insufficient balance")

    class FakeClient:
        def __init__(self, config):
            self.model = config["chat_model"]
            self.embedding_model = config["embedding_model"]
            self.client = type("SDK", (), {})()
            self.client.chat = type("Chat", (), {"completions": FakeCompletions()})()
            self.client.embeddings = FakeEmbeddings()

    monkeypatch.setattr("llms.client.LLMClient", FakeClient)
    result = pages.test_provider(pages.ProviderTestRequest(
        provider_id="zhipu",
        api_key="do-not-return-this",
        chat_model="glm-4-flash",
        embedding_model="embedding-3",
    ))

    assert result["ok"] is False
    assert result["capabilities"] == {"chat": True, "embedding": False}
    assert result["error_code"] == "quota_exceeded"
    assert "额度" in result["message"]
    assert "do-not-return-this" not in repr(result)
