"""Request-scoped LLM provider configuration helpers."""
from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
DEFAULT_MODEL = "glm-4-flash"
DEFAULT_EMBEDDING_MODEL = "embedding-3"

PROVIDER_CATALOG = [
    {
        "id": "zhipu",
        "name": "智谱 AI",
        "description": "当前项目默认支持，适合中文学术研究。",
        "base_url": DEFAULT_BASE_URL,
        "chat_models": ["glm-4-flash", "glm-4-plus"],
        "default_chat_model": DEFAULT_MODEL,
        "embedding_models": [DEFAULT_EMBEDDING_MODEL, "embedding-2"],
        "default_embedding_model": DEFAULT_EMBEDDING_MODEL,
        "capabilities": {"chat": True, "embedding": True},
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "description": "使用 OpenAI 官方 API。",
        "base_url": "https://api.openai.com/v1/",
        "chat_models": ["gpt-5-mini", "gpt-4.1-mini"],
        "default_chat_model": "gpt-5-mini",
        "embedding_models": ["text-embedding-3-small", "text-embedding-3-large"],
        "default_embedding_model": "text-embedding-3-small",
        "capabilities": {"chat": True, "embedding": True},
    },
    {
        "id": "custom",
        "name": "自定义 OpenAI-compatible",
        "description": "高级选项；需要自行确认聊天和向量接口兼容性。",
        "base_url": "",
        "chat_models": [],
        "default_chat_model": "",
        "embedding_models": [],
        "default_embedding_model": "",
        "capabilities": {"chat": True, "embedding": "optional"},
    },
]


def _read_field(provider: Any, name: str) -> str:
    if provider is None:
        return ""
    if isinstance(provider, dict):
        value = provider.get(name, "")
    else:
        value = getattr(provider, name, "")
    return str(value or "").strip()


def _field_was_provided(provider: Any, name: str) -> bool:
    """Tell an omitted field from an explicitly cleared optional field."""
    if provider is None:
        return False
    if isinstance(provider, dict):
        return name in provider
    fields_set = getattr(provider, "model_fields_set", None)
    if fields_set is None:
        fields_set = getattr(provider, "__fields_set__", set())
    return name in fields_set


def sanitize_provider_config(provider: Any = None) -> dict:
    """Return a minimal request-scoped config without empty values."""
    provider_id = _read_field(provider, "provider_id") or "zhipu"
    preset = next((item for item in PROVIDER_CATALOG if item["id"] == provider_id), PROVIDER_CATALOG[0])
    embedding_model = (
        _read_field(provider, "embedding_model")
        if _field_was_provided(provider, "embedding_model")
        else preset.get("default_embedding_model") or ""
    )
    config = {
        "provider_id": provider_id,
        "api_key": _read_field(provider, "api_key"),
        "base_url": _read_field(provider, "base_url") or preset.get("base_url") or DEFAULT_BASE_URL,
        "chat_model": _read_field(provider, "chat_model") or _read_field(provider, "model") or preset.get("default_chat_model") or DEFAULT_MODEL,
        "embedding_model": embedding_model,
    }
    config["model"] = config["chat_model"]
    return {key: value for key, value in config.items() if value}


def server_provider_available() -> bool:
    key = (os.getenv("ZHIPU_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key and key != "your-api-key-here")


def ensure_provider_available(provider: Any = None) -> dict:
    """Validate that either a request key or server fallback key exists."""
    config = sanitize_provider_config(provider)
    if config.get("api_key") or server_provider_available():
        return config
    raise HTTPException(
        status_code=400,
        detail=(
            "需要配置 API Key。请在页面右上角打开 API 配置并填写自己的 API Key，"
            "或由服务端管理员配置 ZHIPU_API_KEY / OPENAI_API_KEY。"
        ),
    )


def public_provider_status() -> dict:
    return {
        "server_provider_available": server_provider_available(),
        "default_base_url": DEFAULT_BASE_URL,
        "default_model": DEFAULT_MODEL,
        "default_embedding_model": DEFAULT_EMBEDDING_MODEL,
    }


def public_provider_catalog() -> dict:
    """Return public provider metadata without credentials."""
    return {"providers": PROVIDER_CATALOG, "default_provider_id": "zhipu"}
