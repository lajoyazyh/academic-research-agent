"""API for the protocol-driven scientific review workflow."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.routes.deps import session_mgr
from backend.scientific_review import (
    EXCLUSION_CODES,
    REVIEW_MODES,
    SCIENTIFIC_SKILL_MANIFESTS,
    ScientificReviewService,
    deterministic_evidence_seed,
)


router = APIRouter(prefix="/api/sessions", tags=["scientific-review"])


class ProtocolUpdate(BaseModel):
    mode: str | None = None
    language: str | None = None
    research_question: str | None = None
    framework: str | None = None
    candidate_cap: int | None = Field(default=None, ge=30, le=2000)
    sources: list[str] | None = None
    languages: list[str] | None = None
    document_types: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    inclusion_criteria: list[str] | None = None
    exclusion_criteria: list[str] | None = None
    extraction_fields: list[str] | None = None
    primary_outcomes: list[str] | None = None
    comparison_dimensions: list[str] | None = None
    appraisal_profile: str | None = None
    synthesis_method: str | None = None


class ModeSwitchRequest(BaseModel):
    mode: str
    candidate_cap: int | None = Field(default=None, ge=30, le=2000)
    language: str | None = None


class ScreeningRequest(BaseModel):
    paper_id: str
    stage: str
    decision: str
    reason_code: str | None = None
    reason: str = ""
    criterion_judgements: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reviewer: str = "human"


class BatchScreeningRequest(BaseModel):
    items: list[ScreeningRequest]


class InclusionSnapshotRequest(BaseModel):
    paper_ids: list[str]


class ExtractionRequest(BaseModel):
    paper_id: str
    fields: dict[str, Any]


class AppraisalRequest(BaseModel):
    paper_id: str
    appraisal: dict[str, Any]


def _service(session_id: str) -> ScientificReviewService:
    if not session_mgr.load_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return ScientificReviewService(session_mgr)


@router.get("/scientific/catalog")
def scientific_catalog() -> dict:
    return {
        "review_modes": REVIEW_MODES,
        "screening_exclusion_codes": sorted(EXCLUSION_CODES),
        "skill_manifests": SCIENTIFIC_SKILL_MANIFESTS,
    }


@router.get("/{session_id}/scientific")
def get_scientific_state(session_id: str) -> dict:
    return _service(session_id).audit_summary(session_id)


@router.get("/{session_id}/protocol")
def get_protocol(session_id: str) -> dict:
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return ScientificReviewService(session_mgr).ensure_protocol(
        session_id,
        topic=session.get("topic", ""),
    )


@router.put("/{session_id}/protocol")
def update_protocol(session_id: str, payload: ProtocolUpdate) -> dict:
    try:
        changes = payload.model_dump(exclude_none=True)
        return _service(session_id).update_protocol(session_id, changes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/protocol/confirm")
def confirm_protocol(session_id: str) -> dict:
    try:
        return _service(session_id).confirm_protocol(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/protocol/version")
def version_protocol(session_id: str, payload: ModeSwitchRequest) -> dict:
    try:
        return _service(session_id).version_for_mode(
            session_id,
            mode=payload.mode,
            candidate_cap=payload.candidate_cap,
            language=payload.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}/candidates")
def list_candidates(session_id: str) -> dict:
    service = _service(session_id)
    return {
        "items": service._read(session_id, "candidates.json", []),
        "flow": service.flow_counts(session_id),
    }


@router.post("/{session_id}/screening")
def record_screening(session_id: str, payload: ScreeningRequest) -> dict:
    try:
        service = _service(session_id)
        result = service.record_screening(session_id, **payload.model_dump())
        if payload.stage == "full_text":
            status = "accepted" if payload.decision == "include" else (
                "rejected" if payload.decision == "exclude" else "pending"
            )
            session_mgr.update_paper_status(session_id, payload.paper_id, status)
        return {"decision": result, "flow": service.flow_counts(session_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/screening/batch")
def record_screening_batch(session_id: str, payload: BatchScreeningRequest) -> dict:
    service = _service(session_id)
    results = []
    try:
        for item in payload.items:
            results.append(service.record_screening(session_id, **item.model_dump()))
            if item.stage == "full_text":
                status = "accepted" if item.decision == "include" else (
                    "rejected" if item.decision == "exclude" else "pending"
                )
                session_mgr.update_paper_status(session_id, item.paper_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": results, "flow": service.flow_counts(session_id)}


@router.post("/{session_id}/inclusion-snapshots/confirm")
def confirm_inclusion_snapshot(session_id: str, payload: InclusionSnapshotRequest) -> dict:
    try:
        service = _service(session_id)
        snapshot = service.confirm_inclusion_snapshot(session_id, payload.paper_ids)
        for paper in session_mgr.get_papers(session_id):
            target = "accepted" if paper.get("paper_id") in payload.paper_ids else "rejected"
            if target != paper.get("status"):
                session_mgr.update_paper_status(session_id, paper.get("paper_id", ""), target)
        return {"snapshot": snapshot, "flow": service.flow_counts(session_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{session_id}/extractions")
def save_extraction(session_id: str, payload: ExtractionRequest) -> dict:
    try:
        return _service(session_id).save_extraction(session_id, payload.paper_id, payload.fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/extractions/seed")
def seed_extractions(session_id: str, payload: InclusionSnapshotRequest) -> dict:
    service = _service(session_id)
    papers = {
        paper.get("paper_id"): paper
        for paper in session_mgr.get_papers(session_id)
    }
    records = []
    for paper_id in payload.paper_ids:
        paper = papers.get(paper_id)
        if not paper:
            raise HTTPException(status_code=400, detail=f"Paper {paper_id} does not exist")
        records.append(service.save_extraction(session_id, paper_id, deterministic_evidence_seed(paper)))
    return {"items": records, "count": len(records)}


@router.put("/{session_id}/appraisals")
def save_appraisal(session_id: str, payload: AppraisalRequest) -> dict:
    try:
        return _service(session_id).save_appraisal(session_id, payload.paper_id, payload.appraisal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}/methodology-audit")
def methodology_audit(session_id: str) -> dict:
    return _service(session_id).audit_summary(session_id)
