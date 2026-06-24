"""Request-scoped LLM provider configuration helpers."""
from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
DEFAULT_MODEL = "glm-4-flash"


def _read_field(provider: Any, name: str) -> str:
    if provider is None:
        return ""
    if isinstance(provider, dict):
        value = provider.get(name, "")
    else:
        value = getattr(provider, name, "")
    return str(value or "").strip()


def sanitize_provider_config(provider: Any = None) -> dict:
    """Return a minimal request-scoped config without empty values."""
    config = {
        "api_key": _read_field(provider, "api_key"),
        "base_url": _read_field(provider, "base_url") or DEFAULT_BASE_URL,
        "model": _read_field(provider, "model") or DEFAULT_MODEL,
    }
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
    }
