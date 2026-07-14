"""页面路由、收藏夹、历史记录、PDF 文件服务"""
import json
import os
import os
import datetime
import time
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .deps import (
    session_mgr, global_kb, skill_mgr, copilot_mgr, _tool_registry,
    RUNS, RUN_LOCK, SESSIONS_DIR, DOCS_DIR, FRONTEND_DIR,
    FAVORITES_FILE,
)
from backend.tenant import tenant_path
from backend.auth import auth_enabled

from fastapi.responses import HTMLResponse
from backend.provider import ensure_provider_available, public_provider_catalog, public_provider_status
from .models import ProviderConfig

router = APIRouter(tags=["pages"])

def _load_favorites() -> list[dict]:
    favorites_file = tenant_path(SESSIONS_DIR) / ".favorites.json"
    if favorites_file.exists():
        try:
            return json.loads(favorites_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return []
    return []


def _save_favorites(favs: list[dict]) -> None:
    favorites_file = tenant_path(SESSIONS_DIR) / ".favorites.json"
    favorites_file.write_text(json.dumps(favs, ensure_ascii=False, indent=2), encoding="utf-8")


def _tenant_docs_dir() -> Path:
    path = tenant_path(SESSIONS_DIR) / ".documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.get("/")
def landing():
    landing_file = FRONTEND_DIR / "market.html"
    if not landing_file.exists():
        raise HTTPException(status_code=404, detail="Landing page not found")
    return HTMLResponse(landing_file.read_text(encoding="utf-8"))

@router.get("/app")
def home():
    home_file = FRONTEND_DIR / "home.html"
    if not home_file.exists():
        raise HTTPException(status_code=404, detail="Home page not found")
    return HTMLResponse(home_file.read_text(encoding="utf-8"))


@router.get("/auth")
def auth_page():
    auth_file = FRONTEND_DIR / "auth.html"
    if not auth_file.exists():
        raise HTTPException(status_code=404, detail="Auth page not found")
    return HTMLResponse(auth_file.read_text(encoding="utf-8"))


@router.get("/app/profile")
def profile_page():
    profile_file = FRONTEND_DIR / "profile.html"
    if not profile_file.exists():
        raise HTTPException(status_code=404, detail="Profile page not found")
    return HTMLResponse(profile_file.read_text(encoding="utf-8"))

@router.get("/app/console")
def console():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Console page not found")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))

@router.get("/app/history")
def history_page():
    hist_file = FRONTEND_DIR / "history.html"
    if not hist_file.exists():
        raise HTTPException(status_code=404, detail="History page not found")
    return HTMLResponse(hist_file.read_text(encoding="utf-8"))

@router.get("/app/chat")
def chat_page():
    chat_file = FRONTEND_DIR / "chat.html"
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="Chat page not found")
    return HTMLResponse(chat_file.read_text(encoding="utf-8"))

@router.get("/app/help")
def help_page():
    help_file = FRONTEND_DIR / "help.html"
    if not help_file.exists():
        raise HTTPException(status_code=404, detail="Help page not found")
    return HTMLResponse(help_file.read_text(encoding="utf-8"))

@router.get("/app/skills")
def skills_page():
    skills_file = FRONTEND_DIR / "skills.html"
    if not skills_file.exists():
        raise HTTPException(status_code=404, detail="Skills page not found")
    return HTMLResponse(skills_file.read_text(encoding="utf-8"))

@router.get("/api/health")
def health() -> Dict[str, str]:
    persistence_enabled = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    return {
        "status": "ok",
        "auth_mode": "supabase" if auth_enabled() else "local",
        "workspace_persistence": "supabase" if persistence_enabled else "local",
    }


@router.get("/api/provider/status")
def provider_status() -> dict:
    return public_provider_status()


@router.get("/api/provider/catalog")
def provider_catalog() -> dict:
    return public_provider_catalog()


class ProviderTestRequest(ProviderConfig):
    pass


def _provider_test_error(exc: Exception, capability: str) -> tuple[str, str]:
    """Map SDK errors to safe, actionable messages without returning provider payloads."""
    error_name = exc.__class__.__name__.lower()
    status_code = getattr(exc, "status_code", None)
    error_text = str(exc).lower()

    if status_code in {401, 403} or any(term in error_name for term in ("authentication", "permission")):
        if capability == "embedding":
            return "embedding_permission_denied", "聊天模型可用，但当前 API Key 没有向量模型权限。请检查账号权限或暂时关闭向量检索。"
        return "invalid_key", "API Key 无效，或没有访问聊天模型的权限。"
    if status_code in {402, 429} or any(term in error_text for term in ("quota", "balance", "credit", "insufficient", "余额", "额度")):
        label = "向量模型" if capability == "embedding" else "聊天模型"
        return "quota_exceeded", f"{label}请求被额度或频率限制。请检查提供商余额、套餐与调用限额。"
    if "timeout" in error_name or "timed out" in error_text:
        return "timeout", "连接超时，请检查网络、Base URL 或稍后重试。"
    if status_code == 404 or "notfound" in error_name or "not found" in error_text:
        label = "向量模型" if capability == "embedding" else "聊天模型"
        return "model_not_found", f"没有找到填写的{label}，请检查模型名称与 Base URL。"
    if capability == "embedding":
        return "embedding_unavailable", "聊天模型可用，但向量模型请求失败。可改用推荐模型，或暂时关闭向量检索继续使用关键词检索。"
    return "connection_failed", "聊天模型连接失败，请检查提供商、地址和模型名称。"


