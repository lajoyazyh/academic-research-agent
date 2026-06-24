"""多会话聊天管理 API"""
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


router = APIRouter(prefix="/api/sessions", tags=["conversations"])

# ━━━━━ 多会话聊天管理 API ━━━━━

@router.get("/{session_id}/conversations")
def list_conversations(session_id: str) -> dict:
    """列出 Session 下所有聊天会话"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    conversations = session_mgr.list_conversations(session_id)
    return {"session_id": session_id, "conversations": conversations}


@router.post("/{session_id}/conversations")
def create_conversation(session_id: str, payload: dict = None) -> dict:
    """创建新的聊天会话"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    title = (payload or {}).get("title", "")
    conv = session_mgr.create_conversation(session_id, title)
    return conv


@router.get("/{session_id}/conversations/{conv_id}/messages")
def get_conversation_messages(session_id: str, conv_id: str) -> dict:
    """获取某个聊天会话的所有消息"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    messages = session_mgr.get_conversation_messages(session_id, conv_id)
    return {"session_id": session_id, "conv_id": conv_id, "messages": messages}


@router.delete("/{session_id}/conversations/{conv_id}")
def delete_conversation(session_id: str, conv_id: str) -> dict:
    """删除聊天会话"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    conversations = session_mgr.list_conversations(session_id)
    if len(conversations) <= 1:
        raise HTTPException(status_code=400, detail="至少保留一个聊天会话")
    session_mgr.delete_conversation(session_id, conv_id)
    return {"message": "已删除"}
