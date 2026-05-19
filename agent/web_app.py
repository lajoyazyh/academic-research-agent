import threading
import uuid
import json
import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from main import run_agent_pipeline, run_agent_pipeline_session
from backend.session_manager import SessionManager, SessionState, STATE_LABELS, VALID_TRANSITIONS


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
            runs.append({"filename": d.name, "size": size})

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

    session_papers.append({
        "paper_id": clean_id,
        "title": paper_title,
        "source": "user_custom",
        "status": "accepted"
    })
    session_mgr.save_papers_list(session_id, session_papers)

    from llms.client import LLMClient
    llm = LLMClient()
    topic = session.get("metadata", {}).get("topic", "")
    
    summarize_prompt = f"""你是一名擅长文献总结的研究员。这里是用户上传的一篇新论文的初步文本内容。研究主题是《{topic}》。
请你认真阅读后，提炼出这篇论文的关键发现、方法或指标，并撰写一段学术笔记（约 300-500 字）。

论文原文（前几页）：
{res_text}

请直接输出你的高质量学术笔记：
"""
    new_note = llm.chat("你是深度的学术研究员。", summarize_prompt, []).strip()

    old_notes = session.get("notes", "")
    updated_notes = old_notes + f"\n\n## 追加参考文献: {paper_id}\n\n{new_note}\n\n---\n"
    session_mgr.save_notes(session_id, updated_notes)
    
    return {"message": "Success", "notes": updated_notes, "draft": session.get("draft", "")}


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
    try:
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
        # 保存笔记（从 result 中获取，run_search_only 已正确读取）
        if result.get("notes"):
            session_mgr.save_notes(session_id, result["notes"])
        # 也从 work_dir 的 research_notes.md 二次确认
        work_dir = SESSIONS_DIR / session_id
        notes_file = work_dir / "research_notes.md"
        if notes_file.exists() and not result.get("notes"):
            session_mgr.save_notes(session_id, notes_file.read_text(encoding="utf-8"))
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
    if not notes.strip():
        raise HTTPException(status_code=400, detail="笔记为空，请先完成搜索阶段")

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

        title = paper.get("title", pid)
        abstract = paper.get("abstract", "")
        source_info = paper.get("source_type", paper.get("source", ""))

        note_prompt = f"""你是一名学术研究员。请为以下论文撰写一份结构化的学术笔记（300-500字）：

研究主题：{topic}
论文标题：{title}
来源：{source_info}
摘要：{abstract}

请按以下格式输出：
## 论文笔记：{title}
- **核心方法**：（简述该论文使用的核心技术或方法）
- **关键发现**：（列出最重要的实验发现或结论）
- **与研究主题的关联**：（说明该论文如何与「{topic}」相关联）
- **亮点与不足**：（简要评价论文的贡献和局限）

直接输出笔记内容，不要额外解释。"""

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


if __name__ == "__main__":
    import uvicorn

    print("\n🚀 Academic Agent Web 服务即将启动...")
    print("👉 请在浏览器中打开: http://127.0.0.1:8000\n")
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