@router.post("/api/provider/test")
def test_provider(payload: ProviderTestRequest) -> dict:
    """Validate BYOK chat and embedding capabilities without persisting secrets."""
    from llms.client import LLMClient

    started_at = time.perf_counter()
    config = ensure_provider_available(payload)
    capabilities = {"chat": False, "embedding": False}
    try:
        llm = LLMClient(config)
        llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            temperature=0,
            max_tokens=3,
        )
        capabilities["chat"] = True
    except Exception as exc:
        error_code, message = _provider_test_error(exc, "chat")
        return {
            "ok": False,
            "capabilities": capabilities,
            "latency_ms": round((time.perf_counter() - started_at) * 1000),
            "error_code": error_code,
            "message": message,
        }

    if config.get("embedding_model"):
        try:
            llm.client.embeddings.create(model=llm.embedding_model, input=["connection test"])
            capabilities["embedding"] = True
        except Exception as exc:
            error_code, message = _provider_test_error(exc, "embedding")
            return {
                "ok": False,
                "capabilities": capabilities,
                "latency_ms": round((time.perf_counter() - started_at) * 1000),
                "error_code": error_code,
                "message": message,
            }

    return {
        "ok": True,
        "capabilities": capabilities,
        "latency_ms": round((time.perf_counter() - started_at) * 1000),
        "message": "聊天和向量模型连接正常。" if capabilities["embedding"] else "聊天模型连接正常；当前使用关键词检索，不启用向量模型。",
    }


@router.post("/api/keywords/extract")
def extract_keywords(payload: dict) -> dict:
    """【辅助】仅提取关键词，不创建 Session"""
    from main import _build_initial_plan, _extract_keywords_from_plan
    from llms.client import LLMClient
    provider_config = ensure_provider_available(payload.get("provider"))
    llm = LLMClient(provider_config)
    plan = _build_initial_plan(llm, payload.get("topic", "").strip())
    keywords = _extract_keywords_from_plan(plan, provider_config=provider_config)
    return {"keywords": keywords, "plan": plan}


