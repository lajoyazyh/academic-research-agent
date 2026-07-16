"""Session 管理、论文管理、笔记管理 API"""
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

from backend.session_manager import SessionState, STATE_LABELS, VALID_TRANSITIONS
from functools import lru_cache
from llms.client import LLMClient

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    topic: str
    # keywords can be a raw string (from simple textarea) or a structured list
    keywords: Optional[list] = None

class UpdateStateRequest(BaseModel):
    state: str

class UpdateKeywordsRequest(BaseModel):
    keywords: list[dict]


class SaveFeedbackRequest(BaseModel):
    feedback: str

class ChatMessageRequest(BaseModel):
    message: str
    view_mode: str = "summary"
    chat_mode: str = "normal"
    current_paper_id: str | None = None
    conv_id: str | None = None       # 多会话：指定对话 ID
    confirmed_revision: bool = False
    revision_target: str | None = None
    revision_feedback: str | None = None


class ChatMessageResponse(BaseModel):
    reply: str
    note: str = ""
    action_taken: bool = False
    action: str = "chat"
    session_state: str = ""
    session_state_label: str = ""

class SessionSummary(BaseModel):
    session_id: str
    topic: str
    state_label: str
    created_at: str
    updated_at: str

class PaperInfo(BaseModel):
    paper_id: str
    title: str = ""
    authors: str = ""
    source: str = "agent_search"
    source_type: str = "arxiv"
    status: str = "pending"
    url: str = ""
    added_at: str = ""

class AddPaperRequest(BaseModel):
    paper: PaperInfo


@lru_cache(maxsize=1)
def _get_chat_intent_llm() -> LLMClient:
    return LLMClient()


@router.post("/create")
def create_session(payload: dict) -> dict:
    """创建新 Session，支持可选的 keywords 字段（字符串或数组）和 skills 字段。"""
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        raise HTTPException(status_code=400, detail="主题不能为空")
    keywords = payload.get("keywords")
    skills = payload.get("skills")  # {"search": "skill_xxx", "notes": null, "write": "skill_yyy"}
    try:
        return session_mgr.create_session(topic, keywords=keywords, skills=skills)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session 创建失败: {str(e)}")


@router.get("/list")
def list_sessions() -> list[dict]:
    """获取所有 Session 摘要列表"""
    return session_mgr.list_sessions()


@router.get("/state-machine")
def get_state_machine() -> dict:
    """获取状态机定义（供前端参考）—— 必须放在 {session_id} 路由之前"""
    transitions = {}
    for state, targets in VALID_TRANSITIONS.items():
        transitions[state.value] = [t.value for t in targets]
    return {
        "states": [s.value for s in SessionState],
        "state_labels": STATE_LABELS,
        "valid_transitions": transitions,
    }


@router.get("/{session_id}")
def get_session(session_id: str) -> dict:
    """获取 Session 完整状态"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return session


@router.delete("/{session_id}")
def delete_session(session_id: str) -> dict:
    """删除 Session"""
    if not session_mgr.delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return {"status": "deleted", "session_id": session_id}


@router.put("/{session_id}/state")
def update_session_state(session_id: str, payload: UpdateStateRequest) -> dict:
    """更新 Session 状态（带状态机校验）"""
    try:
        return session_mgr.update_session_state(session_id, payload.state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"状态更新失败: {str(e)}")

@router.post("/{session_id}/state/auto-fix")
def auto_fix_session_state(session_id: str) -> dict:
    """手动修复卡住的 Session 状态（强制回退到上一个稳定状态）"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    state = session.get("state", "planning")
    if state not in {"searching", "writing"}:
        return {"status": "skipped", "message": f"状态 '{state}' 不需要修复", "state": state}

    fallback = {"searching": "plan_confirmed", "writing": "reviewing_notes"}
    new_state = fallback.get(state, "plan_confirmed")

    try:
        session_mgr.update_session_state(session_id, new_state)
    except ValueError:
        # 如果状态机不允许回退，直接改 metadata
        session_dir = session_mgr.root / session_id
        meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
        meta["state"] = new_state
        meta["updated_at"] = datetime.datetime.now().isoformat()
        (session_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "fixed", "message": f"状态已从 '{state}' 修复为 '{new_state}'", "state": new_state}


