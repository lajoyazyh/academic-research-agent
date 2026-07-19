"""Durable, tenant-scoped metadata for long-running research jobs.

The actual model key deliberately never enters this store.  Live workers may
still keep an in-memory cancellation flag, while everything required to show,
audit, and retry an interrupted run is persisted with the user's workspace.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from backend.tenant import tenant_path


TERMINAL_STATUSES = {"done", "partial", "error", "cancelled", "interrupted"}
SECRET_FIELDS = {"api_key", "x_github_token", "github_token", "authorization"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _safe_value(value: Any) -> Any:
    """Return JSON-safe data with credentials and process-only objects removed."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in SECRET_FIELDS or key.startswith("_"):
                continue
            result[key] = _safe_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class PersistentRunStore:
    """Small filesystem-backed run ledger compatible with local and cloud mode."""

    def __init__(self, sessions_root: str | Path):
        self.sessions_root = Path(sessions_root)
        self._lock = threading.RLock()

    @property
    def root(self) -> Path:
        path = tenant_path(self.sessions_root) / ".runs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _session_dir(self, session_id: str) -> Path:
        safe_id = Path(session_id).name
        path = self.root / safe_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _path(self, session_id: str, run_id: str) -> Path:
        return self._session_dir(session_id) / f"{Path(run_id).name}.json"

    def _write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(json.dumps(_safe_value(data), ensure_ascii=False, indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def create(self, session_id: str, kind: str, payload: dict | None = None) -> dict:
        now = _now()
        run_id = f"run_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        run = {
            "run_id": run_id,
            "session_id": session_id,
            "kind": kind,
            "status": "running",
            "phase": "queued",
            "message": "",
            "progress": {},
            "checkpoint": "queued",
            "retryable": False,
            "payload": _safe_value(payload or {}),
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._write(self._path(session_id, run_id), run)
        return run

    def update(self, session_id: str, run_id: str, **changes: Any) -> dict:
        with self._lock:
            run = self.get(session_id, run_id) or {
                "run_id": run_id,
                "session_id": session_id,
                "kind": "unknown",
                "created_at": _now(),
            }
            run.update(_safe_value(changes))
            run["updated_at"] = _now()
            self._write(self._path(session_id, run_id), run)
            return run

    def get(self, session_id: str, run_id: str) -> dict | None:
        path = self._path(session_id, run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list(self, session_id: str, limit: int = 30) -> list[dict]:
        runs = []
        for path in self._session_dir(session_id).glob("run_*.json"):
            try:
                runs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        runs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return runs[: max(1, min(limit, 100))]

    def latest(self, session_id: str) -> dict | None:
        runs = self.list(session_id, limit=1)
        return runs[0] if runs else None

    def mark_interrupted(self, session_id: str, run_id: str) -> dict | None:
        run = self.get(session_id, run_id)
        if not run or run.get("status") != "running":
            return run
        language = str((run.get("payload") or {}).get("language") or "zh-CN")
        message = (
            "The service restarted while this job was running. Reconnect the model and retry from the saved checkpoint."
            if language == "en"
            else "服务在任务执行期间发生重启。请重新连接模型，并从已保存检查点重试。"
        )
        return self.update(
            session_id,
            run_id,
            status="interrupted",
            message=message,
            retryable=True,
            error_code="run_interrupted",
        )
