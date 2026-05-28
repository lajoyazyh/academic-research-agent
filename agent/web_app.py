import threading
import uuid
import json
import datetime
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from main import run_agent_pipeline, run_agent_pipeline_session
from backend.session_manager import SessionManager, SessionState, STATE_LABELS, VALID_TRANSITIONS
from llms.client import LLMClient
from utils.parser import extract_json


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DOCS_DIR = BASE_DIR / "documents"
SESSIONS_DIR = BASE_DIR / "sessions"

# 初始化全局 SessionManager
session_mgr = SessionManager(str(SESSIONS_DIR))

# ━━━ 收藏夹存储 ━━━
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


class RunRequest(BaseModel):
    topic: str = "LLM Agent Memory（内存框架/机制）"
    max_loops: int = 20


class RunResponse(BaseModel):
    topic: str
    researcher_result: str
    writer_result: str
    traces: list[Dict[str, Any]]
    output_file: str


class RunStartResponse(BaseModel):
    run_id: str


class RunStatusResponse(BaseModel):
    run_id: str
    topic: str
    phase: str
    status: str
    traces: list[Dict[str, Any]]
    researcher_result: str
    writer_result: str
    output_file: str
    error: str
    failure_summary: Dict[str, int]
    papers: list[str] = []


app = FastAPI(title="Academic Agent Web", version="1.0.0")
RUNS: Dict[str, Dict[str, Any]] = {}
RUN_LOCK = threading.Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# 原有路由调整（替换 / 和新增）
@app.get("/")
def home():
    home_file = FRONTEND_DIR / "home.html"
    if not home_file.exists():
        raise HTTPException(status_code=404, detail="Home page not found")
    return HTMLResponse(home_file.read_text(encoding="utf-8"))

@app.get("/app/console")
def console():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Console page not found")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))

@app.get("/app/history")
def history_page():
    hist_file = FRONTEND_DIR / "history.html"
    if not hist_file.exists():
        raise HTTPException(status_code=404, detail="History page not found")
    return HTMLResponse(hist_file.read_text(encoding="utf-8"))

@app.get("/app/chat")
def chat_page():
    chat_file = FRONTEND_DIR / "chat.html"
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="Chat page not found")
    return HTMLResponse(chat_file.read_text(encoding="utf-8"))

@app.get("/app/help")
def help_page():
    help_file = FRONTEND_DIR / "help.html"
    if not help_file.exists():
        raise HTTPException(status_code=404, detail="Help page not found")
    return HTMLResponse(help_file.read_text(encoding="utf-8"))

