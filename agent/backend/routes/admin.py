"""管理 API：工具注册中心、全局知识库、Copilot 会话、Skills 管理"""
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
from functools import lru_cache
from llms.client import LLMClient


@lru_cache(maxsize=1)
def _get_chat_intent_llm() -> LLMClient:
    return LLMClient()


router = APIRouter(tags=["admin"])

# 工具管理 API — 直接使用 deps 中已初始化的 _tool_registry
# ═══════════════════════════════════════════


@router.get("/api/tools")
def list_tools() -> dict:
    """获取所有工具列表（含启用/禁用状态和配置）"""
    all_tools = _tool_registry.get_all()
    return {
        "tools": [t.to_dict() for t in all_tools],
        "enabled_count": len(_tool_registry.get_enabled()),
        "total_count": len(all_tools),
    }


@router.put("/api/tools/{tool_name}/toggle")
def toggle_tool(tool_name: str, payload: dict) -> dict:
    """启用或禁用某个工具"""
    enabled = payload.get("enabled", True)
    success = _tool_registry.set_enabled(tool_name, enabled)
    if not success:
        raise HTTPException(status_code=404, detail=f"工具 '{tool_name}' 不存在")
    return {"tool_name": tool_name, "enabled": enabled, "message": "已更新"}


@router.put("/api/tools/batch-toggle")
def batch_toggle_tools(payload: dict) -> dict:
    """批量启用/禁用工具"""
    enabled_map = payload.get("tools", {})
    result = _tool_registry.batch_set_enabled(enabled_map)
    return {"result": result, "message": "批量更新完成"}


@router.put("/api/tools/{tool_name}/config")
def update_tool_config(tool_name: str, payload: dict) -> dict:
    """更新工具的配置参数"""
    key = payload.get("key")
    value = payload.get("value")
    if not key:
        raise HTTPException(status_code=400, detail="缺少 'key' 参数")
    success = _tool_registry.set_config(tool_name, key, value)
    if not success:
        raise HTTPException(status_code=404, detail=f"工具 '{tool_name}' 不存在")
    return {"tool_name": tool_name, "key": key, "value": value, "message": "配置已更新"}


@router.post("/api/tools/reset")
def reset_tools() -> dict:
    """重置工具配置为默认值"""
    _tool_registry.reset_to_defaults()
    return {"message": "已重置为默认配置", "tools": [t.to_dict() for t in _tool_registry.get_all()]}


#  全局知识库 API（跨 Session 知识共享）
# ═══════════════════════════════════════════

@router.get("/api/knowledge/stats")
def get_knowledge_stats() -> dict:
    """获取全局知识库统计信息"""
    return global_kb.get_stats()


@router.get("/api/knowledge/sessions")
def get_knowledge_sessions() -> dict:
    """获取所有 Session 摘要（供 Copilot 上下文选择）"""
    summaries = global_kb.get_session_summaries()
    return {"sessions": summaries, "count": len(summaries)}


@router.post("/api/knowledge/search")
def search_knowledge(payload: dict) -> dict:
    """跨 Session 全局检索"""
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")
    top_k = int(payload.get("top_k", 8))
    results = global_kb.search(query, top_k=min(top_k, 20))
    return {
        "query": query,
        "results": results,
        "count": len(results),
    }


