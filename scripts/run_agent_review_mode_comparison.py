"""Generate a strict/non-strict review pair through the product Agent.

The comparison intentionally reuses the immutable discovery and full-text
evidence collected by the 2026-07-31 RAG live trial.  It does *not* reuse the
old review prose or screening decisions.  Each mode gets a fresh protocol,
fresh Zhipu title/full-text screening, a fresh inclusion snapshot, and a fresh
call through ``run_write_phase`` / ``run_write_from_notes``.

The request-scoped API key is read from the gitignored ``.env`` file and is
never serialized into the comparison artifacts.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "agent"))

from backend.artifact_export import _docx_bytes, _pdf_bytes, markdown_to_html  # noqa: E402
from backend.routes import agent as agent_routes  # noqa: E402
from backend.routes import scientific_review as scientific_routes  # noqa: E402
from backend.routes.models import ProviderConfig, RunPhaseRequest  # noqa: E402
from backend.routes.scientific_review import AIScreeningRequest  # noqa: E402
from backend.scientific_review import ScientificReviewService  # noqa: E402
from backend.session_manager import SessionManager  # noqa: E402


SOURCE_SESSION = (
    ROOT
    / "artifacts"
    / "methodology-depth-live-trials-2026-07-31-v5"
    / ".runtime_sessions"
    / "sess_20260731_134606_5fcd21"
)
OUTPUT_ROOT = ROOT / "artifacts" / "agent-review-mode-comparison-2026-07-31"
RUNTIME_ROOT = OUTPUT_ROOT / ".runtime_sessions"
MODEL = os.getenv("ZHIPU_MODEL", "glm-4.7-flash")
BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
QUESTION = (
    "检索增强生成系统在静态、迭代、按需与纠错式检索机制、可靠性评价、"
    "实验公平性和计算成本方面有哪些可验证证据与适用边界？"
)
TITLE = "检索增强生成的架构、评价与可靠性证据综述"
INCLUSION = [
    "直接研究RAG架构、检索控制、可靠性评价或计算成本",
    "提供原始实验、基准或具有实证验证的技术框架",
    "综述文章仅用于分类与研究版图，不得支撑性能或成本结论",
    "能够获得足以核验机制和结果的全文",
]
EXCLUSION = [
    "研究问题与RAG机制、评价、可靠性或成本无直接关系",
    "只有观点或产品描述而无可核验技术证据",
    "缺少可用全文，无法完成依赖全文的筛选与质量评价",
]
MODES = {
    "systematic": {
        "directory": "strict-systematic",
        "display_name": "严格模式（systematic）",
    },
    "rapid": {
        "directory": "non-strict-rapid",
        "display_name": "非严格模式（rapid）",
    },
}


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def provider() -> ProviderConfig:
    api_key = str(os.getenv("ZHIPU_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("ZHIPU_API_KEY is missing from the environment or .env")
    return ProviderConfig(
        provider_id="zhipu",
        api_key=api_key,
        base_url=BASE_URL,
        chat_model=MODEL,
        embedding_model="",
        language="zh-CN",
    )


def retry_agent_call(label: str, call: Callable[[], Any]) -> Any:
    deadline = time.monotonic() + float(os.getenv("TRIAL_RETRY_WINDOW_SECONDS", "900"))
    delay = 8.0
    while True:
        try:
            return call()
        except Exception as exc:
            message = str(getattr(exc, "detail", exc)).lower()
            retryable = getattr(exc, "status_code", None) in {429, 500, 502, 503} or any(
                token in message
                for token in (
                    "429",
                    "too many requests",
                    "timeout",
                    "timed out",
                    "connection",
                    "502",
                    "503",
                    "500",
                )
            )
            remaining = deadline - time.monotonic()
            if not retryable or remaining <= 0:
                raise
            pause = min(delay, 60.0, remaining)
            print(
                f"[{label}] transient provider error ({message[:220]}); "
                f"retrying in {pause:.0f}s",
                flush=True,
            )
            time.sleep(pause)
            delay = min(delay * 2, 60.0)


def compact_note(extraction: dict) -> str:
    allowed = {
        "paper_id",
        "study_design",
        "study_or_article_type",
        "evidence_level",
        "population_or_dataset",
        "intervention_or_method",
        "comparator_or_baseline",
        "sample_size",
        "outcomes_and_metrics",
        "main_results",
        "quantitative_results",
        "technical_mechanism",
        "limitations",
        "funding_and_conflicts",
        "evidence_locations",
        "computer_ai",
        "evidence_basis",
        "confidence",
        "review_status",
    }
    value = {key: extraction.get(key) for key in allowed if key in extraction}
    return "结构化全文证据卡（Agent 写作的唯一事实输入之一）：\n" + json.dumps(
        value, ensure_ascii=False, indent=2
    )


def initialize_mode(
    manager: SessionManager,
    mode: str,
) -> tuple[str, ScientificReviewService, Path]:
    case_dir = OUTPUT_ROOT / MODES[mode]["directory"]
    state_path = case_dir / "runtime_state.json"
    state = read_json(state_path, {})
    if state.get("session_id") and manager.load_session(state["session_id"]):
        return state["session_id"], ScientificReviewService(manager), case_dir

    session = manager.create_session(f"{TITLE}｜{MODES[mode]['display_name']}")
    session_id = session["session_id"]
    service = ScientificReviewService(manager)
    protocol = service.update_protocol(
        session_id,
        {
            "mode": mode,
            "language": "zh-CN",
            "research_question": QUESTION,
            "framework": "PICOC（计算机与AI技术问题）",
            "candidate_cap": 100,
            "sources": ["arxiv", "crossref", "dblp"],
            "languages": ["English"],
            "document_types": ["journal article", "conference paper", "preprint"],
            "search_field_scope": ["title", "abstract", "keywords"],
            "date_from": "2020-01-01",
            "date_to": "2026-07-31",
            "inclusion_criteria": INCLUSION,
            "exclusion_criteria": EXCLUSION,
            "appraisal_profile": "computer_ai",
            "synthesis_method": "SWiM structured narrative synthesis",
            "screening_policy": {
                "title_abstract": "independent AI screening; uncertain records retained",
                "full_text": "independent AI screening over structured full-text evidence",
                "conflict_resolution": "human adjudication required; not performed in this automated test",
                "test_operator_confirmation": False,
            },
            "evidence_hierarchy_policy": {
                "primary_required_for": [
                    "performance",
                    "cost",
                    "mechanism effectiveness",
                    "practice recommendation",
                ],
                "secondary_allowed_for": ["background", "taxonomy", "research landscape"],
            },
        },
    )
    protocol = service.confirm_protocol(session_id)

    source_candidates = read_json(SOURCE_SESSION / "methodology" / "candidates.json", [])
    source_queries = read_json(SOURCE_SESSION / "methodology" / "search_queries.json", [])
    source_runs = read_json(SOURCE_SESSION / "plan" / "search_runs.json", [])
    source_papers = {
        str(item.get("paper_id")): item
        for item in read_json(SOURCE_SESSION / "papers" / "papers_list.json", [])
    }
    source_extractions = {
        str(item.get("paper_id")): item
        for item in read_json(SOURCE_SESSION / "methodology" / "extractions.json", [])
    }

    for item in source_candidates:
        service.register_candidate(session_id, item)

    copied_queries = []
    for item in source_queries:
        copied = dict(item)
        copied["protocol_id"] = protocol["protocol_id"]
        copied["protocol_version"] = protocol["version"]
        copied_queries.append(copied)
    service._write(session_id, "search_queries.json", copied_queries)

    for run in source_runs:
        copied = dict(run)
        copied["run_id"] = f"reused_discovery_{mode}_{dt.datetime.now().strftime('%H%M%S')}"
        copied["protocol_id"] = protocol["protocol_id"]
        copied["protocol_version"] = protocol["version"]
        copied["reuse_disclosure"] = (
            "Immutable candidate discovery from the 2026-07-31 live RAG trial; "
            "screening and writing are rerun for this protocol."
        )
        manager.save_search_run(session_id, copied)

    # Only records with previously extracted full text become full-text papers.
    # Their prose notes are replaced by compact structured evidence so the old
    # review draft can never leak into the fresh Agent generation.
    for paper_id, extraction in source_extractions.items():
        source_paper = source_papers.get(paper_id, {})
        manager.add_paper(
            session_id,
            {
                **source_paper,
                "paper_id": paper_id,
                "status": "pending",
                "notes": compact_note(extraction),
                "has_notes": True,
                "evidence_basis": "full_text",
                "pdf_status": "not_retained",
                "pdf_error": "Source PDF removed after the prior extraction run.",
            },
        )

    write_json(
        state_path,
        {
            "session_id": session_id,
            "mode": mode,
            "model": MODEL,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "api_key_retained": False,
            "old_review_reused": False,
        },
    )
    return session_id, service, case_dir


def screen_mode(
    manager: SessionManager,
    service: ScientificReviewService,
    session_id: str,
    mode: str,
    provider_config: ProviderConfig,
) -> list[str]:
    candidates = service._read(session_id, "candidates.json", [])
    existing = service._read(session_id, "screening_decisions.json", [])
    snapshot = service.latest_inclusion_snapshot(session_id)
    if snapshot:
        archive = service._read(session_id, "invalid_screening_responses.json", [])
        existing_ids = {str(item.get("decision_id")) for item in existing}
        restorable = [
            item for item in archive
            if item.get("model_version") == "glm-z1-flash"
            and item.get("criterion_judgements")
            and str(item.get("decision_id")) not in existing_ids
        ]
        if restorable:
            existing.extend(restorable)
            service._write(session_id, "screening_decisions.json", existing)
            restored_ids = {str(item.get("decision_id")) for item in restorable}
            service._write(
                session_id,
                "invalid_screening_responses.json",
                [item for item in archive if str(item.get("decision_id")) not in restored_ids],
            )
            print(
                f"[{mode}] restored {len(restorable)} valid model screening decisions from archive",
                flush=True,
            )
        return list(snapshot.get("paper_ids") or [])
    title_existing = [
        item for item in existing
        if item.get("stage") == "title_abstract" and item.get("actor_type") == "ai"
    ]
    invalid_reasons = {
        "",
        "AI response did not contain a valid decision for this record.",
    }
    invalid_title_existing = [
        item for item in title_existing
        if (
            item.get("decision") == "uncertain"
            and float(item.get("confidence") or 0) == 0
            and str(item.get("reason") or "") in invalid_reasons
            and (
                str(item.get("reason") or "")
                == "AI response did not contain a valid decision for this record."
                or not item.get("criterion_judgements")
            )
        )
    ]
    if invalid_title_existing:
        archive = service._read(session_id, "invalid_screening_responses.json", [])
        archive.extend(invalid_title_existing)
        service._write(session_id, "invalid_screening_responses.json", archive)
        existing = [item for item in existing if item not in invalid_title_existing]
        service._write(session_id, "screening_decisions.json", existing)
        print(
            f"[{mode}] archived {len(invalid_title_existing)} invalid parsed decisions; "
            "rerunning title screening",
            flush=True,
        )
    title_done = {
        str(item.get("paper_id"))
        for item in existing
        if item.get("stage") == "title_abstract" and item.get("actor_type") == "ai"
    }
    pending_title = [
        str(item.get("paper_id"))
        for item in candidates
        if str(item.get("paper_id")) not in title_done
    ]
    title_batch_size = 8 if mode == "rapid" and len(pending_title) > 8 else 4
    for start in range(0, len(pending_title), title_batch_size):
        batch = pending_title[start : start + title_batch_size]
        print(
            f"[{mode}] product Agent title/abstract screening "
            f"{start + 1}-{start + len(batch)}/{len(pending_title)}",
            flush=True,
        )
        retry_agent_call(
            f"{mode}:title-screen",
            lambda batch=batch: scientific_routes.run_independent_ai_screening(
                session_id,
                AIScreeningRequest(
                    paper_ids=batch,
                    stage="title_abstract",
                    provider=provider_config,
                ),
            ),
        )

    resolved = service._resolved_screening_decisions(session_id)
    title_included = [
        str(item.get("paper_id"))
        for item in candidates
        if resolved.get(
            (str(item.get("candidate_id") or item.get("paper_id")), "title_abstract"),
            {},
        ).get("decision") == "include"
    ]
    paper_ids = {str(item.get("paper_id")) for item in manager.get_papers(session_id)}
    available = [paper_id for paper_id in title_included if paper_id in paper_ids]
    unavailable = [paper_id for paper_id in title_included if paper_id not in paper_ids]
    for paper_id in unavailable:
        service.record_screening(
            session_id,
            paper_id=paper_id,
            stage="full_text",
            decision="exclude",
            reason_code="full_text_unavailable",
            reason="No retained structured full-text evidence was available for this comparison run.",
            confidence=1.0,
            reviewer="system",
            actor_type="system",
            actor_id="fulltext_availability_check",
            blinded_to_peer=True,
        )

    existing = service._read(session_id, "screening_decisions.json", [])
    fulltext_done = {
        str(item.get("paper_id"))
        for item in existing
        if item.get("stage") == "full_text" and item.get("actor_type") == "ai"
    }
    pending_fulltext = [paper_id for paper_id in available if paper_id not in fulltext_done]
    for start in range(0, len(pending_fulltext), 6):
        batch = pending_fulltext[start : start + 6]
        print(
            f"[{mode}] product Agent full-text screening "
            f"{start + 1}-{start + len(batch)}/{len(pending_fulltext)}",
            flush=True,
        )
        retry_agent_call(
            f"{mode}:fulltext-screen",
            lambda batch=batch: scientific_routes.run_independent_ai_screening(
                session_id,
                AIScreeningRequest(
                    paper_ids=batch,
                    stage="full_text",
                    provider=provider_config,
                ),
            ),
        )

    resolved = service._resolved_screening_decisions(session_id)
    included = []
    for candidate in candidates:
        paper_id = str(candidate.get("paper_id"))
        decision = resolved.get(
            (str(candidate.get("candidate_id") or paper_id), "full_text"),
            {},
        ).get("decision")
        if decision == "include" and paper_id in paper_ids:
            included.append(paper_id)
            manager.update_paper_status(session_id, paper_id, "accepted")
        elif paper_id in paper_ids:
            manager.update_paper_status(session_id, paper_id, "rejected")
    if not included:
        raise RuntimeError(f"{mode} Agent screening produced no eligible full-text studies")
    if not service.latest_inclusion_snapshot(session_id):
        service.confirm_inclusion_snapshot(
            session_id,
            included,
            confirmed_by="ai_orchestrator",
            record_decisions=False,
        )

    source_extractions = {
        str(item.get("paper_id")): item
        for item in read_json(SOURCE_SESSION / "methodology" / "extractions.json", [])
    }
    source_appraisals = {
        str(item.get("paper_id")): item
        for item in read_json(SOURCE_SESSION / "methodology" / "appraisals.json", [])
    }
    for paper_id in included:
        service.save_extraction(session_id, paper_id, source_extractions[paper_id])
        if paper_id in source_appraisals:
            service.save_appraisal(session_id, paper_id, source_appraisals[paper_id])
    service.build_synthesis_groups(session_id, included)
    return included


def export_mode(
    manager: SessionManager,
    service: ScientificReviewService,
    session_id: str,
    mode: str,
    case_dir: Path,
    included: list[str],
    provider_config: ProviderConfig,
) -> dict:
    final_path = case_dir / "formal_review.md"
    if final_path.exists() and (case_dir / "final_summary.json").exists():
        return read_json(case_dir / "final_summary.json", {})

    print(f"[{mode}] product Agent writing from {len(included)} included studies", flush=True)
    result = retry_agent_call(
        f"{mode}:write",
        lambda: agent_routes.run_write_phase(
            session_id,
            RunPhaseRequest(
                topic=QUESTION,
                start_phase="write",
                paper_ids=included,
                provider=provider_config,
            ),
        ),
    )
    review = str(result.get("review") or "").strip()
    if not review:
        raise RuntimeError(f"{mode} product Agent returned an empty review")

    write_text(final_path, review)
    write_text(case_dir / "formal_review.html", markdown_to_html(review, TITLE))
    (case_dir / "formal_review.docx").write_bytes(_docx_bytes(review))
    (case_dir / "formal_review.pdf").write_bytes(_pdf_bytes(review))

    audit = service.audit_summary(session_id)
    screening_models = sorted({
        str(item.get("model_version"))
        for item in service._read(session_id, "screening_decisions.json", [])
        if item.get("actor_type") == "ai" and item.get("model_version")
    })
    claim_audit = service.audit_review_claims(
        session_id,
        review,
        [
            paper
            for paper in manager.get_papers(session_id)
            if paper.get("paper_id") in set(included)
        ],
    )
    files = {
        "protocol.json": audit["protocol"],
        "search_ledger.json": audit["methodology_report"].get("search_queries", []),
        "screening_ledger.json": service._read(session_id, "screening_decisions.json", []),
        "evidence_cards.json": audit["extractions"],
        "study_appraisals.json": audit["appraisals"],
        "synthesis_groups.json": service._read(session_id, "synthesis_groups.json", []),
        "claim_ledger.json": service._read(session_id, "claims.json", []),
        "methodology_audit.json": audit["methodology_report"],
        "quality_gate.json": result.get("quality", {}).get("scientific_gate", audit["quality_gate"]),
        "claim_audit.json": claim_audit,
        "agent_generation_trace.json": {
            "entrypoint": "backend.routes.agent.run_write_phase",
            "writer": "main.run_write_from_notes",
            "screening_entrypoint": "backend.routes.scientific_review.run_independent_ai_screening",
            "provider": "zhipu",
            "model": MODEL,
            "writer_model": MODEL,
            "screening_models": screening_models,
            "api_key_retained": False,
            "old_review_reused": False,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "traces": result.get("traces", []),
        },
    }
    for filename, value in files.items():
        write_json(case_dir / filename, value)

    flow = service.flow_counts(session_id)
    gate = files["quality_gate.json"]
    summary = {
        "mode": mode,
        "display_name": MODES[mode]["display_name"],
        "title": TITLE,
        "model": MODEL,
        "generation_entrypoint": "backend.routes.agent.run_write_phase",
        "candidate_count": flow.get("unique_candidates"),
        "duplicate_count": flow.get("duplicates_removed"),
        "queries_completed": flow.get("queries_completed"),
        "queries_planned": flow.get("queries_planned"),
        "title_abstract_screened": flow.get("title_abstract_screened"),
        "full_text_assessed": flow.get("full_text_assessed"),
        "included_count": len(included),
        "quality_gate_ok": gate.get("ok"),
        "quality_gate_label": gate.get("output_label"),
        "quality_gate_blockers": gate.get("blockers", []),
        "quality_gate_warnings": gate.get("warnings", []),
        "claim_audit_passed": claim_audit.get("passed"),
        "review_characters": len(review),
        "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "api_key_retained": False,
        "old_review_reused": False,
    }
    write_json(case_dir / "final_summary.json", summary)
    return summary


def main() -> None:
    if not SOURCE_SESSION.exists():
        raise RuntimeError(f"Source live-trial session is missing: {SOURCE_SESSION}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    manager = SessionManager(str(RUNTIME_ROOT))
    # Route functions are the exact product API implementation. Inject the
    # isolated comparison workspace so tests never alter normal user sessions.
    scientific_routes.session_mgr = manager
    agent_routes.session_mgr = manager
    config = provider()
    summaries = []
    for mode in ("systematic", "rapid"):
        session_id, service, case_dir = initialize_mode(manager, mode)
        if (case_dir / "formal_review.md").exists() and (case_dir / "final_summary.json").exists():
            summaries.append(read_json(case_dir / "final_summary.json", {}))
            continue
        included = screen_mode(manager, service, session_id, mode, config)
        summaries.append(
            export_mode(manager, service, session_id, mode, case_dir, included, config)
        )
    write_json(
        OUTPUT_ROOT / "comparison_summary.json",
        {
            "topic": QUESTION,
            "provider": "zhipu",
            "model": MODEL,
            "generation_policy": (
                "Both documents were generated by the product Agent. The previous review prose "
                "was not reused. Immutable candidate discovery and structured full-text evidence "
                "were reused, then screening and writing were rerun for each mode."
            ),
            "results": summaries,
        },
    )
    print(json.dumps(summaries, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
