"""
共享依赖模块：所有路由子模块通过此模块获取公共对象，
避免循环引用。
"""
import json
import threading
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

# ━━━ 路径常量 ━━━
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # agent/
FRONTEND_DIR = BASE_DIR / "frontend"
DOCS_DIR = BASE_DIR / "documents"
SESSIONS_DIR = BASE_DIR / "sessions"

# ━━━ 收藏夹辅助 ━━━
FAVORITES_FILE = BASE_DIR / "favorites.json"


def _load_favorites() -> list[dict]:
    if FAVORITES_FILE.exists():
        try:
            return json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return []
    return []


def _save_favorites(favs: list[dict]) -> None:
    FAVORITES_FILE.write_text(json.dumps(favs, ensure_ascii=False, indent=2), encoding="utf-8")


# ━━━ 全局管理器（延迟初始化，由 web_app.py 注入）━━━━
session_mgr = None
global_kb = None
skill_mgr = None
copilot_mgr = None
_tool_registry = None

# ━━━ 运行时状态 ━━━
RUNS: Dict[str, Dict[str, Any]] = {}
RUN_LOCK = threading.Lock()


def init_deps(mgr, kb, sm, cm, tr):
    """由 web_app.py 在初始化完成后调用，注入所有全局管理器"""
    global session_mgr, global_kb, skill_mgr, copilot_mgr, _tool_registry
    session_mgr = mgr
    global_kb = kb
    skill_mgr = sm
    copilot_mgr = cm
    _tool_registry = tr

