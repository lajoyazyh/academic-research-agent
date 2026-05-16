import threading
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from main import run_agent_pipeline


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DOCS_DIR = BASE_DIR / "documents"


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


@app.get("/")
def index() -> HTMLResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


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


@app.get("/api/agent/document/{filename}/papers/{pdf_name}")
def get_pdf(filename: str, pdf_name: str) -> FileResponse:
    if "/" in filename or "\\" in filename or "/" in pdf_name or "\\" in pdf_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

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
            RUNS[run_id]["researcher_result"] = res["researcher_result"]
            RUNS[run_id]["writer_result"] = res["writer_result"]
            RUNS[run_id]["output_file"] = res["output_file"]

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


if __name__ == "__main__":
    import uvicorn

    print("\n🚀 Academic Agent Web 服务即将启动...")
    print("👉 请在浏览器中打开: http://127.0.0.1:8000\n")
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
