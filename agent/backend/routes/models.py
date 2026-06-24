"""
共享 Pydantic 模型：被多个路由模块使用。
"""
from typing import Optional
from pydantic import BaseModel


class RunRequest(BaseModel):
    topic: str = "LLM Agent Memory"
    max_loops: int = 20


class RunResponse(BaseModel):
    topic: str
    researcher_result: str
    writer_result: str
    traces: list
    output_file: str


class RunStartResponse(BaseModel):
    run_id: str


class RunStatusResponse(BaseModel):
    run_id: str
    topic: str
    phase: str
    status: str
    traces: list
    researcher_result: str
    writer_result: str
    output_file: str
    error: str
    failure_summary: dict
    papers: list[str] = []


class ChatMessageRequest(BaseModel):
    message: str
    view_mode: str = "summary"
    chat_mode: str = "normal"
    current_paper_id: str | None = None
    conv_id: str | None = None
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


class RunPhaseRequest(BaseModel):
    topic: str
    start_phase: str = "plan"
    keywords: Optional[list] = None
    max_loops: int = 20
    min_papers: int = 3


class RunNotesRequest(BaseModel):
    topic: str
    paper_ids: list[str]


class ReviseNotesRequest(BaseModel):
    topic: str
    feedback: str
    paper_id: str | None = None


class AutoRunRequest(BaseModel):
    topic: str
    max_loops: int = 20
    min_papers: int = 3


class AnalysisRequest(BaseModel):
    topic: str
    analysis_type: str = "all"


class UpdateStateRequest(BaseModel):
    state: str


class UpdateKeywordsRequest(BaseModel):
    keywords: list


class SaveFeedbackRequest(BaseModel):
    feedback: str


class AddCustomPaperRequest(BaseModel):
    paper_id: str


class UpdatePaperStatusRequest(BaseModel):
    status: str = "pending"


class CreateSessionRequest(BaseModel):
    topic: str
    keywords: Optional[list] = None

