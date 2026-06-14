"""聊天系统：上下文窗口管理、意图判定、流式端点"""
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

import threading
from functools import lru_cache
from llms.client import LLMClient
from utils.parser import extract_json
from backend.session_manager import STATE_LABELS
from .agent import revise_notes_phase, run_write_phase
from .models import (
    ChatMessageRequest, ChatMessageResponse, RunPhaseRequest,
    ReviseNotesRequest, SaveFeedbackRequest,
)


@lru_cache(maxsize=1)
def _get_chat_intent_llm() -> LLMClient:
    return LLMClient()


router = APIRouter(tags=["chat"])

# ━━━ 上下文窗口管理 ━━━
# glm-4-flash 上下文窗口约 128K tokens，保守估计 1 token ≈ 2 字符（中英文混合）
MAX_CONTEXT_CHARS = 80000  # 约 40K tokens，留一半给 system prompt + 回复
MAX_RAG_CHARS = 30000       # 检索结果最多占用
MAX_HISTORY_CHARS = 15000   # 对话历史最多占用
MAX_NOTES_CHARS = 20000     # 笔记/草稿最多占用


def _truncate_text(text: str, max_chars: int, tail: str = "\n... (内容过长，已截断)") -> str:
    """按字符数截断文本，优先保留开头和结尾。"""
    if not text or len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + tail + text[-half:]


