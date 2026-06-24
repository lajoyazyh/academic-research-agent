"""
Academic Agent Web — FastAPI 入口

路由已按功能模块拆分到 backend/routes/ 目录：
- pages.py        页面路由、收藏夹、历史记录、PDF 服务
- session.py      Session 管理、论文管理、笔记管理
- chat.py         聊天系统（上下文窗口、意图判定、流式端点）
- conversation.py 多会话聊天管理
- draft.py        综述草稿管理
- agent.py        Agent 执行端点（规划、搜索、笔记、综述、自动模式、分析）
- admin.py        管理 API（工具注册中心、知识库、Copilot、Skills）
"""

import sys
import os
from pathlib import Path

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.session_manager import SessionManager
from backend.knowledge_base import GlobalKnowledgeBase
from backend.copilot_session_manager import get_copilot_manager
from backend.skill_manager import get_skill_manager
from core.tool_registry import get_registry
from backend.routes.deps import init_deps

# ━━━ 路径常量 ━━━
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
SESSIONS_DIR = BASE_DIR / "sessions"

# ━━━ 初始化全局管理器 ━━━
session_mgr = SessionManager(str(SESSIONS_DIR))
global_kb = GlobalKnowledgeBase(str(SESSIONS_DIR))
copilot_mgr = get_copilot_manager(str(SESSIONS_DIR))
skill_mgr = get_skill_manager(str(SESSIONS_DIR))
_tool_registry = get_registry(str(BASE_DIR / "config" / "tools.json"))

# ━━━ 注入依赖到路由模块 ━━━
init_deps(session_mgr, global_kb, skill_mgr, copilot_mgr, _tool_registry)

# ━━━ 创建 FastAPI 应用 ━━━
app = FastAPI(title="Academic Agent Web", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ━━━ 注册路由模块 ━━━
from backend.routes.pages import router as pages_router
from backend.routes.session import router as session_router
from backend.routes.chat import router as chat_router
from backend.routes.conversation import router as conversation_router
from backend.routes.draft import router as draft_router
from backend.routes.agent import router as agent_router
from backend.routes.admin import router as admin_router

app.include_router(pages_router)
app.include_router(session_router)
app.include_router(chat_router)
app.include_router(conversation_router)
app.include_router(draft_router)
app.include_router(agent_router)
app.include_router(admin_router)


if __name__ == "__main__":
    import uvicorn
    print("\n>>> Academic Agent Web 服务即将启动...")
    print(">>> 请在浏览器中打开: http://127.0.0.1:8000\n")
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)

