"""API for the protocol-driven scientific review workflow."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.provider import ensure_provider_available
from backend.routes.deps import session_mgr
from backend.routes.models import ProviderConfig
from backend.scientific_review import (
    EXCLUSION_CODES,
    REVIEW_MODES,
    SCIENTIFIC_SKILL_MANIFESTS,
    ScientificReviewService,
    deterministic_evidence_seed,
)
from llms.client import LLMClient
from utils.parser import extract_json


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
    search_field_scope: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    search_strategy: dict[str, Any] | None = None
    screening_policy: dict[str, Any] | None = None
    evidence_hierarchy_policy: dict[str, Any] | None = None
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
    actor_type: str | None = None
    actor_id: str | None = None
    model_version: str | None = None
    blinded_to_peer: bool = False
    supersedes_decision_id: str | None = None


class BatchScreeningRequest(BaseModel):
    items: list[ScreeningRequest]


class AIScreeningRequest(BaseModel):
    paper_ids: list[str]
    stage: str
    provider: ProviderConfig


class ConflictResolutionRequest(BaseModel):
    paper_id: str
    stage: str
    decision: str
    reason_code: str | None = None
    reason: str
    actor_id: str = "human"


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


@router.post("/{session_id}/screening/ai-review")
def run_independent_ai_screening(session_id: str, payload: AIScreeningRequest) -> dict:
    if payload.stage not in {"title_abstract", "full_text"}:
        raise HTTPException(status_code=400, detail="Unsupported screening stage")
    service = _service(session_id)
    protocol = service.ensure_protocol(session_id)
    provider = ensure_provider_available(payload.provider)
    llm = LLMClient(provider)
    candidates = {
        str(item.get("paper_id")): item
        for item in service._read(session_id, "candidates.json", [])
    }
    papers = {
        str(item.get("paper_id")): item
        for item in session_mgr.get_papers(session_id)
    }
    corpus = []
    for paper_id in payload.paper_ids:
        candidate = candidates.get(paper_id, {})
        paper = papers.get(paper_id, {})
        if not candidate and not paper:
            raise HTTPException(status_code=400, detail=f"Paper {paper_id} does not exist")
        evidence_text = (
            str(paper.get("notes") or "")
            if payload.stage == "full_text"
            else str(candidate.get("abstract") or paper.get("abstract") or "")
        )
        corpus.append({
            "paper_id": paper_id,
            "title": candidate.get("title") or paper.get("title"),
            "abstract_or_fulltext_evidence": evidence_text[:18000],
            "evidence_basis": paper.get("evidence_basis") or "unknown",
        })
    schema = {
        "items": [{
            "paper_id": "",
            "decision": "include|exclude|uncertain",
            "reason_code": None,
            "reason": "",
            "criterion_judgements": [{
                "criterion": "",
                "judgement": "met|not_met|uncertain",
                "evidence": "",
            }],
            "evidence": [{"section": None, "page": None, "excerpt": ""}],
            "confidence": 0.0,
        }]
    }
    is_en = str(protocol.get("language") or "").startswith("en")
    system = (
        "You are an independent screening reviewer. You cannot see the human review. "
        "Apply every locked criterion conservatively and return JSON only."
        if is_en else
        "你是独立筛选复核员，不能读取人工筛选决定。必须逐条保守应用已锁定标准，只返回JSON。"
    )
    prompt = (
        f"Protocol:\n{protocol}\n\nStage: {payload.stage}\n\nRecords:\n{corpus}\n\n"
        f"Return:\n{schema}\n\n"
        "Use uncertain when the supplied evidence is insufficient. An exclusion requires one of: "
        + ", ".join(sorted(EXCLUSION_CODES))
    )
    try:
        parsed = extract_json(llm.chat(system, prompt, []))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI screening failed: {exc}") from exc
    valid_ids = set(payload.paper_ids)
    records = []
    for item in parsed.get("items") or []:
        paper_id = str(item.get("paper_id") or "")
        if paper_id not in valid_ids:
            continue
        decision = str(item.get("decision") or "uncertain")
        reason_code = item.get("reason_code")
        if decision == "exclude" and reason_code not in EXCLUSION_CODES:
            reason_code = "other"
        records.append(service.record_screening(
            session_id,
            paper_id=paper_id,
            stage=payload.stage,
            decision=decision if decision in {"include", "exclude", "uncertain"} else "uncertain",
            reason_code=reason_code,
            reason=str(item.get("reason") or ""),
            criterion_judgements=item.get("criterion_judgements") or [],
            evidence=item.get("evidence") or [],
            confidence=item.get("confidence"),
            reviewer="ai",
            actor_type="ai",
            actor_id="independent_ai",
            model_version=provider.get("chat_model") or provider.get("model"),
            blinded_to_peer=True,
        ))
    missing = valid_ids - {str(item.get("paper_id")) for item in records}
    for paper_id in sorted(missing):
        records.append(service.record_screening(
            session_id,
            paper_id=paper_id,
            stage=payload.stage,
            decision="uncertain",
            reason="AI response did not contain a valid decision for this record.",
            confidence=0.0,
            reviewer="ai",
            actor_type="ai",
            actor_id="independent_ai",
            model_version=provider.get("chat_model") or provider.get("model"),
            blinded_to_peer=True,
        ))
    return {
        "items": records,
        "conflicts": service.screening_conflicts(session_id),
        "flow": service.flow_counts(session_id),
    }


@router.get("/{session_id}/screening/conflicts")
def list_screening_conflicts(session_id: str) -> dict:
    service = _service(session_id)
    return {"items": service.screening_conflicts(session_id)}


@router.post("/{session_id}/screening/conflicts/resolve")
def resolve_screening_conflict(session_id: str, payload: ConflictResolutionRequest) -> dict:
    try:
        service = _service(session_id)
        decision = service.resolve_screening_conflict(
            session_id,
            **payload.model_dump(),
        )
        return {
            "decision": decision,
            "conflicts": service.screening_conflicts(session_id),
            "flow": service.flow_counts(session_id),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.get("/{session_id}/review-artifacts")
def review_artifacts(session_id: str) -> dict:
    service = _service(session_id)
    protocol = service.ensure_protocol(session_id)
    snapshot = service.latest_inclusion_snapshot(session_id) or {}
    selected = set(snapshot.get("paper_ids") or [])
    papers = [
        paper for paper in session_mgr.get_papers(session_id)
        if paper.get("paper_id") in selected
    ]
    language = protocol.get("language", "zh-CN")
    return {
        "methodology_markdown": service.build_methodology_markdown(session_id, language),
        "technical_artifacts_markdown": service.build_technical_artifacts_markdown(
            session_id, papers, language
        ),
        "references_markdown": service.format_ieee_references(papers, language),
        "methodology_report": service.methodology_report(session_id),
    }