def _manage_context_window(
    current_notes: str,
    current_review: str,
    current_abstract: str,
    rag_context: str,
    history_context: str,
    message: str,
) -> dict[str, str]:
    """智能管理上下文窗口，按优先级分配字符配额。

    优先级：用户消息 > 检索结果 > 对话历史 > 笔记/草稿 > 摘要
    """
    # 1. 用户消息不截断（通常很短）
    message_chars = len(message)

    # 2. 检索结果优先保留（与问题最相关）
    rag_context = _truncate_text(rag_context, MAX_RAG_CHARS)

    # 3. 对话历史
    history_context = _truncate_text(history_context, MAX_HISTORY_CHARS)

    # 4. 笔记和草稿共享剩余配额
    remaining = MAX_CONTEXT_CHARS - message_chars - len(rag_context) - len(history_context) - 2000  # 2000 留给 system prompt 等
    notes_quota = min(MAX_NOTES_CHARS, max(5000, remaining // 2))
    review_quota = min(MAX_NOTES_CHARS, max(5000, remaining // 2))

    current_notes = _truncate_text(current_notes, notes_quota)
    current_review = _truncate_text(current_review, review_quota)
    current_abstract = _truncate_text(current_abstract, 3000)

    return {
        "notes": current_notes,
        "review": current_review,
        "abstract": current_abstract,
        "rag": rag_context,
        "history": history_context,
    }


def _build_chat_answer(session: dict, message: str, view_mode: str, current_paper_id: str | None = None, conv_id: str = "default") -> dict[str, str]:
    paper = None
    if current_paper_id:
        for item in session.get("papers", []):
            if item.get("paper_id") == current_paper_id:
                paper = item
                break
    if paper is None:
        papers = session.get("papers", [])
        paper = papers[0] if papers else None

    current_name = (paper or {}).get("title") or (paper or {}).get("paper_id") or session.get("topic", "当前主题")
    current_abstract = (paper or {}).get("abstract", "") or (paper or {}).get("summary", "") or ""
    current_notes = session.get("notes", "") or ""
    current_review = session.get("review", "") or ""

    accepted_names = "、".join(
        [p.get("title") or p.get("paper_id", "") for p in session.get("papers", []) if p.get("status") == "accepted"]
    )
    if(view_mode == "review"):
        accepted_names = "review模式下暂不提供已选论文列表"


    # ━━━ 迭代三 RAG 升级：迭代式混合检索 PDF 原文段落 ━━━
    rag_context = ""
    _sid = session.get("session_id", "")
    if _sid:
        try:
            from tools.retriever import iterative_search  # noqa
            _papers_dir = str(SESSIONS_DIR / _sid / "papers")
            passages = iterative_search(_sid, _papers_dir, message, top_k=10, max_rounds=2)
            if passages:
                rag_parts = []
                for p in passages:
                    paper_id = p.get("paper_id", "")
                    page = p.get("page", "?")
                    title = ""
                    for pp in session.get("papers", []):
                        if pp.get("paper_id") == paper_id:
                            title = pp.get("title", "")[:60]
                            break
                    source = f"{title or paper_id} (第{page}页)"
                    rag_parts.append(f"【{source}】\n{p['text']}")
                rag_context = "\n\n---\n\n".join(rag_parts)
        except Exception:
            pass
    
    # 检查是否有 PDF 文件
    has_pdfs = _sid and (SESSIONS_DIR / _sid / "papers").exists() and any((SESSIONS_DIR / _sid / "papers").glob("*.pdf"))

    # ━━━ 阶段一：多轮对话记忆 ━━━
    history_context = ""
    if _sid:
        try:
            all_messages = session_mgr.get_conversation_messages(_sid, conv_id)
            # 取最近 6 轮对话（12 条消息），排除当前正在发送的这一轮
            recent = all_messages[:-1] if len(all_messages) > 1 else []
            recent = recent[-12:]  # 最多 6 轮
            if recent:
                history_lines = []
                for msg in recent:
                    role_label = "用户" if msg.get("role") == "user" else "助手"
                    history_lines.append(f"{role_label}：{msg.get('text', '')}")
                history_context = "\n".join(history_lines)
        except Exception:
            pass

    system_prompt = """你是一个严谨、简洁的中文学术助理。
你的任务是围绕当前论文、笔记或综述草稿，直接回答用户的问题。

要求：
- 只能基于给定上下文回答，不要编造未提供的信息。
- 如果有"检索到的原文段落"，优先引用原文内容回答问题，并标注来源（论文标题+页码）。
- 如果上下文不足，明确说明无法从当前材料判断，并给出下一步建议。
- 用户是在提问或解释时，优先回答问题本身，不要输出修改入口提示。
- 回答要自然、直接、简洁，默认 3-6 句；如果用户要求展开，可以适度加长。
- 如果用户明显在请求修改，应该由外层路由处理，这里只负责普通问答。
- 如果对话历史中有相关上下文，请结合历史理解用户的追问和指代（如"它"、"这个"、"那篇"等）。
"""

    # ━━━ 智能上下文窗口管理 ━━━
    ctx = _manage_context_window(
        current_notes=current_notes,
        current_review=current_review,
        current_abstract=current_abstract,
        rag_context=rag_context,
        history_context=history_context,
        message=message,
    )

    user_prompt = f"""会话主题：{session.get('topic', '')}
当前视图模式：{view_mode}
当前论文：{current_name}
已选论文：{accepted_names or '暂无'}

当前论文摘要（如有）：
{ctx['abstract'] or '无'}

当前研究笔记（如有）：
{ctx['notes'] or '无'}

当前综述草稿（如有）：
{ctx['review'] or '无'}

【从论文 PDF 中检索到的原文段落】
{ctx['rag'] or '（无相关检索结果）'}

【对话历史（最近几轮）】
{ctx['history'] or '（这是对话的第一条消息）'}

用户问题：{message}

请基于以上资料（特别是检索到的原文段落和对话历史）回答问题。如引用原文，请标注来源。注意理解对话历史中的指代关系。"""

    try:
        answer = _get_chat_intent_llm().chat(system_prompt, user_prompt, []).strip()
        if answer:
            if rag_context:
                rag_status = "used"
                rag_count = len(rag_context.split("---"))
            elif not has_pdfs:
                rag_status = "no_pdfs"
                rag_count = 0
            else:
                rag_status = "no_results"
                rag_count = 0
            note = "基于论文原文生成回答" if rag_context else f"基于当前{'综述' if view_mode == 'review' else '论文'}上下文生成回答"
            return {"reply": answer, "note": note, "rag_status": rag_status, "rag_count": rag_count}
    except Exception:
        pass

    return _build_chat_reply(session, view_mode, current_paper_id)


def _parse_explicit_chat_revision(message: str, view_mode: str) -> dict[str, str] | None:
    text = (message or "").strip()
    if not text:
        return None

    if text.startswith("/修订"):
        content = re.sub(r"^/修订\s*", "", text).strip()
        if not content:
            return None
        target_match = re.match(r"^(笔记|综述|report|review)\s+([\s\S]+)$", content, flags=re.IGNORECASE)
        if target_match:
            raw_target = target_match.group(1).lower()
            target = "review" if raw_target in ("综述", "review") else "report"
            return target, target_match.group(2).strip()
        return {"target": "review" if view_mode == "review" else "report", "feedback": content, "source": "explicit"}

    return None


# ━━━ 轻量级意图预判（关键词规则，避免不必要的 LLM 调用）━━━━
_REVISE_KEYWORDS = [
    "修改", "改写", "重写", "删除", "删掉", "去掉", "补充", "添加", "增加",
    "调整", "压缩", "精简", "扩展", "扩充", "重组", "合并", "拆分",
    "改一下", "改改", "改一改", "换成", "替换", "改成",
    "revise", "rewrite", "modify", "change", "update", "delete", "remove",
    "add", "insert", "expand", "compress", "reorganize",
]
_QUESTION_KEYWORDS = [
    "什么是", "是什么", "为什么", "如何", "怎么", "怎样", "什么意思",
    "解释", "说明", "介绍", "区别", "对比", "比较", "有哪些",
    "what", "why", "how", "explain", "describe", "difference",
    "?", "？", "吗", "呢", "吧",
]


def _quick_intent_check(message: str) -> str | None:
    """轻量级关键词预判，返回 'revise' | 'chat' | None（不确定时返回 None，走 LLM）"""
    text = message.strip().lower()
    # 强修改意图：以 /修订 开头（已被 _parse_explicit_chat_revision 处理）
    # 这里只做辅助判断
    revise_hits = sum(1 for kw in _REVISE_KEYWORDS if kw in text)
    question_hits = sum(1 for kw in _QUESTION_KEYWORDS if kw in text)
    if revise_hits >= 2 and question_hits == 0:
        return "revise"
    if question_hits >= 1 and revise_hits == 0:
        return "chat"
    return None  # 不确定，走 LLM


def _infer_chat_revision_ai(session: dict, message: str, view_mode: str, current_paper_id: str | None) -> dict[str, str] | None:
    text = (message or "").strip()
    if not text:
        return None

    # ━━━ 轻量级预判：如果关键词规则能明确判断，跳过 LLM 调用 ━━━
    quick = _quick_intent_check(text)
    if quick == "chat":
        return None  # 明确是提问，不走修订流程
    if quick == "revise":
        # 关键词明确是修改意图，直接构造修订结果
        target = "review" if view_mode == "review" else "report"
        return {
            "intent": "revise",
            "target": target,
            "feedback": text,
            "reason": "关键词匹配：检测到明确的修改意图",
            "source": "keyword",
        }

    # ━━━ 关键词不确定时，走 LLM 意图分类 ━━━
    paper_title = ""
    if current_paper_id:
        for paper in session.get("papers", []):
            if paper.get("paper_id") == current_paper_id:
                paper_title = paper.get("title", "") or paper.get("paper_id", "")
                break

    system_prompt = """你是一个对用户自然语言消息进行意图分类的助手。
你的任务不是回答问题，也不是直接修改内容，而是判断这条消息是否在请求修改当前笔记或综述。

请只输出严格 JSON，不要输出解释、不要输出 Markdown 代码块。
JSON 格式如下：
{
  "intent": "revise" | "chat" | "clarify",
  "target": "report" | "review" | "none",
  "confidence": 0.0-1.0,
  "reason": "一句简短理由",
  "feedback": "若 intent=revise，则提炼出的修改意见；否则为空字符串"
}

判定规则：
- 只有当用户明显在要求改写、删除、补充、压缩、重组、重写当前内容时，才判断为 revise。
- 如果用户是在提问、解释、讨论内容含义，则判断为 chat。
- 如果用户表达模糊，无法确定是否要修改，则判断为 clarify。
- target 只在 revise 时填写 report 或 review；其他情况填 none。
"""

    user_prompt = f"""会话上下文：
- 当前视图模式：{view_mode}
- 当前会话状态：{session.get('state', '')}
- 当前论文标题：{paper_title or '无'}
- 用户消息：{text}

请进行意图分类，并严格按 JSON 输出。"""

    try:
        raw_response = _get_chat_intent_llm().chat(system_prompt, user_prompt, [])
        result = extract_json(raw_response)
    except Exception:
        # LLM 调用失败时，降级为普通问答
        return None

    intent = str(result.get("intent", "chat")).strip().lower()
    target = str(result.get("target", "none")).strip().lower()
    confidence = result.get("confidence", 0)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0

    feedback = str(result.get("feedback", "")).strip()
    reason = str(result.get("reason", "")).strip()

    if intent == "revise":
        if target not in {"report", "review"}:
            target = "review" if view_mode == "review" else "report"
        if confidence_value < 0.6:
            return {"intent": "clarify", "target": "none", "feedback": "", "reason": reason}
        return {
            "intent": "revise",
            "target": target,
            "feedback": feedback or text,
            "reason": reason,
            "source": "ai",
        }

    if intent == "clarify":
        return {"intent": "clarify", "target": "none", "feedback": "", "reason": reason, "source": "ai"}

    return None


def _save_chat_exchange(session_id: str, user_msg: str, reply: str, note: str, view_mode: str, conv_id: str = "default") -> None:
    """保存一轮对话（用户消息 + AI 回复）到指定的聊天会话"""
    try:
        session_mgr.append_conversation_messages(session_id, conv_id, [
            {"role": "user", "text": user_msg, "view_mode": view_mode},
            {"role": "agent", "text": reply, "note": note, "view_mode": view_mode},
        ])
    except Exception:
        pass  # 聊天记录保存失败不应阻断回复


@router.post("/api/sessions/{session_id}/chat")
def chat_message(session_id: str, payload: ChatMessageRequest) -> dict:
    """统一聊天入口：普通对话与 Agent 修订动作共用一个接口。"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    # 确定当前对话 ID：如果没传或不存在则自动创建/获取默认
    conv_id = payload.conv_id or "default"
    conversations = session.get("conversations", [])
    if not any(c.get("conv_id") == conv_id for c in conversations):
        conv_id = (conversations[0]["conv_id"] if conversations
                   else session_mgr.create_conversation(session_id, "默认对话")["conv_id"])

    revision = None
    if payload.chat_mode == "agent":
        if payload.confirmed_revision:
            if not payload.revision_target or not payload.revision_feedback:
                raise HTTPException(status_code=400, detail="确认修改时必须提供 revision_target 和 revision_feedback")
            revision = {
                "target": payload.revision_target,
                "feedback": payload.revision_feedback,
                "source": "confirmed",
            }
        else:
            revision = _parse_explicit_chat_revision(message, payload.view_mode)
            if not revision:
                revision = _infer_chat_revision_ai(session, message, payload.view_mode, payload.current_paper_id)

    if revision and revision.get("intent") == "clarify":
        reply = "我还不能确定你是不是在请求修改内容。你可以直接说出要改哪里，或者用 /修订 + 修改意见 明确告诉我。"
        note = revision.get("reason", "需要你进一步澄清修改意图。")
        _save_chat_exchange(session_id, message, reply, note, payload.view_mode, conv_id)
        return {
            "conv_id": conv_id,
            "reply": reply,
            "note": note,
            "action_taken": False,
            "action": "clarify_revision",
            "confirmation_required": False,
            "session_state": session.get("state", ""),
            "session_state_label": STATE_LABELS.get(session.get("state", ""), session.get("state", "")),
        }

    if revision:
        target = revision["target"]
        feedback = revision["feedback"]
        source = revision.get("source", "explicit")

        if source == "semantic" or source == "ai":
            reply = "我判断你这条消息像是在请求修改内容。请在对话里确认后再执行，我会按你的确认内容进行修订。"
            note = "已识别到修改意图，等待你确认后执行。"
            _save_chat_exchange(session_id, message, reply, note, payload.view_mode, conv_id)
            return {
                "conv_id": conv_id,
                "reply": reply,
                "note": note,
                "action_taken": False,
                "action": "confirm_revision",
                "confirmation_required": True,
                "pending_revision": {
                    "target": target,
                    "feedback": feedback,
                },
                "session_state": session.get("state", ""),
                "session_state_label": STATE_LABELS.get(session.get("state", ""), session.get("state", "")),
            }

        if target == "review":
            session_mgr.save_feedback(session_id, feedback)
            result = run_write_phase(
                session_id,
                RunPhaseRequest(
                    topic=session.get("topic", ""),
                    start_phase="write",
                    max_loops=20,
                ),
            )
            fresh_session = session_mgr.load_session(session_id) or session
            reply = "综述已根据你的反馈重新生成。"
            note = "综述修订已完成。"
            _save_chat_exchange(session_id, message, reply, note, payload.view_mode, conv_id)
            return {
                "conv_id": conv_id,
                "reply": reply,
                "note": note,
                "action_taken": True,
                "action": "revise_review",
                "confirmation_required": False,
                "session_state": fresh_session.get("state", ""),
                "session_state_label": STATE_LABELS.get(fresh_session.get("state", ""), fresh_session.get("state", "")),
                "review": result.get("review", fresh_session.get("review", "")),
                "draft": result.get("review", fresh_session.get("draft", "")),
            }

        revise_result = revise_notes_phase(
            session_id,
            ReviseNotesRequest(
                topic=session.get("topic", ""),
                feedback=feedback,
                paper_id=payload.current_paper_id,
            ),
        )
        try:
            session_mgr.update_session_state(session_id, "reviewing_notes")
        except ValueError:
            pass
        fresh_session = session_mgr.load_session(session_id) or session
        reply = "笔记已根据你的反馈修订。"
        note = "笔记修订已完成。"
        _save_chat_exchange(session_id, message, reply, note, payload.view_mode, conv_id)
        return {
            "conv_id": conv_id,
            "reply": reply,
            "note": note,
            "action_taken": True,
            "action": "revise_notes",
            "confirmation_required": False,
            "session_state": fresh_session.get("state", session.get("state", "")),
            "session_state_label": STATE_LABELS.get(fresh_session.get("state", ""), session.get("state", "")),
            "notes": revise_result.get("notes", ""),
        }

    reply_data = _build_chat_answer(session, message, payload.view_mode, payload.current_paper_id, conv_id)
    reply = reply_data["reply"]
    note = reply_data.get("note", "")

    _save_chat_exchange(session_id, message, reply, note, payload.view_mode, conv_id)

    return {
        "conv_id": conv_id,
        "reply": reply,
        "note": note,
        "action_taken": False,
        "action": "chat",
        "confirmation_required": False,
        "session_state": session.get("state", ""),
        "session_state_label": STATE_LABELS.get(session.get("state", ""), session.get("state", "")),
    }


# ━━━━━ 流式聊天端点（SSE）━━━━━

@router.post("/api/sessions/{session_id}/chat/stream")
async def chat_message_stream(session_id: str, payload: ChatMessageRequest):
    """流式聊天端点：SSE 逐 token 推送回复，带引用标注。"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    conv_id = payload.conv_id or "default"
    conversations = session.get("conversations", [])
    if not any(c.get("conv_id") == conv_id for c in conversations):
        conv_id = (conversations[0]["conv_id"] if conversations
                   else session_mgr.create_conversation(session_id, "默认对话")["conv_id"])

    # 构建 prompt（复用 _build_chat_answer 的逻辑，但不调用 LLM）
    paper = None
    if payload.current_paper_id:
        for item in session.get("papers", []):
            if item.get("paper_id") == payload.current_paper_id:
                paper = item
                break
    if paper is None:
        papers = session.get("papers", [])
        paper = papers[0] if papers else None

    current_name = (paper or {}).get("title") or (paper or {}).get("paper_id") or session.get("topic", "当前主题")
    current_abstract = (paper or {}).get("abstract", "") or (paper or {}).get("summary", "") or ""
    current_notes = session.get("notes", "") or ""
    current_review = session.get("review", "") or ""
    accepted_names = "、".join(
        [p.get("title") or p.get("paper_id", "") for p in session.get("papers", []) if p.get("status") == "accepted"]
    )

    # RAG 检索
    rag_context = ""
    rag_citations = []  # 引用标注列表
    _sid = session.get("session_id", "")
    if _sid:
        try:
            from tools.retriever import HybridRetriever  # noqa
            _papers_dir = str(SESSIONS_DIR / _sid / "papers")
            retriever = HybridRetriever(_sid, _papers_dir)
            passages = retriever.iterative_retrieve(message, top_k=10)
            if passages:
                rag_parts = []
                for i, p in enumerate(passages):
                    paper_id = p.get("paper_id", "")
                    page = p.get("page", "?")
                    title = ""
                    for pp in session.get("papers", []):
                        if pp.get("paper_id") == paper_id:
                            title = pp.get("title", "")[:60]
                            break
                    source = f"{title or paper_id} (第{page}页)"
                    ref_id = f"[{i + 1}]"
                    rag_parts.append(f"【{ref_id} {source}】\n{p['text']}")
                    rag_citations.append({
                        "id": ref_id,
                        "paper_id": paper_id,
                        "title": title or paper_id,
                        "page": page,
                        "snippet": p.get("text", "")[:200],
                    })
                rag_context = "\n\n---\n\n".join(rag_parts)
        except Exception:
            pass

    # 对话历史
    history_context = ""
    if _sid:
        try:
            all_messages = session_mgr.get_conversation_messages(_sid, conv_id)
            recent = all_messages[:-1] if len(all_messages) > 1 else []
            recent = recent[-12:]
            if recent:
                history_lines = []
                for msg in recent:
                    role_label = "用户" if msg.get("role") == "user" else "助手"
                    history_lines.append(f"{role_label}：{msg.get('text', '')}")
                history_context = "\n".join(history_lines)
        except Exception:
            pass

    # 上下文窗口管理
    ctx = _manage_context_window(
        current_notes=current_notes,
        current_review=current_review,
        current_abstract=current_abstract,
        rag_context=rag_context,
        history_context=history_context,
        message=message,
    )

    system_prompt = """你是一个严谨、简洁的中文学术助理。
你的任务是围绕当前论文、笔记或综述草稿，直接回答用户的问题。

要求：
- 只能基于给定上下文回答，不要编造未提供的信息。
- 如果有"检索到的原文段落"，优先引用原文内容回答问题，并在引用处标注来源编号如 [1]、[2]。
- 如果上下文不足，明确说明无法从当前材料判断，并给出下一步建议。
- 回答要自然、直接、简洁，默认 3-6 句；如果用户要求展开，可以适度加长。
- 如果对话历史中有相关上下文，请结合历史理解用户的追问和指代。
"""

    user_prompt = f"""会话主题：{session.get('topic', '')}
当前视图模式：{payload.view_mode}
当前论文：{current_name}
已选论文：{accepted_names or '暂无'}

当前论文摘要（如有）：
{ctx['abstract'] or '无'}

当前研究笔记（如有）：
{ctx['notes'] or '无'}

当前综述（如有）：
{ctx['review'] or '无'}

【从论文 PDF 中检索到的原文段落】
{ctx['rag'] or '（无相关检索结果）'}

【对话历史（最近几轮）】
{ctx['history'] or '（这是对话的第一条消息）'}

用户问题：{message}

请基于以上资料（特别是检索到的原文段落和对话历史）回答问题。如引用原文，请标注来源编号。注意理解对话历史中的指代关系。"""

    async def generate_sse():
        full_reply = ""
        try:
            llm = _get_chat_intent_llm()
            for token in llm.chat_stream(system_prompt, user_prompt, []):
                full_reply += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # 发送引用标注
        if rag_citations:
            yield f"data: {json.dumps({'citations': rag_citations})}\n\n"

        # 发送结束标记
        rag_status = "used" if rag_context else "no_results"
        yield f"data: {json.dumps({'done': True, 'rag_status': rag_status, 'rag_count': len(rag_citations)})}\n\n"

        # 保存对话记录
        note = "基于论文原文生成回答" if rag_context else "基于当前上下文生成回答"
        _save_chat_exchange(session_id, message, full_reply, note, payload.view_mode, conv_id)

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ━━━ 上下文窗口统计与压缩 ━━━

@router.get("/api/sessions/{session_id}/context/stats")
def get_context_stats(session_id: str, conv_id: str = "default") -> dict:
    """获取当前对话的上下文窗口使用统计"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    messages = session_mgr.get_conversation_messages(session_id, conv_id) or []
    total_chars = sum(len(m.get("text", "")) for m in messages)
    # 粗略估算 token 数（中文约 1.5 字符/token，英文约 4 字符/token）
    estimated_tokens = int(total_chars / 2.5)
    message_count = len(messages)
    round_count = message_count // 2  # 每轮 = 用户 + AI

    # 各组件占用估算
    notes_chars = len(session.get("notes", "") or "")
    review_chars = len(session.get("review", session.get("draft", "")) or "")

    return {
        "session_id": session_id,
        "conv_id": conv_id,
        "message_count": message_count,
        "round_count": round_count,
        "total_chars": total_chars,
        "estimated_tokens": estimated_tokens,
        "max_tokens": MAX_CONTEXT_CHARS // 2,  # 约 40K tokens
        "usage_percent": min(100, round(estimated_tokens / (MAX_CONTEXT_CHARS // 2) * 100, 1)),
        "notes_chars": notes_chars,
        "review_chars": review_chars,
        "draft_chars": review_chars,
        "rag_limit": MAX_RAG_CHARS,
        "history_limit": MAX_HISTORY_CHARS,
    }


@router.post("/api/sessions/{session_id}/context/compress")
def compress_context(session_id: str, conv_id: str = "default") -> dict:
    """压缩对话历史：用 LLM 将早期消息摘要为一段简短上下文"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    messages = session_mgr.get_conversation_messages(session_id, conv_id) or []
    if len(messages) <= 6:  # 少于 3 轮不压缩
        return {"status": "skipped", "message": "对话轮次太少，无需压缩", "message_count": len(messages)}

    # 保留最近 4 轮（8 条），压缩更早的消息
    recent = messages[-8:]
    to_compress = messages[:-8]
    if not to_compress:
        return {"status": "skipped", "message": "无需压缩", "message_count": len(messages)}

    # 构建压缩 prompt
    history_text = "\n".join(
        f"{'用户' if m.get('role') == 'user' else 'AI'}：{m.get('text', '')[:300]}"
        for m in to_compress
    )

    compress_prompt = f"""请将以下对话历史压缩为一段简洁的摘要（不超过 300 字），保留关键信息和上下文：

{history_text}

只输出摘要文本，不要加任何前缀或解释。"""

    try:
        llm = _get_chat_intent_llm()
        summary = llm.chat("你是简洁的对话摘要助手。", compress_prompt, []).strip()
    except Exception as e:
        return {"status": "error", "message": f"压缩失败: {str(e)}"}

    # 构建新的消息列表：摘要消息 + 最近 4 轮
    compressed = [
        {"role": "system", "text": f"[对话历史摘要] {summary}", "timestamp": datetime.datetime.now().isoformat()},
    ] + recent

    # 保存压缩后的消息
    conv_path = SESSIONS_DIR / session_id / "chats" / f"{conv_id}.json"
    try:
        conv_path.write_text(json.dumps(compressed, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    # 更新索引
    from backend.session_manager import SessionManager
    mgr = SessionManager(str(SESSIONS_DIR))
    try:
        mgr._update_conv_index(session_id, conv_id, len(compressed))
    except Exception:
        pass

    return {
        "status": "compressed",
        "original_count": len(messages),
        "compressed_count": len(compressed),
        "summary": summary[:200],
        "message": f"已将 {len(to_compress)} 条消息压缩为摘要，保留最近 4 轮对话",
    }

