"""
Copilot 全局对话会话管理器

管理 Copilot 的多轮对话历史，支持创建/切换/删除会话。
数据存储在 sessions/.copilot_sessions/ 目录下。
"""

import json
import os
import uuid
import datetime
from pathlib import Path
from typing import Optional


class CopilotSessionManager:
    """Copilot 会话管理器：CRUD + 消息归档"""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")
        self._base_dir = Path(base_dir)
        self._sessions_dir = self._base_dir / ".copilot_sessions"
        os.makedirs(self._sessions_dir, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.json"

    def _read_session(self, session_id: str) -> Optional[dict]:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return None

    def _write_session(self, session_id: str, data: dict):
        path = self._session_path(session_id)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ━━━ CRUD ━━━

    def create_session(self, title: str = "新对话") -> dict:
        """创建新的 Copilot 会话"""
        session_id = uuid.uuid4().hex[:12]
        now = datetime.datetime.now().isoformat()
        data = {
            "session_id": session_id,
            "title": title,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        self._write_session(session_id, data)
        return data

    def get_session(self, session_id: str) -> Optional[dict]:
        """获取单个会话完整数据"""
        return self._read_session(session_id)

    def list_sessions(self) -> list[dict]:
        """列出所有 Copilot 会话（摘要，不含消息）"""
        sessions = []
        for f in sorted(self._sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            data = self._read_session(f.stem)
            if data:
                sessions.append({
                    "session_id": data["session_id"],
                    "title": data.get("title", "新对话"),
                    "message_count": len(data.get("messages", [])),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                })
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def rename_session(self, session_id: str, title: str) -> bool:
        """重命名会话"""
        data = self._read_session(session_id)
        if not data:
            return False
        data["title"] = title
        data["updated_at"] = datetime.datetime.now().isoformat()
        self._write_session(session_id, data)
        return True

    def add_message(self, session_id: str, role: str, content: str, meta: dict = None) -> bool:
        """向会话添加一条消息"""
        data = self._read_session(session_id)
        if not data:
            return False
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        if meta:
            msg["meta"] = meta
        data["messages"].append(msg)
        data["updated_at"] = datetime.datetime.now().isoformat()

        # 自动生成标题：取第一条用户消息的前 30 字
        if data.get("title") == "新对话" and role == "user":
            title = content.strip()[:30]
            if len(content.strip()) > 30:
                title += "…"
            data["title"] = title

        self._write_session(session_id, data)
        return True

    def get_messages(self, session_id: str) -> list[dict]:
        """获取会话的所有消息"""
        data = self._read_session(session_id)
        if not data:
            return []
        return data.get("messages", [])

    def get_last_session_id(self) -> Optional[str]:
        """获取最近使用的会话 ID"""
        sessions = sorted(self._sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if sessions:
            return sessions[0].stem
        return None


# 全局单例
_copilot_manager: Optional[CopilotSessionManager] = None


def get_copilot_manager(base_dir: str = None) -> CopilotSessionManager:
    global _copilot_manager
    if _copilot_manager is None:
        _copilot_manager = CopilotSessionManager(base_dir)
    return _copilot_manager