@router.put("/{session_id}")
def update_session(session_id: str, payload: dict) -> dict:
    """更新会话基本信息（主题等）"""
    session_dir = session_mgr.root / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    metadata_path = session_dir / "metadata.json"
    import json as _json
    if metadata_path.exists():
        meta = _json.loads(metadata_path.read_text(encoding="utf-8"))
        if "topic" in payload:
            meta["topic"] = payload["topic"]
        meta["updated_at"] = datetime.datetime.now().isoformat()
        metadata_path.write_text(_json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_mgr.load_session(session_id)


@router.put("/{session_id}/keywords")
def save_keywords(session_id: str, payload: UpdateKeywordsRequest) -> dict:
    """保存确认后的关键词"""
    try:
        return session_mgr.save_keywords(session_id, payload.keywords)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.get("/{session_id}/papers")
def get_papers(session_id: str) -> list[dict]:
    """获取论文列表"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return session.get("papers", [])


@router.delete("/{session_id}/papers/{paper_id:path}")
def delete_paper(session_id: str, paper_id: str) -> dict:
    """删除单篇论文"""
    # paper_id:path 允许 ID 中包含斜杠（如 DOI: 10.2139/ssrn.xxx）
    try:
        return session_mgr.delete_paper(session_id, paper_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/papers/batch-delete")
def batch_delete_papers(session_id: str, paper_ids: list[str]) -> dict:
    """批量删除论文"""
    try:
        return session_mgr.batch_delete_papers(session_id, paper_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdatePaperStatusRequest(BaseModel):
    status: str = "pending"


@router.put("/{session_id}/papers/{paper_id:path}/status")
def update_paper_status(session_id: str, paper_id: str, payload: UpdatePaperStatusRequest) -> dict:
    """更新论文审查状态"""
    try:
        return session_mgr.update_paper_status(session_id, paper_id, payload.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

class AddCustomPaperRequest(BaseModel):
    paper_id: str

@router.post("/{session_id}/papers/custom")
def add_custom_paper(session_id: str, payload: AddCustomPaperRequest):
    """用户手动添加自定义论文并自动合并入笔记，重新生成综述"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    
    paper_id = payload.paper_id.strip()
    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id 不能为空")

    from tools.pdf_tools import ArxivPdfReaderTool  # noqa
    
    # 获取真正的 session 存储目录
    import os
    session_dir = session_mgr.root / session_id
    papers_dir = str(session_dir / "papers")
    os.makedirs(papers_dir, exist_ok=True)
    reader = ArxivPdfReaderTool(papers_dir=papers_dir)
    
    res_text = reader.execute(paper_id=paper_id, read_full=True)
    pdf_ok = not ("发生错误" in res_text or "解析失败" in res_text)

    session_papers = session.get("papers", [])
    
    clean_id = paper_id
    if paper_id.startswith("http"):
        import hashlib
        clean_id = "paper_" + hashlib.md5(paper_id.encode('utf-8')).hexdigest()[:8]
    else:
        clean_id = paper_id.split("v")[0] if "v" in paper_id else paper_id

    if any(p.get("paper_id") == clean_id for p in session_papers):
        return {"message": "Success", "notes": session.get("notes", ""), "draft": session.get("draft", ""), "exists": True}

    # ━━━ 获取论文元数据（标题、作者、摘要）━━━
    paper_title = f"{paper_id}"
    paper_authors = ""
    paper_abstract = ""
    paper_url = f"https://arxiv.org/abs/{clean_id}"

    # 优先尝试用 arxiv_fetch 获取元数据
    from tools.arxiv_tools import ArxivFetchTool  # noqa
    try:
        fetch_tool = ArxivFetchTool()
        fetch_result = fetch_tool.execute(paper_id=clean_id)
        if fetch_result and "发生错误" not in fetch_result and "失败" not in fetch_result:
            # 尝试从 arxiv_fetch 的返回中提取元数据
            import re as _re
            title_match = _re.search(r'(?:Title|标题)[：:]\s*(.+?)(?:\n|$)', fetch_result, _re.IGNORECASE)
            if title_match:
                paper_title = title_match.group(1).strip()
            authors_match = _re.search(r'(?:Authors?|作者)[：:]\s*(.+?)(?:\n|$)', fetch_result, _re.IGNORECASE)
            if authors_match:
                paper_authors = authors_match.group(1).strip()
            abstract_match = _re.search(r'(?:Abstract|摘要)[：:]\s*(.+?)(?:\n\w|$)', fetch_result, _re.IGNORECASE | _re.DOTALL)
            if abstract_match:
                paper_abstract = abstract_match.group(1).strip()[:500]
    except Exception:
        pass  # 如果 fetch 失败，用默认值兜底

    # 如果元数据仍为空且 PDF 下载成功，用 LLM 从 PDF 文本中提取
    if (not paper_title or paper_title == clean_id) and pdf_ok:
        try:
            from llms.client import LLMClient
            llm = LLMClient()
            if llm.language == "en":
                extract_prompt = f"""Extract the paper title and authors from the text below. Return JSON only.

Paper text excerpt:
{res_text[:2000]}

Return:
{{"title": "paper title", "authors": "author list"}}
"""
                extract_system = "You are a precise scholarly metadata extractor. Return valid JSON only."
            else:
                extract_prompt = f"""从以下论文文本中提取标题和作者。只输出 JSON，不要其他内容。

论文文本片段：
{res_text[:2000]}

请输出：
{{"title": "论文标题", "authors": "作者列表"}}
"""
                extract_system = "你是精确的元数据提取工具。只输出JSON。"
            raw = llm.chat(extract_system, extract_prompt, [])
            import re as _re
            jmatch = _re.search(r'\{[\s\S]*\}', raw)
            if jmatch:
                import json as _json
                meta = _json.loads(jmatch.group())
                if meta.get("title"):
                    paper_title = meta["title"]
                if meta.get("authors"):
                    paper_authors = meta["authors"]
        except Exception:
            pass

    # 从删除列表中移除，允许重新添加
    session_mgr.undelete_paper(session_id, clean_id)

    session_papers.append({
        "paper_id": clean_id,
        "title": paper_title,
        "authors": paper_authors,
        "abstract": paper_abstract,
        "url": paper_url,
        "source": "user_custom",
        "source_type": "arxiv",
        "status": "accepted",
        "added_at": datetime.datetime.now().isoformat(),
    })
    session_mgr.save_papers_list(session_id, session_papers)

#    from llms.client import LLMClient
#    llm = LLMClient()
#    topic = session.get("topic", "")
#    
#    summarize_prompt = f"""你是一名擅长文献总结的研究员。这里是用户上传的一篇新论文的初步文本内容。研究主题是《{topic}》。
#请你认真阅读后，提炼出这篇论文的关键发现、方法或指标，并撰写一段学术笔记（约 300-500 字）。
#
#论文原文（前几页）：
#{res_text}
#
#请直接输出你的高质量学术笔记：
#"""
#    new_note = llm.chat("你是深度的学术研究员。", summarize_prompt, []).strip()
#
#    old_notes = session.get("notes", "")
#    updated_notes = old_notes + f"\n\n## 追加参考文献: {paper_id}\n\n{new_note}\n\n---\n"
#    session_mgr.save_notes(session_id, updated_notes)
#    
#    return {"message": "Success", "notes": updated_notes, "draft": session.get("draft", "")}
    return {"message": "Success"}


@router.post("/{session_id}/papers/upload")
async def upload_paper(session_id: str, file: UploadFile = File(...)):
    """用户上传本地 PDF，解析并总结笔记"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    
    import os
    import shutil
    import hashlib
    session_dir = session_mgr.root / session_id
    papers_dir = session_dir / "papers"
    os.makedirs(papers_dir, exist_ok=True)
    
    # Keep the user-facing name as metadata only. Persist under the generated
    # paper id so preview/delete routes use the same stable filename and an
    # uploaded filename can never escape the papers directory.
    safe_filename = Path(file.filename or "uploaded-paper.pdf").name
    clean_id = "paper_" + hashlib.md5(safe_filename.encode('utf-8')).hexdigest()[:8]
    
    stored_filename = f"{clean_id}.pdf"
    file_path = papers_dir / stored_filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        import fitz
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少依赖 PyMuPDF")

    try:
        doc = fitz.open(str(file_path))
        total_pages = len(doc)
        if total_pages == 0:
            raise ValueError("PDF 为空。")

        text_blocks = []
        pages_to_read = list(range(min(5, total_pages)))
        for p_num in pages_to_read:
            t = doc.load_page(p_num).get_text("text").strip()
            if t: text_blocks.append(f"--- 第 {p_num + 1} 页全文 ---\n{t}")
            
        res_text = "\n\n".join(text_blocks)
        if not res_text.strip():
            raise ValueError("无法从 PDF 提取文本内容")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析 PDF 失败：{str(e)}")

    session_papers = session.get("papers", [])
    paper_title = f"{safe_filename}"
    paper_authors = ""

    if any(p.get("paper_id") == clean_id for p in session_papers):
        return {"message": "Success", "notes": session.get("notes", ""), "draft": session.get("draft", ""), "exists": True, "paper_id": clean_id}

    # ━━━ 从 PDF 文本中提取元数据（标题、作者）━━━
    try:
        from llms.client import LLMClient
        llm = LLMClient()
        if llm.language == "en":
            extract_prompt = f"""Extract the paper title and authors from the PDF text below. Return JSON only.

PDF excerpt (first five pages):
{res_text[:2000]}

Return:
{{"title": "paper title", "authors": "author list"}}
"""
            extract_system = "You are a precise scholarly metadata extractor. Return valid JSON only."
        else:
            extract_prompt = f"""从以下 PDF 论文文本中提取标题和作者。只输出 JSON，不要其他内容。

PDF 文本片段（前 5 页）：
{res_text[:2000]}

请输出：
{{"title": "论文标题", "authors": "作者列表"}}
"""
            extract_system = "你是精确的元数据提取工具。只输出JSON。"
        raw = llm.chat(extract_system, extract_prompt, [])
        import re as _re
        jmatch = _re.search(r'\{[\s\S]*\}', raw)
        if jmatch:
            import json as _json
            meta = _json.loads(jmatch.group())
            if meta.get("title"):
                paper_title = meta["title"]
            if meta.get("authors"):
                paper_authors = meta["authors"]
    except Exception:
        pass  # 如果 LLM 提取失败，用文件名兜底

    # 从删除列表中移除，允许重新添加
    session_mgr.undelete_paper(session_id, clean_id)

    session_papers.append({
        "paper_id": clean_id,
        "title": paper_title,
        "authors": paper_authors,
        "source": "user_upload",
        "source_type": "pdf",
        "original_filename": safe_filename,
        "pdf_filename": stored_filename,
        "status": "accepted",
        "added_at": datetime.datetime.now().isoformat(),
    })
    session_mgr.save_papers_list(session_id, session_papers)

#    from llms.client import LLMClient
#    llm = LLMClient()
#    topic = session.get("topic", "")
#    
#    summarize_prompt = f"""你是一名擅长文献总结的研究员。这里是用户上传的一篇新论文的初步文本内容。研究主题是《{topic}》。
#请你认真阅读后，提炼出这篇论文的关键发现、方法或指标，并撰写一段学术笔记（约 300-500 字）。
#
#论文原文（前几页）：
#{res_text}
#
#请直接输出你的高质量学术笔记：
#"""
#    try:
#        new_note = llm.chat("你是深度的学术研究员。", summarize_prompt, []).strip()
#    except Exception as e:
#        new_note = f"生成笔记失败: {str(e)}"
#
#    old_notes = session.get("notes", "")
#    updated_notes = old_notes + f"\n\n## 追加参考文献: {safe_filename}\n\n{new_note}\n\n---\n"
#    session_mgr.save_notes(session_id, updated_notes)
#    
#    return {"message": "Success", "notes": updated_notes, "draft": session.get("draft", ""), "paper_id": clean_id}
    return {"message": "Success"}


@router.post("/{session_id}/papers/{paper_id}/pdf/retry")
def retry_paper_pdf(session_id: str, paper_id: str) -> dict:
    """Retry lawful OA/arXiv PDF resolution for a metadata-only paper."""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    paper = next((item for item in session.get("papers", []) if item.get("paper_id") == paper_id), None)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    from tools.paper_register import PaperRegisterTool
    tool = PaperRegisterTool(
        session_id=session_id,
        papers_dir=str(session_mgr.root / session_id / "papers"),
        session_manager=session_mgr,
    )
    downloaded, message, _path = tool.retry_pdf(paper)
    return {
        "ok": downloaded,
        "message": message,
        "paper": next(
            (item for item in session_mgr.get_papers(session_id) if item.get("paper_id") == paper_id),
            paper,
        ),
    }

# ━━━━━ 笔记管理（第一波基础接口，完整功能在第三波）━━━━━

@router.get("/{session_id}/notes")
def get_notes(session_id: str) -> dict:
    """获取笔记"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return {"notes": session.get("notes", "")}


@router.put("/{session_id}/notes")
def save_notes(session_id: str, payload: dict) -> dict:
    """保存笔记编辑"""
    content = payload.get("content", "")
    version_note = payload.get("version_note", "")
    paper_id = payload.get("paper_id", "")
    try:
        if paper_id:
            session_mgr.batch_update_paper_notes(session_id, {paper_id: content})
            return {"message": "Success"}
        else:
            return session_mgr.save_notes(session_id, content, version_note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{session_id}/analysis")
def save_analysis(session_id: str, payload: dict) -> dict:
    """保存用户手动编辑后的分析 Markdown 内容"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    content = str(payload.get("content", "") or "")
    section = str(payload.get("section", "") or "").strip()
    analysis = dict(session.get("analysis") or {})
    if section:
        if section not in {"compare", "lineage", "gaps"}:
            raise HTTPException(status_code=400, detail="section 必须是 compare、lineage 或 gaps")
        analysis[section] = content
    else:
        analysis["document"] = content

    analysis.update({
        "phase": "analysis",
        "session_id": session_id,
        "document": _analysis_to_markdown(analysis, session.get("topic", "")),
        "updated_at": datetime.datetime.now().isoformat(),
    })

    analysis_dir = session_mgr.root / session_id / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "analysis_results.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"message": "Success", "analysis": analysis}


def _analysis_to_markdown(analysis: dict, topic: str) -> str:
    sections = []
    compare = str(analysis.get("compare", "") or "").strip()
    lineage = str(analysis.get("lineage", "") or "").strip()
    gaps = str(analysis.get("gaps", "") or "").strip()
    if compare:
        sections.append(f"## 文献对比分析\n\n{compare}")
    if lineage:
        sections.append(f"## 研究脉络梳理\n\n{lineage}")
    if gaps:
        sections.append(f"## 研究空白发现\n\n{gaps}")
    if not sections:
        return str(analysis.get("document", "") or "")
    return f"# 深度分析：{topic or '当前主题'}\n\n" + "\n\n---\n\n".join(sections)


@router.put("/{session_id}/feedback")
def save_feedback(session_id: str, payload: SaveFeedbackRequest) -> dict:
    """保存综述修改反馈"""
    try:
      return session_mgr.save_feedback(session_id, payload.feedback)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _build_chat_reply(session: dict, view_mode: str, current_paper_id: str | None = None) -> dict[str, str]:
    paper = None
    if current_paper_id:
        for item in session.get("papers", []):
            if item.get("paper_id") == current_paper_id:
                paper = item
                break
    if paper is None:
        papers = session.get("papers", [])
        paper = papers[0] if papers else None

    if view_mode == "review":
        accepted_count = len([p for p in session.get("papers", []) if p.get("status") == "accepted"])
        accepted_names = "、".join(
            [p.get("title") or p.get("paper_id", "") for p in session.get("papers", []) if p.get("status") == "accepted"]
        )
        return {
            "reply": f"根据当前综述草稿和 {accepted_count} 篇已选论文（{accepted_names or '暂无'}），请明确要修改的章节或段落，并将修改意见压缩为 3-5 条可执行建议。",
            "note": "综述模式：可直接输入 /修订 + 修改意见 触发综述重写。",
            "rag_status": "not_attempted",
        }

    if view_mode == "report":
        current_name = (paper or {}).get("title") or (paper or {}).get("paper_id") or session.get("topic", "当前论文")
        return {
            "reply": f"收到你对「{current_name}」笔记的修改意见。你可以直接输入 /修订 + 修改意见，让系统基于反馈修订当前笔记。",
            "note": "笔记模式：可直接输入 /修订 + 修改意见 触发笔记修订。",
            "rag_status": "not_attempted",
        }

    current_name = (paper or {}).get("title") or (paper or {}).get("paper_id") or session.get("topic", "当前主题")
    return {
        "reply": f"针对「{current_name}」的摘要内容，我可以继续回答你的问题。若要修改内容，请切换到笔记或综述视图后使用 Agent 模式和 /修订 指令。",
        "note": "当前为摘要模式，仅回答当前论文内容。",
        "rag_status": "not_attempted",
    }


