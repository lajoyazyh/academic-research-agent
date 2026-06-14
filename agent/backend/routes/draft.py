"""综述草稿管理 API"""
import json
import os
import datetime
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


router = APIRouter(prefix="/api/sessions", tags=["draft"])

@router.get("/{session_id}/draft")
def get_draft(session_id: str, version: int = None) -> dict:
    """获取综述草稿"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    draft_content = session_mgr.get_draft(session_id, version)
    return {
        "draft": draft_content,
        "draft_version": session.get("draft_version", 0),
        "rewrite_count": session.get("rewrite_count", 0),
    }

@router.put("/{session_id}/draft")
def save_draft(session_id: str, payload: dict) -> dict:
    """保存综述草稿编辑"""
    content = payload.get("content", "")
    try:
        session_mgr.save_draft(session_id, content)
        return {"message": "Success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