@router.post("/api/knowledge/chat")
def global_chat(payload: dict) -> dict:
    """全局 Copilot 对话：跨 Session 知识问答，支持多会话历史"""
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    copilot_session_id = (payload.get("copilot_session_id") or "").strip()
    raw_session_ids = payload.get("session_ids", None)
    session_ids = None
    if raw_session_ids is not None:
        if not isinstance(raw_session_ids, list):
            raise HTTPException(status_code=400, detail="session_ids 必须是数组")
        session_ids = [str(sid).strip() for sid in raw_session_ids if str(sid).strip()]

    # 1. 全局检索
    search_results = global_kb.search(message, top_k=8, session_ids=session_ids)

    # 2. 构建 RAG 上下文
    rag_context = ""
    if search_results:
        parts = []
        for r in search_results:
            rtype = r.get("type", "")
            label = {"paper_abstract": "📄", "note": "📝", "draft": "📋"}.get(rtype, "📌")
            parts.append(
                f"{label} [{r.get('topic', '')}] {r.get('text', '')[:800]}"
            )
        rag_context = "\n\n---\n\n".join(parts)

    # 3. 获取统计信息作为补充上下文
    stats = global_kb.get_stats()

    system_prompt = """你是一个学术研究 Copilot 助手，帮助用户了解和管理他们的所有研究项目。

你的能力：
- 基于所有 Session 的论文、笔记、综述草稿回答用户问题
- 帮助用户发现不同项目之间的关联
- 提供研究进度概览和建议

要求：
- 基于检索到的资料回答，标注信息来源（Session 主题 + 内容类型）
- 如果用户问的是全局概况，结合统计信息回答
- 回答简洁、有条理，默认 3-6 句
- 如果资料不足以回答，诚实说明并给出建议
"""

    user_prompt = f"""全局知识库统计：
- 总 Session 数：{stats.get('session_count', 0)}
- 总论文数：{stats.get('total_papers', 0)}
- 总笔记字数：{stats.get('total_notes_chars', 0)}
- 总综述草稿数：{stats.get('total_drafts', 0)}

【知识检索范围】
{('全部 Session' if session_ids is None else '选中的 Session：' + ', '.join(session_ids))}

【跨 Session 检索到的相关资料】
{rag_context or '（未找到相关资料）'}

用户问题：{message}

请基于以上资料回答。如引用资料，请标注来源（如"[Session主题] 的笔记中提到..."）。"""

    try:
        llm = _get_chat_intent_llm()
        reply = llm.chat(system_prompt, user_prompt, []).strip()
    except Exception as e:
        reply = f"抱歉，生成回答时出错：{str(e)}"

    # 4. 保存到 Copilot 会话历史
    if copilot_session_id:
        try:
            copilot_mgr.add_message(copilot_session_id, "user", message)
            copilot_mgr.add_message(copilot_session_id, "assistant", reply,
                                    meta={
                                        "search_count": len(search_results),
                                        "has_rag": bool(rag_context),
                                        "session_ids": session_ids,
                                    })
        except Exception:
            pass  # 历史记录保存失败不阻断回复

    return {
        "reply": reply,
        "search_count": len(search_results),
        "has_rag": bool(rag_context),
        "copilot_session_id": copilot_session_id or None,
        "session_ids": session_ids,
    }


@router.post("/api/knowledge/rebuild")
def rebuild_knowledge() -> dict:
    """强制重建全局知识库索引"""
    stats = global_kb.build_index(force=True)
    return {"message": "索引已重建", "stats": stats}


@router.get("/api/copilot/context/stats")
def get_copilot_context_stats(copilot_session_id: str) -> dict:
    """获取 Copilot 对话的上下文窗口使用统计"""
    messages = copilot_mgr.get_messages(copilot_session_id) or []
    total_chars = sum(len(m.get("content", "")) for m in messages)
    estimated_tokens = int(total_chars / 2.5)
    message_count = len(messages)
    round_count = message_count // 2
    max_tokens = 40000

    return {
        "copilot_session_id": copilot_session_id,
        "message_count": message_count,
        "round_count": round_count,
        "total_chars": total_chars,
        "estimated_tokens": estimated_tokens,
        "max_tokens": max_tokens,
        "usage_percent": min(100, round(estimated_tokens / max_tokens * 100, 1)),
    }


# ═══════════════════════════════════════════
#  Copilot 会话管理 API（多会话历史记录）
# ═══════════════════════════════════════════
# copilot_mgr 和 skill_mgr 由 web_app.py 初始化，通过 deps.py 注入


@router.get("/api/copilot/sessions")
def list_copilot_sessions() -> dict:
    """列出所有 Copilot 会话"""
    sessions = copilot_mgr.list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@router.post("/api/copilot/sessions")
def create_copilot_session(payload: dict = None) -> dict:
    """创建新的 Copilot 会话"""
    title = (payload or {}).get("title", "新对话")
    session = copilot_mgr.create_session(title)
    return session