@router.get("/api/stats")
def get_stats() -> dict:
    """获取全局统计信息（首页仪表盘用）"""
    sessions = session_mgr.list_sessions()
    total_sessions = len(sessions)

    total_papers = 0
    total_notes = 0
    total_reviews = 0
    state_counts = {}
    recent_activity = None
    all_activities = []

    for s in sessions:
        total_papers += s.get("paper_count", 0)
        session_dir = tenant_path(SESSIONS_DIR) / s["session_id"]
        papers_list = None
        papers_path = session_dir / "papers" / "papers_list.json"
        if papers_path.exists():
            try:
                papers_list = json.loads(papers_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                papers_list = []
        if papers_list:
            for p in papers_list:
                if isinstance(p, dict) and p.get("notes", "").strip():
                    total_notes += 1

        draft_dir = session_dir / "draft"
        if draft_dir.exists():
            drafts = list(draft_dir.glob("*.md"))
            if drafts:
                total_reviews += len(drafts)

        st = s.get("state", "planning")
        label = s.get("state_label", "未知")
        state_counts[label] = state_counts.get(label, 0) + 1

        updated = s.get("updated_at") or s.get("created_at")
        if updated and (recent_activity is None or updated > recent_activity["time"]):
            recent_activity = {
                "time": updated,
                "topic": s.get("topic", ""),
                "state": s.get("state", "planning"),
                "state_label": label,
                "session_id": s["session_id"],
            }

        all_activities.append({
            "time": updated or "",
            "topic": s.get("topic", ""),
            "state": s.get("state", "planning"),
            "state_label": label,
            "session_id": s["session_id"],
            "paper_count": s.get("paper_count", 0),
        })

    active_count = sum(1 for s in sessions if s.get("state") not in ("complete",))
    all_activities.sort(key=lambda x: x.get("time", ""), reverse=True)
    recent_activities = all_activities[:5]

    return {
        "total_sessions": total_sessions,
        "active_sessions": active_count,
        "total_papers": total_papers,
        "total_notes": total_notes,
        "total_reviews": total_reviews,
        "state_breakdown": state_counts,
        "recent_activity": recent_activity,
        "recent_activities": recent_activities,
    }


def _summarize_failures_from_traces(traces: list[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for step in traces:
        if not isinstance(step, dict):
            continue
        error_type = str(step.get("error_type", "") or "").strip()
        if not error_type:
            continue
        summary[error_type] = summary.get(error_type, 0) + 1

@router.get("/api/agent/history")
def get_history() -> list[Dict[str, Any]]:
    docs_dir = _tenant_docs_dir()
    if not docs_dir.exists():
        return []

    favs = _load_favorites()
    fav_filenames = {f.get("filename") for f in favs}

    runs = []
    for d in docs_dir.iterdir():
        if not d.is_dir():
            continue

        review_file = d / "final_review.md"
        note_file = d / "research_notes.md"
        if review_file.exists():
            size = review_file.stat().st_size
        elif note_file.exists():
            size = note_file.stat().st_size
        else:
            size = 0

        if size > 0:
            runs.append({
                "filename": d.name,
                "size": size,
                "favorited": d.name in fav_filenames,
            })

    runs.sort(key=lambda x: x["filename"], reverse=True)
    return runs


@router.get("/api/agent/history/{filename}")
def get_history_detail(filename: str) -> Dict[str, Any]:
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    run_dir = _tenant_docs_dir() / filename
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    review_file = run_dir / "final_review.md"
    note_file = run_dir / "research_notes.md"
    papers_dir = run_dir / "papers"

    content = ""
    writer_res = ""
    res_notes = ""
    papers = []

    if papers_dir.exists():
        for p in papers_dir.glob("*.pdf"):
            papers.append(p.name)

    if review_file.exists():
        writer_res = review_file.read_text(encoding="utf-8")
        content += writer_res
    if note_file.exists():
        res_notes = note_file.read_text(encoding="utf-8")
        content += "\n\n---\n\n## 📔 原始研究笔记 (Research Notes)\n\n" + res_notes

    return {
        "filename": filename,
        "content": content,
        "writer_result": writer_res,
        "researcher_result": res_notes,
        "papers": papers,
    }


@router.delete("/api/agent/history/{filename}")
def delete_history(filename: str) -> dict:
    """删除历史综述记录"""
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    run_dir = _tenant_docs_dir() / filename
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="记录不存在")
    import shutil
    shutil.rmtree(run_dir)
    # 同时清理收藏夹中的记录
    favs = _load_favorites()
    favs = [f for f in favs if f.get("filename") != filename]
    _save_favorites(favs)
    return {"status": "deleted", "filename": filename}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/favorites")
def get_favorites() -> list[dict]:
    """获取收藏夹列表"""
    favs = _load_favorites()
    # 补充文件大小信息
    enriched = []
    for fav in favs:
        filename = fav.get("filename", "")
        run_dir = _tenant_docs_dir() / filename
        size = 0
        if run_dir.exists():
            review_file = run_dir / "final_review.md"
            if review_file.exists():
                size = review_file.stat().st_size
            else:
                note_file = run_dir / "research_notes.md"
                if note_file.exists():
                    size = note_file.stat().st_size
        enriched.append({
            "filename": filename,
            "topic": fav.get("topic", filename),
            "size": size,
            "added_at": fav.get("added_at", ""),
        })
    return enriched


@router.post("/api/favorites")
def add_favorite(payload: dict) -> dict:
    """加入收藏夹"""
    filename = payload.get("filename", "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename 不能为空")
    topic = payload.get("topic", filename).strip()
    
    favs = _load_favorites()
    # 去重
    if not any(f.get("filename") == filename for f in favs):
        favs.append({
            "filename": filename,
            "topic": topic,
            "added_at": datetime.datetime.now().isoformat(),
        })
        _save_favorites(favs)
    
    return {"status": "favorited", "count": len(favs)}


@router.delete("/api/favorites/{filename}")
def remove_favorite(filename: str) -> dict:
    """取消收藏"""
    favs = _load_favorites()
    favs = [f for f in favs if f.get("filename") != filename]
    _save_favorites(favs)
    return {"status": "unfavorited", "count": len(favs)}


@router.get("/api/agent/document/{filename}/papers/{pdf_name:path}")
def get_pdf(filename: str, pdf_name: str) -> FileResponse:
    if "/" in filename or "\\" in filename or "/" in pdf_name or "\\" in pdf_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # 先检查 Session 目录（current version新路径）
    pdf_path = tenant_path(SESSIONS_DIR) / filename / "papers" / pdf_name
    if pdf_path.exists():
        return FileResponse(pdf_path, media_type="application/pdf")

    # Compatibility for uploads created before files were normalized to
    # <paper_id>.pdf. Their original filename may still be available in paper
    # metadata. Never scan or expose another session/user directory.
    requested_paper_id = pdf_name[:-4] if pdf_name.lower().endswith(".pdf") else pdf_name
    for paper in session_mgr.get_papers(filename):
        if paper.get("paper_id") != requested_paper_id:
            continue
        legacy_name = paper.get("pdf_filename") or paper.get("original_filename")
        if not legacy_name and str(paper.get("title", "")).lower().endswith(".pdf"):
            legacy_name = paper.get("title")
        if legacy_name and Path(str(legacy_name)).name == legacy_name:
            legacy_path = tenant_path(SESSIONS_DIR) / filename / "papers" / legacy_name
            if legacy_path.exists():
                return FileResponse(legacy_path, media_type="application/pdf")
        break

    raise HTTPException(status_code=404, detail="PDF not found")
