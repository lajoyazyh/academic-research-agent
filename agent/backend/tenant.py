"""Request-scoped tenant helpers used by the public multi-user deployment."""
from __future__ import annotations

import contextvars
import hashlib
from pathlib import Path


_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "academic_agent_user_id", default="local"
)


def set_current_user(user_id: str):
    return _current_user_id.set(user_id or "local")


def reset_current_user(token) -> None:
    _current_user_id.reset(token)


def get_current_user() -> str:
    return _current_user_id.get()


def tenant_key(user_id: str | None = None) -> str:
    value = user_id or get_current_user()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def tenant_path(base: str | Path, user_id: str | None = None) -> Path:
    """Keep local mode backwards compatible; isolate authenticated users."""
    root = Path(base)
    value = user_id or get_current_user()
    if value == "local":
        return root
    path = root / ".users" / tenant_key(value)
    path.mkdir(parents=True, exist_ok=True)
    return path
