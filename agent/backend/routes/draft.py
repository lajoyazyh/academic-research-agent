"""
综述管理路由 — 迭代三清理：draft → review
"""

from fastapi import APIRouter, HTTPException
from backend.session_manager import SessionManager
from config import SESSIONS_ROOT

router = APIRouter(prefix="/api/sessions", tags=["review"])

_session_mgr = SessionManager(SESSIONS_ROOT)


@router.get("/{session_id}/review")
def get_review(session_id: str, version: int = None) -> dict:
    """获取综述"""
    session = _session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    review_content = _session_mgr.get_review(session_id, version)
    return {
        "review": review_content,
        "draft": review_content,
        "review_version": session.get("review_version", 0),
        "draft_version": session.get("draft_version", session.get("review_version", 0)),
        "rewrite_count": session.get("rewrite_count", 0),
    }


@router.get("/{session_id}/draft")
def get_draft(session_id: str, version: int = None) -> dict:
    """兼容旧接口：获取综述草稿。"""
    return get_review(session_id, version)


@router.put("/{session_id}/review")
def save_review(session_id: str, payload: dict) -> dict:
    """保存综述编辑"""
    content = payload.get("review") or payload.get("content") or payload.get("draft") or ""
    if not content:
        raise HTTPException(status_code=400, detail="缺少 review 内容")

    try:
        _session_mgr.save_review(session_id, content)
        return {"message": "Success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{session_id}/draft")
def save_draft(session_id: str, payload: dict) -> dict:
    """兼容旧接口：保存综述草稿。"""
    return save_review(session_id, payload)