@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def _summarize_failures_from_traces(traces: list[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for step in traces:
        if not isinstance(step, dict):
            continue
        error_type = str(step.get("error_type", "") or "").strip()
        if not error_type:
            continue
        summary[error_type] = summary.get(error_type, 0) + 1
    return summary


@app.get("/api/agent/history")
def get_history() -> list[Dict[str, Any]]:
    if not DOCS_DIR.exists():
        return []

    favs = _load_favorites()
    fav_filenames = {f.get("filename") for f in favs}

    runs = []
    for d in DOCS_DIR.iterdir():
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


@app.get("/api/agent/history/{filename}")
def get_history_detail(filename: str) -> Dict[str, Any]:
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    run_dir = DOCS_DIR / filename
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


@app.delete("/api/agent/history/{filename}")
def delete_history(filename: str) -> dict:
    """删除历史综述记录"""
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    run_dir = DOCS_DIR / filename
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
#  迭代三：收藏夹 API（替代原来的历史综述自动列表）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/favorites")
def get_favorites() -> list[dict]:
    """获取收藏夹列表"""
    favs = _load_favorites()
    # 补充文件大小信息
    enriched = []
    for fav in favs:
        filename = fav.get("filename", "")
        run_dir = DOCS_DIR / filename
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


@app.post("/api/favorites")
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


@app.delete("/api/favorites/{filename}")
def remove_favorite(filename: str) -> dict:
    """取消收藏"""
    favs = _load_favorites()
    favs = [f for f in favs if f.get("filename") != filename]
    _save_favorites(favs)
    return {"status": "unfavorited", "count": len(favs)}


@app.get("/api/agent/document/{filename}/papers/{pdf_name}")
def get_pdf(filename: str, pdf_name: str) -> FileResponse:
    if "/" in filename or "\\" in filename or "/" in pdf_name or "\\" in pdf_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # 先检查 Session 目录（迭代三新路径）
    pdf_path = SESSIONS_DIR / filename / "papers" / pdf_name
    if pdf_path.exists():
        return FileResponse(pdf_path, media_type="application/pdf")

    # 再检查旧 Documents 目录（迭代二兼容路径）
    pdf_path = DOCS_DIR / filename / "papers" / pdf_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(pdf_path, media_type="application/pdf")


def _run_pipeline_in_background(run_id: str, topic: str, max_loops: int) -> None:
    def on_agent_created(agent, work_dir):
        with RUN_LOCK:
            if run_id in RUNS:
                RUNS[run_id]["agent_ref"] = agent
                RUNS[run_id]["work_dir"] = work_dir

    try:
        with RUN_LOCK:
            RUNS[run_id]["status"] = "running"
            RUNS[run_id]["phase"] = "researcher"

        res = run_agent_pipeline(user_topic=topic, max_loops=max_loops, agent_callback=on_agent_created)

        with RUN_LOCK:
            RUNS[run_id]["phase"] = "done"
            RUNS[run_id]["status"] = "done"
            RUNS[run_id]["researcher_result"] = res.get("researcher_result", "")
            RUNS[run_id]["writer_result"] = res.get("writer_result", "")
            RUNS[run_id]["output_file"] = res.get("output_file", "")
            RUNS[run_id]["papers"] = res.get("papers", [])

    except Exception as exc:
        with RUN_LOCK:
            RUNS[run_id]["status"] = "error"
            RUNS[run_id]["phase"] = "failed"
            RUNS[run_id]["error"] = str(exc)


@app.post("/api/run", response_model=RunResponse)
def run_agent(payload: RunRequest) -> RunResponse:
    topic = payload.topic.strip() or "LLM Agent Memory（内存框架/机制）"

    if payload.max_loops < 1 or payload.max_loops > 60:
        raise HTTPException(status_code=400, detail="max_loops 必须在 1 到 60 之间")

    try:
        res = run_agent_pipeline(user_topic=topic, max_loops=payload.max_loops)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RunResponse(
        topic=topic,
        researcher_result=res["researcher_result"],
        writer_result=res["writer_result"],
        traces=res["traces"],
        output_file=res["output_file"],
    )


@app.post("/api/run/start", response_model=RunStartResponse)
def start_run(payload: RunRequest) -> RunStartResponse:
    topic = payload.topic.strip() or "LLM Agent Memory（内存框架/机制）"

    if payload.max_loops < 1 or payload.max_loops > 60:
        raise HTTPException(status_code=400, detail="max_loops 必须在 1 到 60 之间")

    run_id = uuid.uuid4().hex
    with RUN_LOCK:
        RUNS[run_id] = {
            "run_id": run_id,
            "topic": topic,
            "phase": "queued",
            "status": "running",
            "traces": [],
            "researcher_result": "",
            "writer_result": "",
            "output_file": "",
            "error": "",
            "agent_ref": None,
            "work_dir": "",
        }

    worker = threading.Thread(
        target=_run_pipeline_in_background,
        args=(run_id, topic, payload.max_loops),
        daemon=True,
    )
    worker.start()
    return RunStartResponse(run_id=run_id)


@app.get("/api/run/{run_id}", response_model=RunStatusResponse)
def get_run_status(run_id: str) -> RunStatusResponse:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run_id 不存在")

        if run.get("agent_ref"):
            traces = list(run["agent_ref"].traces)
        else:
            traces = list(run["traces"])

        failure_summary = _summarize_failures_from_traces(traces)

        papers = []
        if run.get("work_dir"):
            papers_dir = Path(run["work_dir"]) / "papers"
            if papers_dir.exists():
                papers = [p.name for p in papers_dir.glob("*.pdf")]

        return RunStatusResponse(
            run_id=run["run_id"],
            topic=run["topic"],
            phase=run["phase"],
            status=run["status"],
            traces=traces,
            researcher_result=run["researcher_result"],
            writer_result=run["writer_result"],
            output_file=run["output_file"],
            error=run["error"],
            failure_summary=failure_summary,
            papers=papers,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  迭代三新增：Session 管理 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    state: str
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


@app.post("/api/sessions/create")
def create_session(payload: dict) -> dict:
    """创建新 Session，支持可选的 keywords 字段（字符串或数组）。"""
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        raise HTTPException(status_code=400, detail="主题不能为空")
    keywords = payload.get("keywords")
    try:
        return session_mgr.create_session(topic, keywords=keywords)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session 创建失败: {str(e)}")


@app.get("/api/sessions/list")
def list_sessions() -> list[dict]:
    """获取所有 Session 摘要列表"""
    return session_mgr.list_sessions()


@app.get("/api/stats")
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
        session_dir = SESSIONS_DIR / s["session_id"]
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

    active_count = sum(
        1 for s in sessions
        if s.get("state") not in ("complete",)
    )

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


@app.get("/api/sessions/state-machine")
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


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    """获取 Session 完整状态"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return session


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """删除 Session"""
    if not session_mgr.delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return {"status": "deleted", "session_id": session_id}


@app.put("/api/sessions/{session_id}/state")
def update_session_state(session_id: str, payload: UpdateStateRequest) -> dict:
    """更新 Session 状态（带状态机校验）"""
    try:
        return session_mgr.update_session_state(session_id, payload.state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"状态更新失败: {str(e)}")


@app.put("/api/sessions/{session_id}")
def update_session(session_id: str, payload: dict) -> dict:
    """更新会话基本信息（主题等）"""
    session_dir = SESSIONS_DIR / session_id
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


@app.put("/api/sessions/{session_id}/keywords")
def save_keywords(session_id: str, payload: UpdateKeywordsRequest) -> dict:
    """保存确认后的关键词"""
    try:
        return session_mgr.save_keywords(session_id, payload.keywords)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ━━━━━ 论文管理（第一波基础接口，完整功能在第二波）━━━━━

@app.get("/api/sessions/{session_id}/papers")
def get_papers(session_id: str) -> list[dict]:
    """获取论文列表"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return session.get("papers", [])


@app.delete("/api/sessions/{session_id}/papers/{paper_id}")
def delete_paper(session_id: str, paper_id: str) -> dict:
    """删除单篇论文"""
    try:
        return session_mgr.delete_paper(session_id, paper_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/sessions/{session_id}/papers/batch-delete")
def batch_delete_papers(session_id: str, paper_ids: list[str]) -> dict:
    """批量删除论文"""
    try:
        return session_mgr.batch_delete_papers(session_id, paper_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdatePaperStatusRequest(BaseModel):
    status: str = "pending"


@app.put("/api/sessions/{session_id}/papers/{paper_id}/status")
def update_paper_status(session_id: str, paper_id: str, payload: UpdatePaperStatusRequest) -> dict:
    """更新论文审查状态"""
    try:
        return session_mgr.update_paper_status(session_id, paper_id, payload.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

class AddCustomPaperRequest(BaseModel):
    paper_id: str

@app.post("/api/sessions/{session_id}/papers/custom")
def add_custom_paper(session_id: str, payload: AddCustomPaperRequest):
    """用户手动添加自定义论文并自动合并入笔记，重新生成综述"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    
    paper_id = payload.paper_id.strip()
    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id 不能为空")

    from tools.pdf_tools import ArxivPdfReaderTool
    
    # 获取真正的 session 存储目录
    import os
    session_dir = session_mgr.root / session_id
    papers_dir = str(session_dir / "papers")
    os.makedirs(papers_dir, exist_ok=True)
    reader = ArxivPdfReaderTool(papers_dir=papers_dir)
    
    res_text = reader.execute(paper_id=paper_id, read_full=True)
    if "发生错误" in res_text or "解析失败" in res_text or "下载失败" in res_text:
        raise HTTPException(status_code=400, detail=res_text)

    session_papers = session.get("papers", [])
    paper_title = f"User Upload: {paper_id}"
    
    clean_id = paper_id
    if paper_id.startswith("http"):
        import hashlib
        clean_id = "paper_" + hashlib.md5(paper_id.encode('utf-8')).hexdigest()[:8]
    else:
        clean_id = paper_id.split("v")[0] if "v" in paper_id else paper_id

    if any(p.get("paper_id") == clean_id for p in session_papers):
        return {"message": "Success", "notes": session.get("notes", ""), "draft": session.get("draft", ""), "exists": True}

    # 从删除列表中移除，允许重新添加
    session_mgr.undelete_paper(session_id, clean_id)

    session_papers.append({
        "paper_id": clean_id,
        "title": paper_title,
        "source": "user_custom",
        "status": "accepted"
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


@app.post("/api/sessions/{session_id}/papers/upload")
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
    
    safe_filename = file.filename
    clean_id = "paper_" + hashlib.md5(safe_filename.encode('utf-8')).hexdigest()[:8]
    
    file_path = papers_dir / safe_filename
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

    if any(p.get("paper_id") == clean_id for p in session_papers):
        return {"message": "Success", "notes": session.get("notes", ""), "draft": session.get("draft", ""), "exists": True, "paper_id": clean_id}

    # 从删除列表中移除，允许重新添加
    session_mgr.undelete_paper(session_id, clean_id)

    session_papers.append({
        "paper_id": clean_id,
        "title": paper_title,
        "source": "user_upload",
        "status": "accepted"
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

# ━━━━━ 笔记管理（第一波基础接口，完整功能在第三波）━━━━━

@app.get("/api/sessions/{session_id}/notes")
def get_notes(session_id: str) -> dict:
    """获取笔记"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return {"notes": session.get("notes", "")}


@app.put("/api/sessions/{session_id}/notes")
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


@app.put("/api/sessions/{session_id}/feedback")
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
        }

    if view_mode == "report":
        current_name = (paper or {}).get("title") or (paper or {}).get("paper_id") or session.get("topic", "当前论文")
        return {
            "reply": f"收到你对「{current_name}」笔记的修改意见。你可以直接输入 /修订 + 修改意见，让系统基于反馈修订当前笔记。",
            "note": "笔记模式：可直接输入 /修订 + 修改意见 触发笔记修订。",
        }

    current_name = (paper or {}).get("title") or (paper or {}).get("paper_id") or session.get("topic", "当前主题")
    return {
        "reply": f"针对「{current_name}」的摘要内容，我可以继续回答你的问题。若要修改内容，请切换到笔记或综述视图后使用 Agent 模式和 /修订 指令。",
        "note": "当前为摘要模式，仅回答当前论文内容。",
    }


def _build_chat_answer(session: dict, message: str, view_mode: str, current_paper_id: str | None = None) -> dict[str, str]:
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
    current_draft = session.get("draft", "") or ""
    accepted_names = "、".join(
        [p.get("title") or p.get("paper_id", "") for p in session.get("papers", []) if p.get("status") == "accepted"]
    )

    system_prompt = """你是一个严谨、简洁的中文学术助理。
你的任务是围绕当前论文、笔记或综述草稿，直接回答用户的问题。

要求：
- 只能基于给定上下文回答，不要编造未提供的信息。
- 如果上下文不足，明确说明无法从当前材料判断，并给出下一步建议。
- 用户是在提问或解释时，优先回答问题本身，不要输出修改入口提示。
- 回答要自然、直接、简洁，默认 3-6 句；如果用户要求展开，可以适度加长。
- 如果用户明显在请求修改，应该由外层路由处理，这里只负责普通问答。
"""

    user_prompt = f"""会话主题：{session.get('topic', '')}
当前视图模式：{view_mode}
当前论文：{current_name}
已选论文：{accepted_names or '暂无'}

当前论文摘要（如有）：
{current_abstract or '无'}

当前研究笔记（如有）：
{current_notes[:4000] or '无'}

当前综述草稿（如有）：
{current_draft[:4000] or '无'}

用户问题：{message}

请直接回答用户问题。"""

    try:
        answer = _get_chat_intent_llm().chat(system_prompt, user_prompt, []).strip()
        if answer:
            note = f"基于当前{'综述' if view_mode == 'review' else '论文'}上下文生成回答。"
            return {"reply": answer, "note": note}
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


def _infer_chat_revision_ai(session: dict, message: str, view_mode: str, current_paper_id: str | None) -> dict[str, str] | None:
    text = (message or "").strip()
    if not text:
        return None

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


@app.post("/api/sessions/{session_id}/chat")
def chat_message(session_id: str, payload: ChatMessageRequest) -> dict:
    """统一聊天入口：普通对话与 Agent 修订动作共用一个接口。"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")

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
        return {
            "reply": "我还不能确定你是不是在请求修改内容。你可以直接说出要改哪里，或者用 /修订 + 修改意见 明确告诉我。",
            "note": revision.get("reason", "需要你进一步澄清修改意图。"),
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
            return {
                "reply": "我判断你这条消息像是在请求修改内容。请在对话里确认后再执行，我会按你的确认内容进行修订。",
                "note": "已识别到修改意图，等待你确认后执行。",
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
            return {
                "reply": "综述已根据你的反馈重新生成。",
                "note": "综述修订已完成。",
                "action_taken": True,
                "action": "revise_review",
                "confirmation_required": False,
                "session_state": fresh_session.get("state", ""),
                "session_state_label": STATE_LABELS.get(fresh_session.get("state", ""), fresh_session.get("state", "")),
                "draft": result.get("draft", fresh_session.get("draft", "")),
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
        return {
            "reply": "笔记已根据你的反馈修订。",
            "note": "笔记修订已完成。",
            "action_taken": True,
            "action": "revise_notes",
            "confirmation_required": False,
            "session_state": fresh_session.get("state", ""),
            "session_state_label": STATE_LABELS.get(fresh_session.get("state", ""), fresh_session.get("state", "")),
            "notes": revise_result.get("notes", ""),
        }

    reply_data = _build_chat_answer(session, message, payload.view_mode, payload.current_paper_id)
    return {
        "reply": reply_data["reply"],
        "note": reply_data.get("note", ""),
        "action_taken": False,
        "action": "chat",
        "confirmation_required": False,
        "session_state": session.get("state", ""),
        "session_state_label": STATE_LABELS.get(session.get("state", ""), session.get("state", "")),
    }


# ━━━━━ 草稿管理（第一波基础接口，完整功能在第三波）━━━━━

@app.get("/api/sessions/{session_id}/draft")
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

@app.put("/api/sessions/{session_id}/draft")
def save_draft(session_id: str, payload: dict) -> dict:
    """保存综述草稿编辑"""
    content = payload.get("content", "")
    try:
        session_mgr.save_draft(session_id, content)
        return {"message": "Success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  迭代三新增：Session 驱动的 Agent 执行端点
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RunPhaseRequest(BaseModel):
    topic: str
    start_phase: str = "plan"  # plan / search / write
    keywords: Optional[list[dict]] = None
    max_loops: int = 20


@app.post("/api/sessions/{session_id}/run/plan")
def run_plan_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段1】执行规划，生成关键词候选项"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    try:
        result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=payload.topic.strip(),
            start_phase="plan",
        )
        # 保存初始规划到 Session
        if result.get("initial_plan"):
            session_mgr.save_initial_plan(session_id, result["initial_plan"])
        # 保存关键词候选项
        if result.get("keywords"):
            session_mgr.save_keywords(session_id, result["keywords"])
        # 保存 Plan 阶段的 traces
        if result.get("traces"):
            session_mgr.save_traces(session_id, result["traces"])
        # 保持 planning 状态（Session 创建时已为此状态，无需再次转移）

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"规划阶段执行失败: {str(e)}")


def _run_search_in_background(session_id: str, topic: str, keywords: list[dict], max_loops: int) -> None:
    """后台执行搜索阶段，周期性保存 traces 供前端实时轮询"""
    import time as _time
    _stop_flag = False
    
    def _periodic_trace_saver():
        """每 3 秒将运行中的 traces 保存到 Session"""
        while not _stop_flag:
            _time.sleep(3)
            try:
                agent = _agent_holder.get("agent")
                traces = list(agent.traces) if agent else []
                if not traces:
                    with RUN_LOCK:
                        traces = list(RUNS.get(f"session_{session_id}", {}).get("traces", []))
                if traces:
                    session_mgr.save_traces(session_id, traces)
            except Exception:
                pass
    
    _saver_thread = threading.Thread(target=_periodic_trace_saver, daemon=True)
    _agent_holder = {}  # 用于捕获运行中 Agent 的引用
    
    try:
        # 更新 Session 状态为 searching（端点可能已更新，忽略重复异常）
        try:
            session_mgr.update_session_state(session_id, "searching")
        except ValueError:
            pass
        
        with RUN_LOCK:
            RUNS[f"session_{session_id}"] = {
                "status": "running",
                "phase": "searching",
                "traces": [],
            }
        
        _saver_thread.start()

        result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=topic,
            start_phase="search",
            user_keywords=keywords,
            max_loops=max_loops,
            agent_callback=lambda agent, wd: _agent_holder.update({"agent": agent}),
        )
        
        _stop_flag = True

        # 保存论文列表到 Session
        if result.get("papers"):
            session_mgr.save_papers_list(session_id, result["papers"])
        # 保存轨迹
        if result.get("traces"):
            session_mgr.save_traces(session_id, result["traces"])
        # 更新状态
        session_mgr.update_session_state(session_id, "search_complete")

        with RUN_LOCK:
            RUNS[f"session_{session_id}"] = {
                "status": "done",
                "phase": "search_complete",
                "traces": result.get("traces", []),
                "result": result,
            }

    except Exception as exc:
        _stop_flag = True
        with RUN_LOCK:
            RUNS[f"session_{session_id}"] = {
                "status": "error",
                "phase": "failed",
                "error": str(exc),
            }


@app.post("/api/sessions/{session_id}/run/search")
def run_search_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段2】执行搜索（后台运行，需轮询状态）"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    # 获取用户确认的关键词
    keywords = payload.keywords or session.get("keywords", [])
    if not keywords:
        raise HTTPException(status_code=400, detail="关键词不能为空，请先确认关键词")

    # 更新状态为 searching
    try:
        session_mgr.update_session_state(session_id, "searching")
    except ValueError:
        pass  # 状态可能已经是 searching

    # 后台执行
    worker = threading.Thread(
        target=_run_search_in_background,
        args=(session_id, payload.topic.strip(), keywords, payload.max_loops),
        daemon=True,
    )
    worker.start()

    return {
        "session_id": session_id,
        "status": "searching",
        "message": "搜索已开始，请通过 GET /api/sessions/{session_id} 轮询状态",
    }


@app.get("/api/sessions/{session_id}/run/status")
def get_session_run_status(session_id: str) -> dict:
    """获取 Session Agent 运行状态"""
    run_key = f"session_{session_id}"
    with RUN_LOCK:
        run = RUNS.get(run_key)
    if not run:
        return {"status": "unknown", "message": "无正在运行的任务"}
    return run


@app.post("/api/sessions/{session_id}/run/write")
def run_write_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段3】撰写综述（基于 Session 中的笔记）"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    notes = session.get("notes", "")
    # 如果 draft_notes.md 为空，尝试从 papers_list.json 中聚合各论文的笔记
    if not notes.strip():
        papers = session.get("papers", [])
        aggregated = []
        for p in papers:
            pn = (p.get("notes") or "").strip()
            if pn:
                aggregated.append(f"## {p.get('title', p.get('paper_id', ''))}\n\n{pn}")
        notes = "\n\n---\n\n".join(aggregated)
    
    if not notes.strip():
        raise HTTPException(status_code=400, detail="笔记为空，请先为选中论文生成笔记")

    previous_draft = session.get("draft", "")
    feedback = session_mgr.get_feedback(session_id)
    rewrite_count = session.get("rewrite_count", 0)

    try:
        from main import run_write_from_notes
        result = run_write_from_notes(
            user_topic=payload.topic.strip(),
            notes_content=notes,
            previous_draft=previous_draft,
            user_feedback=feedback,
            rewrite_count=rewrite_count,
        )

        # 保存草稿
        if result.get("draft"):
            session_mgr.save_draft(session_id, result["draft"])

        # 更新状态
        new_state = "reviewing_draft" if result.get("can_rewrite", True) else "complete"
        try:
            session_mgr.update_session_state(session_id, new_state)
        except ValueError:
            pass

        result["session_id"] = session_id
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"撰写阶段执行失败: {str(e)}")


# ━━━ 迭代三：关键词提取（新建会话前即可使用）━━━

class KeywordExtractRequest(BaseModel):
    topic: str

@app.post("/api/keywords/extract")
def extract_keywords(payload: KeywordExtractRequest) -> dict:
    """【辅助】仅提取关键词，不创建 Session"""
    from main import _build_initial_plan, _extract_keywords_from_plan
    from llms.client import LLMClient
    llm = LLMClient()
    plan = _build_initial_plan(llm, payload.topic.strip())
    keywords = _extract_keywords_from_plan(plan)
    return {"keywords": keywords, "plan": plan}

# ━━━ 迭代三新增：为选中论文生成独立笔记 ━━━

class RunNotesRequest(BaseModel):
    topic: str
    paper_ids: list[str]

@app.post("/api/sessions/{session_id}/run/notes")
def run_notes_phase(session_id: str, payload: RunNotesRequest) -> dict:
    """【阶段2b】为选中的每篇论文生成独立笔记"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    papers = session.get("papers", [])
    paper_ids = [pid.strip() for pid in payload.paper_ids if pid.strip()]
    if not paper_ids:
        raise HTTPException(status_code=400, detail="paper_ids 不能为空")

    from llms.client import LLMClient
    llm = LLMClient()
    topic = payload.topic.strip()
    notes_map = {}

    for paper in papers:
        pid = paper.get("paper_id", "")
        if pid not in paper_ids:
            continue
        try:
            import fitz
        except ImportError:
            raise HTTPException(status_code=500, detail="缺少依赖 PyMuPDF")

        title = paper.get("title", pid)
        abstract = paper.get("abstract", "")
        source_info = paper.get("source", "")
        if source_info == "agent_search":
            paper_path = session_mgr.get_agent_search_paper_path(session_id, pid)
        elif source_info == "user_custom":
            paper_path = session_mgr.get_user_custom_paper_path(session_id, pid)
        elif source_info == "user_upload":
            paper_path = session_mgr.get_user_upload_paper_path(session_id, title)
        try:
            doc = fitz.open(str(paper_path))
        except Exception:
            paper_path = None

#这里最好能将全文交给 LLM 来理解，而不是只提取前几页的文本。
        res_text = ""
        if paper_path:
            try:
                doc = fitz.open(str(paper_path))
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



        note_prompt = f"""你是一名严谨的学术研究员。请为以下论文撰写一份**深度学术笔记**（800-1200字），使其能够直接支撑后续的综述写作。


论文原文（前几页）：
{res_text}

请按以下详细格式输出：

## 论文笔记：{title}

- **核心方法**：（详细描述该论文提出的技术核心。至少 150 字。）

- **实验设置**：（详细说明改论文的实验设计。至少 80 字。）

- **关键结果**：（详细列出主要实验结果。 至少 100 字。）

- **消融与分析**：（论文是否做了消融实验？是否有可视化分析或案例研究？至少 80 字。）

- **与研究主题的关联**：（具体说明该论文如何支撑「{topic}」的研究，填补了什么空白，或者提供了什么新视角。至少 60 字。）

- **亮点与不足**：（客观评价论文的主要贡献、创新性以及潜在局限、未解决的问题。至少 60 字。）

写作要求：内容具体、引用数值，避免空洞概括。直接输出笔记，不要额外解释。"""

        try:
            note_text = llm.chat("你是严谨的学术研究员。", note_prompt, []).strip()
            notes_map[pid] = note_text
        except Exception as e:
            notes_map[pid] = f"## 论文笔记：{title}\n\n生成笔记时出错：{str(e)}"

    if notes_map:
        session_mgr.batch_update_paper_notes(session_id, notes_map)

    return {
        "phase": "notes",
        "notes_map": notes_map,
        "count": len(notes_map),
    }

class ReviseNotesRequest(BaseModel):
    topic: str
    feedback: str
    paper_id: str | None = None

@app.post("/api/sessions/{session_id}/run/notes/revise")
def revise_notes_phase(session_id: str, payload: ReviseNotesRequest) -> dict:
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    
    # 优先获取论文独立笔记，否则获取整体笔记
    notes = ""
    is_paper_notes = False
    if payload.paper_id:
        papers = session.get("papers", [])
        for p in papers:
            if p.get("paper_id") == payload.paper_id:
                notes = p.get("notes", "")
                is_paper_notes = True
                break
    
    if not notes:
        notes = session.get("notes", "")
        is_paper_notes = False

    if not notes.strip():
        raise HTTPException(status_code=400, detail="笔记为空，无法修订")
    
    from llms.client import LLMClient
    llm = LLMClient()
    
    revise_prompt = f"""你是一名严谨的学术研究员。请根据用户的反馈意见，对现有的研究笔记进行修订。
    
研究主题：{payload.topic}

【用户反馈意见】：
{payload.feedback}

【现有研究笔记】：
{notes}

请按照用户的反馈意见修改现有研究笔记，输出修改后的完整笔记内容，不要保留未修改部分的省略号，不要输出额外的解释。
"""
    try:
        new_notes = llm.chat("你是学术笔记修改专家。", revise_prompt, []).strip()
        
        if is_paper_notes and payload.paper_id:
            session_mgr.batch_update_paper_notes(session_id, {payload.paper_id: new_notes})
        else:
            session_mgr.save_notes(session_id, new_notes)
            
        return {"notes": new_notes, "message": "笔记已根据反馈修订"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"笔记修订执行失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    print("\n🚀 Academic Agent Web 服务即将启动...")
    print("👉 请在浏览器中打开: http://127.0.0.1:8000\n")
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
