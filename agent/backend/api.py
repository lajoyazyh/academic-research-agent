import os
import sys
import uuid
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# 由于现在文件放在了 backend 目录下，路径层级要变一下
CURRENT_DIR = Path(__file__).resolve().parent
AGENT_DIR = CURRENT_DIR.parent
ITERATION_ROOT = AGENT_DIR.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from main import run_agent_pipeline


class RunAgentRequest(BaseModel):
    topic: str = Field(default="LLM Agent Memory", min_length=2)
    max_loops: int = Field(default=20, ge=3, le=40)

class RunStartResponse(BaseModel):
    run_id: str
    status: str

class RunStatusResponse(BaseModel):
    run_id: str
    topic: str
    phase: str
    status: str
    traces: list[dict[str, Any]]
    researcher_result: str
    writer_result: str
    output_file: str
    error: str
    papers: list[str] = []
    failure_summary: dict[str, int] = {}

app = FastAPI(title="Academic Agent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = AGENT_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def index():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/api/agent/history")
def get_history() -> list[dict[str, Any]]:
    docs_dir = AGENT_DIR / "documents"
    if not docs_dir.exists():
        return []
    runs = []
    for d in docs_dir.iterdir():
        if d.is_dir():
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
def get_history_detail(filename: str) -> dict[str, Any]:
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    run_dir = AGENT_DIR / "documents" / filename
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
        content += "\\n\\n---\\n\\n## 📔 原始研究笔记 (Research Notes)\\n\\n" + res_notes
        
    return {
        "filename": filename, 
        "content": content, 
        "writer_result": writer_res, 
        "researcher_result": res_notes,
        "papers": papers
    }

from fastapi.responses import FileResponse

@app.get("/api/agent/document/{filename}/papers/{pdf_name}")
def get_pdf(filename: str, pdf_name: str):
    if "/" in filename or "\\" in filename or "/" in pdf_name or "\\" in pdf_name:
        raise HTTPException(status_code=400, detail="Invalid filename")
        
    pdf_path = AGENT_DIR / "documents" / filename / "papers" / pdf_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
        
    return FileResponse(pdf_path, media_type="application/pdf")
RUNS = {}
RUN_LOCK = threading.Lock()


def _summarize_failures_from_traces(traces: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for step in traces:
        if not isinstance(step, dict):
            continue
        error_type = str(step.get("error_type", "") or "").strip()
        if not error_type:
            continue
        summary[error_type] = summary.get(error_type, 0) + 1
    return summary

def agent_background_task(run_id: str, topic: str, max_loops: int):
    # 通过这个回调，把 agent 实例注入到全局并发字典，从而被前端轮询 trace
    def on_agent_created(agent, work_dir):
        with RUN_LOCK:
            if run_id in RUNS:
                RUNS[run_id]['agent_ref'] = agent
                RUNS[run_id]['work_dir'] = work_dir

    try:
        with RUN_LOCK:
            RUNS[run_id]['status'] = 'running'
            RUNS[run_id]['phase'] = 'researcher'

        res = run_agent_pipeline(user_topic=topic, max_loops=max_loops, agent_callback=on_agent_created)
        
        with RUN_LOCK:
            RUNS[run_id]['phase'] = 'done'
            RUNS[run_id]['status'] = 'done'
            RUNS[run_id]['researcher_result'] = res['researcher_result']
            RUNS[run_id]['writer_result'] = res['writer_result']
            RUNS[run_id]['output_file'] = res['output_file']

    except Exception as e:
        with RUN_LOCK:
            RUNS[run_id]['status'] = 'error'
            RUNS[run_id]['error'] = str(e)


@app.post("/api/run/start", response_model=RunStartResponse)
def start_run(payload: RunAgentRequest, background_tasks: BackgroundTasks) -> RunStartResponse:
    run_id = uuid.uuid4().hex
    with RUN_LOCK:
        RUNS[run_id] = {
            'run_id': run_id,
            'topic': payload.topic.strip(),
            'phase': 'queued',
            'status': 'queued',
            'traces': [],
            'researcher_result': '',
            'writer_result': '',
            'output_file': '',
            'error': '',
            'agent_ref': None,
        }
    
    background_tasks.add_task(agent_background_task, run_id, payload.topic.strip(), payload.max_loops)
    return RunStartResponse(run_id=run_id, status='started')

@app.get("/api/run/{run_id}", response_model=RunStatusResponse)
def get_run_status(run_id: str) -> RunStatusResponse:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run_id not found")
        
        traces = list(run['agent_ref'].traces) if run.get('agent_ref') else []
        
        # 动态尝试读取草稿本内容，让前端能实时看到笔记情况
        current_notes = run.get('researcher_result', '')
        if run['status'] == 'running' and 'work_dir' in run:
            note_path = os.path.join(run['work_dir'], 'research_notes.md')
            if os.path.exists(note_path):
                with open(note_path, 'r', encoding='utf-8') as f:
                    current_notes = f.read()

        # 动态尝试读取已下载的论文 PDF
        papers = []
        if 'work_dir' in run:
            papers_dir = os.path.join(run['work_dir'], 'papers')
            if os.path.exists(papers_dir):
                for p in os.listdir(papers_dir):
                    if p.endswith('.pdf'):
                        papers.append(p)

        failure_summary = _summarize_failures_from_traces(traces)

        return RunStatusResponse(
            run_id=run['run_id'],
            topic=run['topic'],
            phase=run['phase'],
            status=run['status'],
            traces=traces,
            researcher_result=current_notes,
            writer_result=run.get('writer_result', ''),
            output_file=run.get('output_file', ''),
            error=run.get('error', ''),
            papers=papers,
            failure_summary=failure_summary,
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)