@router.get("/api/copilot/sessions/{copilot_session_id}")
def get_copilot_session(copilot_session_id: str) -> dict:
    """获取 Copilot 会话完整数据（含消息历史）"""
    session = copilot_mgr.get_session(copilot_session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Copilot 会话 {copilot_session_id} 不存在")
    return session


@router.delete("/api/copilot/sessions/{copilot_session_id}")
def delete_copilot_session(copilot_session_id: str) -> dict:
    """删除 Copilot 会话"""
    if not copilot_mgr.delete_session(copilot_session_id):
        raise HTTPException(status_code=404, detail=f"Copilot 会话 {copilot_session_id} 不存在")
    return {"status": "deleted", "session_id": copilot_session_id}


@router.put("/api/copilot/sessions/{copilot_session_id}/title")
def rename_copilot_session(copilot_session_id: str, payload: dict) -> dict:
    """重命名 Copilot 会话"""
    title = (payload or {}).get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title 不能为空")
    if not copilot_mgr.rename_session(copilot_session_id, title):
        raise HTTPException(status_code=404, detail=f"Copilot 会话 {copilot_session_id} 不存在")
    return {"status": "renamed", "session_id": copilot_session_id, "title": title}


@router.get("/api/copilot/sessions/{copilot_session_id}/messages")
def get_copilot_messages(copilot_session_id: str) -> dict:
    """获取 Copilot 会话的所有消息"""
    messages = copilot_mgr.get_messages(copilot_session_id)
    return {"session_id": copilot_session_id, "messages": messages, "count": len(messages)}


# ═══════════════════════════════════════════
#  Skills 管理 API（迭代三扩展：用户自定义 Agent 行为策略）
# ═══════════════════════════════════════════

@router.get("/api/skills")
def list_skills(skill_type: str = None) -> dict:
    """获取 Skills 列表，支持 ?type=search|notes|write 过滤"""
    if skill_type and skill_type not in {"search", "notes", "write"}:
        raise HTTPException(status_code=400, detail=f"无效的 type 参数: {skill_type}")
    skills = skill_mgr.list_skills(skill_type=skill_type)
    return {"skills": skills, "count": len(skills)}


@router.post("/api/skills")
def create_skill(payload: dict) -> dict:
    """创建新 Skill"""
    title = str(payload.get("title", "")).strip()
    skill_type = str(payload.get("type", "")).strip()
    content = str(payload.get("content", "")).strip()

    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    if skill_type not in {"search", "notes", "write"}:
        raise HTTPException(status_code=400, detail=f"无效的 skill 类型: {skill_type}")
    if not content:
        raise HTTPException(status_code=400, detail="Skill 内容不能为空")

    try:
        skill = skill_mgr.create_skill(title, skill_type, content)
        return skill
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建 Skill 失败: {str(e)}")


# ━━━ 固定路径路由必须在 {skill_id} 之前注册，避免 FastAPI 将 "defaults"/"usage" 当作 skill_id ━━━

@router.get("/api/skills/defaults")
def get_default_skills() -> dict:
    """获取各阶段的默认 Skill 内容（留空时使用的内置提示词）"""
    return {"defaults": skill_mgr.get_defaults()}


@router.get("/api/skills/{skill_id}")
def get_skill(skill_id: str) -> dict:
    """获取单个 Skill 完整数据"""
    skill = skill_mgr.get_skill(skill_id)
    if not skill or skill.get("deleted"):
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} 不存在")
    return skill


@router.put("/api/skills/{skill_id}")
def update_skill(skill_id: str, payload: dict) -> dict:
    """更新 Skill 标题或内容"""
    title = payload.get("title")
    content = payload.get("content")

    try:
        skill = skill_mgr.update_skill(skill_id, title=title, content=content)
        return skill
    except ValueError as e:
        raise HTTPException(status_code=400 if "不存在" in str(e) else 409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新 Skill 失败: {str(e)}")


@router.delete("/api/skills/{skill_id}")
def delete_skill(skill_id: str, hard: bool = False) -> dict:
    """删除 Skill（默认软删除）"""
    if not skill_mgr.delete_skill(skill_id, soft=not hard):
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} 不存在")
    return {"status": "deleted", "skill_id": skill_id}


@router.get("/api/skills/{skill_id}/usage")
def get_skill_usage(skill_id: str) -> dict:
    """获取引用该 Skill 的 Session 列表"""
    skill = skill_mgr.get_skill(skill_id)
    if not skill or skill.get("deleted"):
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} 不存在")
    sessions = skill_mgr.get_skill_usage(skill_id)
    return {"skill_id": skill_id, "sessions": sessions, "count": len(sessions)}

