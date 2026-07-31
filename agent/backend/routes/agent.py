"""Agent 执行端点：规划、搜索、笔记、综述、自动模式、分析"""
import json
import os
import datetime
import re
import time
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
from backend.provider import ensure_provider_available
from backend.cloud_persistence import get_workspace_store
from backend.run_store import PersistentRunStore, TERMINAL_STATUSES
from backend.scientific_review import ScientificReviewService, deterministic_evidence_seed
from backend.tenant import get_current_user, reset_current_user, set_current_user, tenant_key
from utils.locale import is_english, language_from_config
from utils.parser import extract_json

import threading
from main import run_agent_pipeline, run_agent_pipeline_session  # noqa
from .models import (
    RunPhaseRequest, RunNotesRequest, ReviseNotesRequest,
    AutoRunRequest, AnalysisRequest,
    RetryRunRequest,
)

router = APIRouter(prefix="/api/sessions", tags=["agent"])
_workspace_store = get_workspace_store(SESSIONS_DIR)
_run_store = PersistentRunStore(SESSIONS_DIR)
_checkpoint_sync_at: dict[str, float] = {}
_checkpoint_sync_lock = threading.Lock()


def _tenant_worker(target, *args) -> threading.Thread:
    """Carry request identity into long-running agent threads and persist on exit."""
    user_id = get_current_user()
    session_id = str(args[0]) if args else None

    def runner():
        token = set_current_user(user_id)
        try:
            target(*args)
        finally:
            try:
                _workspace_store.sync(user_id, session_id=session_id)
            except Exception as exc:
                print(f"[WorkspaceSync] background sync failed: {exc}")
            reset_current_user(token)

    return threading.Thread(target=runner, daemon=True)


def _run_key(session_id: str) -> str:
    return f"{tenant_key()}:{session_id}"


def _public_run(run: dict | None) -> dict:
    if not run:
        return {"status": "unknown", "message": "无运行记录"}
    return {key: value for key, value in run.items() if not key.startswith("_")}


def _persist_run(session_id: str, run: dict) -> None:
    run_id = str(run.get("run_id") or "")
    if not run_id:
        return
    _run_store.update(session_id, run_id, **_public_run(run))
    # A Render restart can discard its local disk before the worker's final
    # snapshot. Persist a bounded checkpoint during long runs without uploading
    # the whole workspace on every trace update.
    user_id = get_current_user()
    if user_id != "local" and _workspace_store.enabled:
        now = time.monotonic()
        with _checkpoint_sync_lock:
            previous = _checkpoint_sync_at.get(user_id, 0.0)
            if now - previous >= 20:
                _checkpoint_sync_at[user_id] = now
                _workspace_store.schedule_sync(
                    user_id,
                    session_id=session_id,
                    delay_seconds=0.5,
                )


def _create_run(session_id: str, kind: str, payload: dict) -> dict:
    durable = _run_store.create(session_id, kind, payload)
    live = dict(durable)
    with RUN_LOCK:
        RUNS[_run_key(session_id)] = live
    return live


def _build_skill_trace(phase: str, skill_id: str = "", skill_title: str = "", loaded: bool = False,
                       fallback_default: bool = True, reason: str = "not_configured") -> dict:
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "thought": f"Skill trace for {phase}",
        "action": "SKILL_STATUS",
        "input": {
            "phase": phase,
            "skill_id": skill_id or "",
            "skill_title": skill_title or "",
            "loaded": bool(loaded),
            "fallback_default": bool(fallback_default),
        },
        "observation": (
            f"skill_phase: {phase} | skill_id: {skill_id or '-'} | "
            f"skill_title: {skill_title or '-'} | loaded: {str(bool(loaded)).lower()} | "
            f"fallback_default: {str(bool(fallback_default)).lower()} | reason: {reason}"
        ),
        "error_type": "skill_info" if loaded else "skill_fallback",
    }


def _accepted_papers(session: dict, paper_ids: list[str] | None = None) -> list[dict]:
    """Resolve the explicit inclusion snapshot used by downstream artifacts."""
    papers = [paper for paper in session.get("papers", []) if paper.get("status") == "accepted"]
    if paper_ids is not None:
        requested = {str(pid).strip() for pid in paper_ids if str(pid).strip()}
        papers = [paper for paper in papers if paper.get("paper_id") in requested]
    return papers


def classify_search_outcome(new_count: int, target_new_papers: int) -> tuple[str, str]:
    """Map authoritative Session deltas to a user-facing search outcome/state."""
    actual = max(0, int(new_count or 0))
    target = max(1, int(target_new_papers or 1))
    if actual >= target:
        return "complete", "search_complete"
    if actual > 0:
        return "partial", "search_partial"
    return "failed", "search_failed"


def recommended_search_loop_budget(target_new_papers: int) -> int:
    """Return a non-binding UI/default recommendation for the requested paper count."""
    target = max(1, min(int(target_new_papers or 1), 15))
    return min(80, max(20, target * 5 + 10))


def effective_search_loop_budget(requested_loops: int, target_new_papers: int) -> int:
    """Honor the user's hard execution cap; the target only informs recommendations."""
    requested = max(1, int(requested_loops or 1))
    return min(80, requested)


def _search_outcome_message(
    new_count: int,
    target_new_papers: int,
    outcome: str,
    language: str = "zh-CN",
) -> str:
    if language == "en":
        if outcome == "complete":
            return f"Search complete: added {new_count}/{target_new_papers} papers in this run."
        if outcome == "partial":
            return (
                f"Search partially complete: added {new_count}/{target_new_papers} papers. "
                "The target has not been reached; you can continue searching."
            )
        return (
            f"Search failed: added 0/{target_new_papers} papers. "
            "Check the keywords, data sources, or registration errors and retry."
        )
    if outcome == "complete":
        return f"检索完成：本轮实际新增 {new_count}/{target_new_papers} 篇论文。"
    if outcome == "partial":
        return f"检索部分完成：本轮实际新增 {new_count}/{target_new_papers} 篇，尚未达到目标，可继续检索。"
    return f"检索失败：本轮实际新增 0/{target_new_papers} 篇。请检查关键词、数据源或登记错误后重试。"


def _search_stop_reason(traces: list[dict] | None) -> str:
    for trace in reversed(traces or []):
        action = str(trace.get("action") or "")
        if action == "BUDGET_EXHAUSTED":
            return "budget_exhausted"
        if action == "FINISH":
            return str(trace.get("error_type") or "completed")
    return "agent_returned"


def _retrieval_ledger(traces: list[dict] | None) -> dict:
    """Summarize real tool activity so later searches can expand instead of repeat."""
    queries: list[dict] = []
    source_counts: dict[str, int] = {}
    registered_attempts = 0
    duplicate_attempts = 0
    seen = set()
    for trace in traces or []:
        if not isinstance(trace, dict):
            continue
        action = str(trace.get("action") or "")
        action_input = trace.get("input") if isinstance(trace.get("input"), dict) else {}
        if "search" in action or "citation" in action:
            source = action.replace("_search", "").replace("search_", "") or action
            source_counts[source] = source_counts.get(source, 0) + 1
            query = str(
                action_input.get("query")
                or action_input.get("keywords")
                or action_input.get("work_id")
                or ""
            ).strip()
            page = action_input.get("page", action_input.get("offset", action_input.get("start", "")))
            observation = str(trace.get("observation") or "")
            failed = bool(
                trace.get("error_type")
                or re.search(
                    r"(?:http\s*429|too many requests|error executing|request failed|检索请求失败|限流)",
                    observation,
                    flags=re.I,
                )
            )
            identity = (source, query.casefold(), str(page))
            if query and identity not in seen:
                seen.add(identity)
                queries.append({
                    "source": source,
                    "query": query,
                    "page": page,
                    "direction": action_input.get("direction"),
                    "success": not failed,
                    "error": observation[:500] if failed else None,
                })
        elif action == "paper_register":
            registered_attempts += 1
            observation = str(trace.get("observation") or "").lower()
            if "已存在" in observation or "duplicate" in observation or "already exists" in observation:
                duplicate_attempts += 1
    return {
        "queries": queries[-40:],
        "source_counts": source_counts,
        "registered_attempts": registered_attempts,
        "duplicate_attempts": duplicate_attempts,
    }


def _pdf_available_count(session_id: str, papers: list[dict]) -> int:
    papers_dir = session_mgr.root / session_id / "papers"
    count = 0
    for paper in papers:
        paper_id = str(paper.get("paper_id") or "")
        filename = str(paper.get("pdf_filename") or f"{paper_id}.pdf")
        if paper.get("pdf_status") == "available" or (filename and (papers_dir / filename).exists()):
            count += 1
    return count


def _load_analysis_context_for_writing(session_id: str, paper_ids: list[str] | None = None) -> str:
    """Load saved compare/lineage/gaps analysis as optional writing context."""
    analysis_path = session_mgr.root / session_id / "analysis" / "analysis_results.json"
    if not analysis_path.exists():
        return ""
    try:
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""

    if paper_ids is not None:
        expected = sorted(str(pid) for pid in paper_ids if pid)
        actual = sorted(str(pid) for pid in data.get("paper_ids", []) if pid)
        if expected != actual:
            return ""

    document = str(data.get("document", "") or "").strip()
    if document:
        return document

    sections = []
    labels = {
        "compare": "Paper comparison",
        "lineage": "Research lineage",
        "gaps": "Research gaps",
    }
    for key in ("compare", "lineage", "gaps"):
        content = str(data.get(key, "") or "").strip()
        if content:
            sections.append(f"### {labels[key]}\n\n{content}")
    return "\n\n".join(sections)


def _repository_context_for_writing(session: dict, language: str = "zh-CN") -> str:
    repositories = session.get("repositories") or []
    sections = []
    for index, repo in enumerate(repositories, start=1):
        report = str(repo.get("report") or "").strip()
        if report:
            label = "GitHub repository evidence" if language == "en" else "GitHub 仓库证据"
            sections.append(f"## {label} R{index}: {repo.get('full_name', 'repository')}\n\n{report}")
    return "\n\n---\n\n".join(sections)


def _collect_notes_for_analysis(session: dict, paper_ids: list[str] | None = None) -> tuple[str, list[dict]]:
    papers = _accepted_papers(session, paper_ids)
    parts = []
    for paper in papers:
        paper_notes = (paper.get("notes") or "").strip()
        if paper_notes:
            title = paper.get("title") or paper.get("paper_id") or "Unknown"
            parts.append(f"## {title}\n\n{paper_notes}")
    notes = "\n\n---\n\n".join(parts)

    return notes, papers


def _extract_scientific_evidence(
    llm,
    *,
    topic: str,
    paper: dict,
    notes: str,
    appraisal_profile: str,
) -> tuple[dict, dict]:
    """Convert one evidence note into typed extraction and appraisal records."""
    schema = {
        "extraction": {
            "study_design": None,
            "study_or_article_type": "primary_study|benchmark|framework|dataset_or_resource|systematic_or_scoping_review|narrative_survey|other|unclear",
            "population_or_dataset": None,
            "intervention_or_method": None,
            "comparator_or_baseline": None,
            "sample_size": None,
            "outcomes_and_metrics": [],
            "main_results": [{"statement": "", "support_type": "reported_result|author_claim|reviewer_inference", "location": None}],
            "quantitative_results": [{
                "statement": "",
                "dataset_or_task": None,
                "base_model": None,
                "retriever": None,
                "corpus_size": None,
                "baseline": None,
                "metric": None,
                "baseline_value": None,
                "method_value": None,
                "effect_value": None,
                "effect_type": "absolute|relative|raw_comparison|unclear",
                "aggregation": None,
                "statistical_significance": None,
                "hardware": None,
                "evidence_location": {"page": None, "section": None, "table": None},
            }],
            "technical_mechanism": {
                "method_family": None,
                "inputs": [],
                "internal_state": None,
                "decision_rule": None,
                "thresholds": [],
                "trigger_granularity": None,
                "actions": [],
                "fusion_strategy": None,
                "failure_propagation": [],
                "applicability_conditions": [],
                "agentic_criteria_met": False,
            },
            "uncertainty": None,
            "limitations": [],
            "funding_and_conflicts": None,
            "evidence_locations": [{"section": None, "page": None, "excerpt": ""}],
            "computer_ai": {
                "dataset_provenance": None,
                "split_and_leakage_risk": None,
                "baseline_fairness": None,
                "variance_or_significance": None,
                "ablation_reported": None,
                "code_data_environment": None,
                "external_validity": None,
                "compute_cost": None,
            },
            "confidence": 0.0,
        },
        "appraisal": {
            "profile": appraisal_profile,
            "study_design": None,
            "domains": [{
                "id": "baseline_fairness|data_leakage|statistical_sufficiency|ablation|reproducibility|external_validity|compute_cost",
                "name": "",
                "judgement": "low|some_concerns|high|unclear",
                "reason": "",
                "evidence": "",
            }],
            "overall_judgement": "low|some_concerns|high|unclear",
            "rationale": "",
        },
    }
    is_en = getattr(llm, "language", "zh-CN") == "en"
    system = (
        "You are a conservative evidence extraction and study-appraisal engine. "
        "Return one JSON object only. Never infer absent information; use null or []. "
        "Every quantitative result needs its metric, comparison and evidence location. "
        "Classify primary versus secondary evidence. Extract mechanism inputs, decision rules, "
        "thresholds, granularity, actions, failure propagation and applicability. "
        "A single overall score without domain-level reasons is forbidden."
        if is_en else
        "你是保守的结构化证据提取与研究质量评价引擎。只返回一个 JSON 对象。"
        "笔记中未提供的信息必须使用 null 或 []，禁止依据常识补齐。"
        "每个定量结果必须保留指标、比较对象和证据位置。禁止只给没有逐领域理由的总分。"
        "必须区分一级与二级证据，并提取机制输入、决策规则、阈值、粒度、动作、失效传播和适用条件。"
    )
    labels = (
        ("Research question", "Paper", "Evidence basis", "Appraisal profile", "Evidence note",
         "Return JSON matching this shape")
        if is_en else
        ("研究问题", "论文", "证据基础", "评价配置", "证据笔记", "返回符合以下结构的 JSON")
    )
    prompt = (
        f"{labels[0]}：{topic}\n"
        f"{labels[1]}：{paper.get('title')}（{paper.get('paper_id')}）\n"
        f"{labels[2]}：{paper.get('evidence_basis') or 'unknown'}\n"
        f"{labels[3]}：{appraisal_profile}\n\n"
        f"{labels[4]}：\n{notes[:18000]}\n\n"
        f"{labels[5]}：\n{json.dumps(schema, ensure_ascii=False)}\n\n"
        "For computer_ai appraisal, return all seven domains exactly once: "
        "baseline_fairness, data_leakage, statistical_sufficiency, ablation, "
        "reproducibility, external_validity, compute_cost."
    )
    parsed = extract_json(llm.chat(system, prompt, []))
    extraction = parsed.get("extraction") if isinstance(parsed.get("extraction"), dict) else {}
    appraisal = parsed.get("appraisal") if isinstance(parsed.get("appraisal"), dict) else {}
    extraction["evidence_basis"] = paper.get("evidence_basis") or (
        "full_text" if paper.get("pdf_status") == "available" else "abstract"
    )
    extraction["review_status"] = "ai_draft"
    appraisal["review_status"] = "ai_draft"
    return extraction, appraisal


def _run_session_analysis(session_id: str, topic: str, analysis_type: str = "all",
                          provider_config: dict | None = None,
                          paper_ids: list[str] | None = None) -> dict:
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    analysis_type = analysis_type or "all"
    if analysis_type not in {"compare", "lineage", "gaps", "all"}:
        raise HTTPException(status_code=400, detail="analysis_type 必须是 compare、lineage、gaps 或 all")

    notes, papers = _collect_notes_for_analysis(session, paper_ids)
    if not papers:
        raise HTTPException(status_code=400, detail="请先至少纳入一篇论文")
    if not notes.strip():
        raise HTTPException(status_code=400, detail="已纳入论文尚无笔记，请先生成笔记")

    scientific = ScientificReviewService(session_mgr)
    selected_ids = {paper.get("paper_id", "") for paper in papers}
    protocol = scientific.ensure_protocol(session_id, topic=topic)
    extraction_rows = [
        item for item in scientific._read(session_id, "extractions.json", [])
        if item.get("protocol_id") == protocol.get("protocol_id")
        and item.get("paper_id") in selected_ids
    ]
    appraisal_rows = [
        item for item in scientific._read(session_id, "appraisals.json", [])
        if item.get("protocol_id") == protocol.get("protocol_id")
        and item.get("paper_id") in selected_ids
    ]
    if extraction_rows:
        synthesis_groups = scientific.build_synthesis_groups(session_id, selected_ids)
        notes = (
            "## Structured evidence matrix (source of truth)\n\n"
            f"```json\n{json.dumps(extraction_rows, ensure_ascii=False, indent=2)}\n```\n\n"
            "## Study appraisal records\n\n"
            f"```json\n{json.dumps(appraisal_rows, ensure_ascii=False, indent=2)}\n```\n\n"
            "## Predefined synthesis groups\n\n"
            f"```json\n{json.dumps(synthesis_groups, ensure_ascii=False, indent=2)}\n```\n\n"
            "---\n\n"
            + notes
        )

    from tools.analysis_tools import compare_papers, trace_lineage, find_gaps

    selected_ids_list = [paper.get("paper_id", "") for paper in papers]
    result = {"phase": "analysis", "session_id": session_id, "paper_ids": selected_ids_list}
    if analysis_type in ("compare", "all"):
        result["compare"] = compare_papers(topic, notes, papers, provider_config)
    if analysis_type in ("lineage", "all"):
        result["lineage"] = trace_lineage(topic, notes, papers, provider_config)
    if analysis_type in ("gaps", "all"):
        result["gaps"] = find_gaps(topic, notes, papers, provider_config)
    result["document"] = _analysis_result_to_markdown(
        result, topic, language_from_config(provider_config)
    )

    analysis_dir = session_mgr.root / session_id / "analysis"
    os.makedirs(analysis_dir, exist_ok=True)
    session_mgr._write_json(analysis_dir / "analysis_results.json", result)
    return result


def _analysis_result_to_markdown(result: dict, topic: str, language: str = "zh-CN") -> str:
    sections = []
    labels = (
        {
            "compare": "Comparative Evidence Analysis",
            "lineage": "Research Lineage",
            "gaps": "Research Gaps",
            "title": "In-depth Analysis",
        }
        if language == "en"
        else {
            "compare": "文献对比分析",
            "lineage": "研究脉络梳理",
            "gaps": "研究空白发现",
            "title": "深度分析",
        }
    )
    if str(result.get("compare", "") or "").strip():
        sections.append(f"## {labels['compare']}\n\n{result['compare']}")
    if str(result.get("lineage", "") or "").strip():
        sections.append(f"## {labels['lineage']}\n\n{result['lineage']}")
    if str(result.get("gaps", "") or "").strip():
        sections.append(f"## {labels['gaps']}\n\n{result['gaps']}")
    if not sections:
        return ""
    return f"# {labels['title']}: {topic}\n\n" + "\n\n---\n\n".join(sections)


def _strip_document_markdown_fence(value: str) -> str:
    """Remove a model-added fence that wraps an entire Markdown document."""
    text = str(value or "").strip()
    lines = text.splitlines()
    if lines and re.fullmatch(r"```(?:markdown|md)?\s*", lines[0].strip(), flags=re.I):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
    return "\n".join(lines).strip()

@router.post("/{session_id}/run/plan")
def run_plan_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段1】执行规划，生成关键词候选项"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    provider_config = ensure_provider_available(payload.provider)

    try:
        result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=payload.topic.strip(),
            start_phase="plan",
            provider_config=provider_config,
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

def _run_search_in_background(
    session_id: str,
    topic: str,
    keywords: list[dict],
    max_loops: int,
    search_mode: str,
    target_new_papers: int,
    provider_config: dict | None = None,
    run_id: str = "",
) -> None:
    """后台执行搜索阶段，周期性保存 traces 供前端实时轮询"""
    import time as _time
    _stop_flag = [False]  # 用列表做可变容器，线程间可共享修改
    
    def _periodic_trace_saver():
        """每 3 秒将运行中的 traces 同步到 RUNS 内存（不写磁盘，避免覆盖历史数据）"""
        while not _stop_flag[0]:
            _time.sleep(3)
            try:
                agent = _agent_holder.get("agent")
                traces = list(agent.traces) if agent else []
                if not traces:
                    with RUN_LOCK:
                        traces = list(RUNS.get(_run_key(session_id), {}).get("traces", []))
                if traces:
                    # 只更新 RUNS 内存，供前端轮询 /api/sessions/{id}/run/status
                    live_run = None
                    with RUN_LOCK:
                        if _run_key(session_id) in RUNS:
                            RUNS[_run_key(session_id)]["traces"] = traces
                            live_run = dict(RUNS[_run_key(session_id)])
                    if run_id and live_run:
                        _persist_run(session_id, live_run)
            except Exception:
                pass
    
    _saver_thread = threading.Thread(target=_periodic_trace_saver, daemon=True)
    _agent_holder = {}  # 用于捕获运行中 Agent 的引用
    
    try:
        from backend.session_manager import papers_match
        before_papers = session_mgr.get_papers(session_id)
        search_started_at = datetime.datetime.now().isoformat()
        scientific_service = ScientificReviewService(session_mgr)
        scientific_state = scientific_service.audit_summary(session_id)
        review_protocol = scientific_state.get("protocol") or {}
        search_query_plan = scientific_state.get("search_queries") or []
        # 更新 Session 状态为 searching（端点可能已更新，忽略重复异常）
        try:
            session_mgr.update_session_state(session_id, "searching")
        except ValueError:
            pass
        
        with RUN_LOCK:
            RUNS[_run_key(session_id)] = {
                "run_id": run_id,
                "session_id": session_id,
                "kind": "search",
                "status": "running",
                "phase": "searching",
                "checkpoint": "searching",
                "retryable": False,
                "traces": [],
                "_stop_flag": _stop_flag,  # 暴露终止标志供 cancel API 使用
            }
            live_run = dict(RUNS[_run_key(session_id)])
        _persist_run(session_id, live_run)
        
        _saver_thread.start()

        result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=topic,
            start_phase="search",
            user_keywords=keywords,
            max_loops=max_loops,
            provider_config=provider_config,
            existing_papers=before_papers,
            target_new_papers=target_new_papers,
            search_mode=search_mode,
            review_protocol=review_protocol,
            search_query_plan=search_query_plan,
            agent_callback=lambda agent, wd: _agent_holder.update({"agent": agent}),
        )
        
        _stop_flag[0] = True

        # 保存论文列表到 Session
        if result.get("papers"):
            session_mgr.save_papers_list(session_id, result["papers"])
        # 保存轨迹（追加模式：不覆盖之前的轨迹）
        if result.get("traces"):
            session_mgr.save_traces(session_id, result["traces"], append=True)
        after_papers = session_mgr.get_papers(session_id)
        new_papers = [
            paper for paper in after_papers
            if not any(papers_match(paper, old) for old in before_papers)
        ]
        search_summary = {
            "mode": search_mode,
            "started_at": search_started_at,
            "finished_at": datetime.datetime.now().isoformat(),
            "keywords": keywords,
            "before_count": len(before_papers),
            "after_count": len(after_papers),
            "new_count": len(new_papers),
            "new_paper_ids": [paper.get("paper_id", "") for paper in new_papers],
            "target_new_papers": target_new_papers,
            "max_loops": max_loops,
            "stop_reason": _search_stop_reason(result.get("traces")),
            "pdf_available_count": _pdf_available_count(session_id, new_papers),
            "retrieval_ledger": _retrieval_ledger(result.get("traces")),
        }
        outcome, outcome_state = classify_search_outcome(len(new_papers), target_new_papers)
        search_summary["outcome"] = outcome
        search_summary["state"] = outcome_state
        language = language_from_config(provider_config)
        search_summary["message"] = _search_outcome_message(
            len(new_papers), target_new_papers, outcome, language
        )
        search_summary["message"] += (
            f" PDF available for {search_summary['pdf_available_count']}/{len(new_papers)} papers."
            if language == "en"
            else f" 本轮 PDF 可用 {search_summary['pdf_available_count']}/{len(new_papers)} 篇。"
        )
        if outcome != "complete" and search_summary["stop_reason"] == "budget_exhausted":
            search_summary["message"] += (
                " The execution budget was exhausted; continuing will resume from a new results page."
                if language == "en"
                else " 本轮执行预算已耗尽；继续检索将从新结果页开始。"
            )
        result["search_summary"] = search_summary
        session_mgr.save_search_run(session_id, search_summary)
        reconciled_queries = scientific_service.reconcile_search_ledger(
            session_id, search_summary["retrieval_ledger"]
        )
        search_summary["protocol_search"] = {
            "completed": sum(item.get("status") == "completed" for item in reconciled_queries),
            "planned": len(reconciled_queries),
            "items": reconciled_queries,
        }
        flow = scientific_service.flow_counts(session_id)
        protocol_stopping_condition_met = bool(reconciled_queries) and all(
            item.get("status") == "completed" for item in reconciled_queries
        )
        protocol_stopping_condition_met = protocol_stopping_condition_met or (
            flow.get("unique_candidates", 0) >= int(review_protocol.get("candidate_cap") or 100)
        )
        if not protocol_stopping_condition_met and outcome == "complete":
            outcome = "partial"
            outcome_state = "search_partial"
            search_summary["outcome"] = outcome
            search_summary["state"] = outcome_state
            search_summary["message"] += (
                " The requested batch size was reached, but protocol search coverage remains incomplete."
                if language == "en"
                else " 已达到本轮篇数目标，但协议检索覆盖尚未完成。"
            )
        session_mgr.save_search_run(session_id, search_summary)
        try:
            session_mgr.update_session_state(session_id, outcome_state)
        except ValueError:
            pass  # 可能已被取消设置为其他状态

        with RUN_LOCK:
            RUNS[_run_key(session_id)] = {
                "run_id": run_id,
                "session_id": session_id,
                "kind": "search",
                "status": "done" if outcome == "complete" else outcome,
                "phase": outcome_state,
                "checkpoint": outcome_state,
                "retryable": outcome != "complete",
                "message": search_summary["message"],
                "traces": result.get("traces", []),
                "result": result,
                "search_summary": search_summary,
            }
            live_run = dict(RUNS[_run_key(session_id)])
        _persist_run(session_id, live_run)

    except Exception as exc:
        import traceback
        _stop_flag[0] = True
        from backend.session_manager import papers_match
        failed_before = locals().get("before_papers", [])
        failed_after = session_mgr.get_papers(session_id)
        failed_new = [
            paper for paper in failed_after
            if not any(papers_match(paper, old) for old in failed_before)
        ]
        failed_outcome, failed_state = classify_search_outcome(len(failed_new), target_new_papers)
        if failed_outcome == "complete":
            failed_outcome, failed_state = "partial", "search_partial"
        failed_summary = {
            "mode": search_mode,
            "started_at": locals().get("search_started_at", datetime.datetime.now().isoformat()),
            "finished_at": datetime.datetime.now().isoformat(),
            "keywords": keywords,
            "before_count": len(failed_before),
            "after_count": len(failed_after),
            "new_count": len(failed_new),
            "new_paper_ids": [paper.get("paper_id", "") for paper in failed_new],
            "target_new_papers": target_new_papers,
            "outcome": failed_outcome,
            "state": failed_state,
            "message": (
                f"{_search_outcome_message(len(failed_new), target_new_papers, failed_outcome, language_from_config(provider_config))} "
                f"{'Reason' if is_english(provider_config) else '原因'}: {exc}"
            ),
            "error": str(exc),
            "retrieval_ledger": _retrieval_ledger(
                (locals().get("result") or {}).get("traces") if isinstance(locals().get("result"), dict) else []
            ),
        }
        try:
            session_mgr.save_search_run(session_id, failed_summary)
        except Exception:
            pass
        try:
            session_mgr.update_session_state(session_id, failed_state)
        except ValueError:
            pass
        with RUN_LOCK:
            RUNS[_run_key(session_id)] = {
                "run_id": run_id,
                "session_id": session_id,
                "kind": "search",
                "status": "error",
                "phase": failed_state,
                "checkpoint": failed_state,
                "retryable": True,
                "error_code": "search_failed",
                "message": failed_summary["message"],
                "search_summary": failed_summary,
                "error": str(exc),
                "_traceback": traceback.format_exc(),
            }
            live_run = dict(RUNS[_run_key(session_id)])
        _persist_run(session_id, live_run)


@router.post("/{session_id}/run/search")
def run_search_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段2】执行搜索（后台运行，需轮询状态）"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    provider_config = ensure_provider_available(payload.provider)
    scientific = ScientificReviewService(session_mgr)
    protocol = scientific.ensure_protocol(
        session_id,
        topic=session.get("topic", payload.topic.strip()),
        language=language_from_config(provider_config),
    )
    if protocol.get("status") != "confirmed":
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "protocol_confirmation_required",
                "message": "请先确认研究协议，再开始检索",
                "protocol": protocol,
                "retryable": False,
            },
        )
    flow = scientific.flow_counts(session_id)
    if flow.get("unique_candidates", 0) >= int(protocol.get("candidate_cap", 100)):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "candidate_cap_reached",
                "message": f"候选文献已达到协议上限 {protocol.get('candidate_cap')} 条",
                "retryable": False,
            },
        )

    # 获取用户确认的关键词
    keywords = payload.keywords or session.get("keywords", [])
    if not keywords:
        raise HTTPException(status_code=400, detail="关键词不能为空，请先确认关键词")
    target_new_papers = max(1, min(int(payload.target_new_papers or 3), 15))
    max_loops = effective_search_loop_budget(payload.max_loops, target_new_papers)
    search_mode = "incremental" if session.get("papers") else "initial"
    if payload.search_mode in {"initial", "incremental"}:
        search_mode = payload.search_mode if session.get("papers") else "initial"

    run_key = _run_key(session_id)
    with RUN_LOCK:
        existing = RUNS.get(run_key)
        if existing and existing.get("status") == "running":
            raise HTTPException(status_code=409, detail="该项目已有正在运行的任务，请等待完成或取消后再试")

    run = _create_run(session_id, "search", {
        "topic": payload.topic.strip(),
        "keywords": keywords,
        "max_loops": max_loops,
        "search_mode": search_mode,
        "target_new_papers": target_new_papers,
        "provider": provider_config,
        "language": language_from_config(provider_config),
    })

    # 更新状态为 searching
    try:
        session_mgr.update_session_state(session_id, "searching")
    except ValueError:
        pass  # 状态可能已经是 searching

    # 后台执行
    worker = _tenant_worker(
        _run_search_in_background,
        session_id, payload.topic.strip(), keywords, max_loops,
        search_mode, target_new_papers, provider_config, run["run_id"],
    )
    worker.start()
    return {
        "session_id": session_id,
        "run_id": run["run_id"],
        "status": "searching",
        "search_mode": search_mode,
        "target_new_papers": target_new_papers,
        "max_loops": max_loops,
        "protocol_id": protocol.get("protocol_id"),
        "protocol_version": protocol.get("version"),
        "candidate_cap": protocol.get("candidate_cap"),
        "message": "搜索已开始，请通过 GET /api/sessions/{session_id} 轮询状态",
    }


@router.get("/{session_id}/run/status")
def get_session_run_status(session_id: str) -> dict:
    run_key = _run_key(session_id)
    with RUN_LOCK:
        run = RUNS.get(run_key)
    if run:
        return _public_run(run)
    durable = _run_store.latest(session_id)
    if durable and durable.get("status") == "running":
        durable = _run_store.mark_interrupted(session_id, durable["run_id"])
    return _public_run(durable)


@router.get("/{session_id}/runs")
def list_session_runs(session_id: str, limit: int = 30) -> dict:
    if not session_mgr.load_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return {"runs": [_public_run(run) for run in _run_store.list(session_id, limit)]}


@router.get("/{session_id}/runs/{run_id}")
def get_session_run(session_id: str, run_id: str) -> dict:
    run_key = _run_key(session_id)
    with RUN_LOCK:
        live = RUNS.get(run_key)
    if live and live.get("run_id") == run_id:
        return _public_run(live)
    durable = _run_store.get(session_id, run_id)
    if durable and durable.get("status") == "running":
        durable = _run_store.mark_interrupted(session_id, run_id)
    if not durable:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return _public_run(durable)


@router.post("/{session_id}/runs/{run_id}/retry")
def retry_session_run(session_id: str, run_id: str, request: RetryRunRequest) -> dict:
    """Start a replacement run from durable, credential-free run metadata."""
    previous = _run_store.get(session_id, run_id)
    if not previous:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    if previous.get("status") == "running":
        with RUN_LOCK:
            live = RUNS.get(_run_key(session_id))
        if live and live.get("run_id") == run_id:
            raise HTTPException(status_code=409, detail="任务仍在运行，无需重试")
        previous = _run_store.mark_interrupted(session_id, run_id) or previous
    if previous.get("status") not in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="当前运行状态不可重试")

    saved = previous.get("payload") or {}
    kind = previous.get("kind")
    if kind == "search":
        response = run_search_phase(session_id, RunPhaseRequest(
            topic=str(saved.get("topic") or ""),
            start_phase="search",
            keywords=saved.get("keywords") or None,
            search_mode="incremental",
            target_new_papers=int(saved.get("target_new_papers") or 3),
            max_loops=int(saved.get("max_loops") or 20),
            provider=request.provider,
        ))
    elif kind == "auto":
        response = run_auto_pipeline(session_id, AutoRunRequest(
            topic=str(saved.get("topic") or ""),
            min_papers=int(saved.get("min_papers") or 3),
            max_loops=int(saved.get("max_loops") or 20),
            provider=request.provider,
        ))
    else:
        raise HTTPException(status_code=400, detail="该类型任务暂不支持自动重试")

    _run_store.update(
        session_id,
        run_id,
        retried_as=response.get("run_id", ""),
        retryable=False,
    )
    return response


@router.post("/{session_id}/run/cancel")
def cancel_session_run(session_id: str) -> dict:
    """打断正在运行的搜索/撰写任务"""
    run_key = _run_key(session_id)
    with RUN_LOCK:
        run = RUNS.get(run_key)
    
    if not run:
        durable = _run_store.latest(session_id)
        if durable and durable.get("status") in {"running", "interrupted"}:
            _run_store.update(
                session_id,
                durable["run_id"],
                status="cancelled",
                phase="cancelled",
                checkpoint=durable.get("checkpoint", "queued"),
                retryable=True,
                message="任务已取消；已完成的阶段和部分结果仍然保留。",
            )
        # RUNS 里没有（可能是服务器重启过），检查磁盘状态
        session = session_mgr.load_session(session_id)
        if session and session.get("state") in {"searching", "writing"}:
            # 卡住状态，直接回退
            fallback = {"searching": "search_complete", "writing": "reviewing_notes"}
            new_state = fallback.get(session["state"], "search_complete")
            try:
                session_mgr.update_session_state(session_id, new_state)
            except ValueError:
                session_dir = session_mgr.root / session_id
                meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
                meta["state"] = new_state
                session_mgr._write_json(session_dir / "metadata.json", meta)
            return {"status": "fixed", "message": f"卡住状态已修复：{session['state']} → {new_state}"}
        raise HTTPException(status_code=404, detail="没有正在运行的任务，且状态未卡住")

    # 设置停止标志
    stop_flag = run.get("_stop_flag")
    if stop_flag and isinstance(stop_flag, list):
        stop_flag[0] = True
    
    # 更新 RUNS 状态
    with RUN_LOCK:
        RUNS[run_key]["status"] = "cancelled"
        RUNS[run_key]["phase"] = "cancelled"
        RUNS[run_key]["retryable"] = True
        live_run = dict(RUNS[run_key])
    _persist_run(session_id, live_run)

    # 回退 Session 状态
    try:
        session_mgr.update_session_state(session_id, "search_complete")
    except ValueError:
        try:
            session_mgr.update_session_state(session_id, "plan_confirmed")
        except ValueError:
            pass

    return {"status": "cancelled", "message": "任务已被用户终止"}


@router.post("/{session_id}/run/write")
def run_write_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段3】撰写综述（基于 Session 中的笔记）"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    provider_config = ensure_provider_available(payload.provider)

    papers = _accepted_papers(session, payload.paper_ids)
    if not papers and not session.get("repositories"):
        raise HTTPException(status_code=400, detail="请先至少纳入一篇论文，再生成综述")
    aggregated = []
    for p in papers:
        pn = (p.get("notes") or "").strip()
        if pn:
            aggregated.append(f"## {p.get('title', p.get('paper_id', ''))}\n\n{pn}")
    notes = "\n\n---\n\n".join(aggregated)

    repository_context = _repository_context_for_writing(
        session, language_from_config(provider_config)
    )
    if repository_context:
        notes = f"{notes}\n\n---\n\n{repository_context}" if notes.strip() else repository_context
    
    if not notes.strip():
        raise HTTPException(status_code=400, detail="笔记为空，请先为选中论文生成笔记")

    previous_review = session.get("review", "")
    feedback = session_mgr.get_feedback(session_id)
    rewrite_count = session.get("rewrite_count", 0)
    selected_ids = [paper.get("paper_id", "") for paper in papers]
    scientific = ScientificReviewService(session_mgr)
    protocol = scientific.ensure_protocol(
        session_id,
        topic=session.get("topic", payload.topic.strip()),
        language=language_from_config(provider_config),
    )
    snapshot = scientific.latest_inclusion_snapshot(session_id)
    if not snapshot:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "inclusion_confirmation_required",
                "message": "请先确认最终纳入论文，再生成综述",
                "selected_paper_ids": selected_ids,
                "retryable": False,
            },
        )
    existing_extractions = {
        item.get("paper_id")
        for item in scientific._read(session_id, "extractions.json", [])
        if item.get("protocol_id") == protocol.get("protocol_id")
    }
    for paper in papers:
        if paper.get("paper_id") not in existing_extractions:
            scientific.save_extraction(
                session_id,
                paper.get("paper_id", ""),
                deterministic_evidence_seed(paper),
            )
    gate = scientific.quality_gate(session_id, requested_paper_ids=selected_ids)
    # A failed methodology gate must downgrade the document, not suppress the
    # evidence synthesis entirely.  The product specification explicitly
    # allows an incomplete research draft while preventing it from being
    # presented as a systematic review.  Keeping the gate attached to the
    # result also gives the researcher a concrete remediation checklist.
    analysis_context = _load_analysis_context_for_writing(session_id, selected_ids)
    methodology_context = scientific.build_methodology_context(
        session_id, language_from_config(provider_config)
    )
    analysis_context = (
        f"{methodology_context}\n\n{analysis_context}"
        if analysis_context.strip()
        else methodology_context
    )

    try:
        from main import run_write_from_notes  # noqa
        result = run_write_from_notes(
            user_topic=payload.topic.strip(),
            notes_content=notes,
            previous_review=previous_review,
            user_feedback=feedback,
            rewrite_count=rewrite_count,
            session_id=session_id,
            analysis_context=analysis_context,
            provider_config=provider_config,
            papers_list=papers,
            repository_sources=session.get("repositories", []),
            review_mode=protocol.get("mode", "rapid"),
        )

        # 保存综述，并记录本次撰写引用了哪些论文
        if result.get("review"):
            result["review"] = _strip_document_markdown_fence(result["review"])
            result["review"] = scientific.inject_deterministic_review_sections(
                session_id,
                result["review"],
                papers,
                language_from_config(provider_config),
            )
            result["review"] = scientific.enforce_review_label(
                session_id,
                result["review"],
                gate,
                language_from_config(provider_config),
            )
            claim_audit = scientific.audit_review_claims(
                session_id, result["review"], papers
            )
            effective_gate = gate
            if not claim_audit.get("passed"):
                effective_gate = {
                    **gate,
                    "ok": False,
                    "can_claim_systematic": False,
                    "output_label": "incomplete_research_draft",
                    "blockers": list(dict.fromkeys(
                        list(gate.get("blockers") or []) + ["citation_claim_audit_failed"]
                    )),
                    "dimensions": {
                        **(gate.get("dimensions") or {}),
                        "citation_integrity": {
                            "passed": False,
                            "issues": ["citation_claim_audit_failed"],
                        },
                        "evidence_fit": {
                            "passed": not bool(claim_audit.get("evidence_mismatches")),
                            "issues": (
                                ["secondary_evidence_used_for_primary_claim"]
                                if claim_audit.get("evidence_mismatches") else []
                            ),
                        },
                        "quantitative_context": {
                            "passed": not bool(claim_audit.get("quantitative_context_issues")),
                            "issues": (
                                ["quantitative_claim_context_incomplete"]
                                if claim_audit.get("quantitative_context_issues") else []
                            ),
                        },
                        "internal_consistency": {
                            "passed": not bool(claim_audit.get("internal_consistency_issues")),
                            "issues": (
                                ["internal_claim_conflict"]
                                if claim_audit.get("internal_consistency_issues") else []
                            ),
                        },
                        "claim_strength": {
                            "passed": not bool(
                                claim_audit.get("normative_strength_issues")
                                or claim_audit.get("terminology_issues")
                            ),
                            "issues": (
                                ["unsupported_normative_or_agentic_claim"]
                                if (
                                    claim_audit.get("normative_strength_issues")
                                    or claim_audit.get("terminology_issues")
                                ) else []
                            ),
                        },
                        "artifact_completeness": {
                            "passed": bool(
                                (claim_audit.get("artifact_audit") or {}).get("passed")
                            ),
                            "issues": (
                                [] if (claim_audit.get("artifact_audit") or {}).get("passed")
                                else ["required_tables_or_figure_missing"]
                            ),
                        },
                        "reference_hygiene": {
                            "passed": bool(
                                (claim_audit.get("reference_audit") or {}).get("passed")
                            ),
                            "issues": (
                                [] if (claim_audit.get("reference_audit") or {}).get("passed")
                                else ["ieee_reference_hygiene_failed"]
                            ),
                        },
                    },
                }
                if gate.get("can_claim_systematic"):
                    result["review"] = scientific.enforce_review_label(
                        session_id,
                        result["review"],
                        effective_gate,
                        language_from_config(provider_config),
                    )
            session_mgr.save_review(session_id, result["review"], referenced_papers=selected_ids)
            quality_path = session_mgr.root / session_id / "review" / "quality.json"
            combined_quality = {
                **result.get("quality", {}),
                "scientific_gate": effective_gate,
                "output_label": effective_gate.get("output_label"),
                "claim_audit": claim_audit,
            }
            session_mgr._write_json(quality_path, combined_quality)
            result["quality"] = combined_quality
            result["review_version"] = scientific.write_review_version(
                session_id, result["review"], effective_gate
            )
        if result.get("traces"):
            session_mgr.save_traces(session_id, result["traces"], append=True)

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


# ━━━ Session-aware: 为选中论文生成独立笔记 ━━━


@router.post("/{session_id}/run/notes")
def run_notes_phase(session_id: str, payload: RunNotesRequest) -> dict:
    """【阶段2b】为选中的每篇论文生成独立笔记"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    provider_config = ensure_provider_available(payload.provider)

    papers = session.get("papers", [])
    paper_ids = [pid.strip() for pid in payload.paper_ids if pid.strip()]
    if not paper_ids:
        raise HTTPException(status_code=400, detail="paper_ids 不能为空")
    accepted_ids = {paper.get("paper_id") for paper in papers if paper.get("status") == "accepted"}
    invalid_ids = [pid for pid in paper_ids if pid not in accepted_ids]
    if invalid_ids:
        raise HTTPException(status_code=400, detail="只能为已纳入的论文生成笔记")

    from llms.client import LLMClient
    from tools.rag_note_generator import RAGNoteGenerator
    llm = LLMClient(provider_config)
    rag = RAGNoteGenerator(provider_config)
    topic = payload.topic.strip()

    # ━━━ 双通道 Skill 注入：笔记阶段 ━━━
    notes_skill_content = ""
    skills_config = session.get("skills", {})
    notes_skill_id = skills_config.get("notes")
    notes_skill_trace = _build_skill_trace("notes", skill_id=notes_skill_id or "")
    if notes_skill_id:
        try:
            notes_skill = skill_mgr.get_skill(notes_skill_id)
            if notes_skill and not notes_skill.get("deleted"):
                notes_skill_content = str(notes_skill.get("content", ""))
                notes_skill_title = str(notes_skill.get("title", "") or "")
                if notes_skill_content:
                    print(f"[NotesSkill] Loaded skill {notes_skill_id}: len={len(notes_skill_content)}, title={notes_skill.get('title','?')}")
                    notes_skill_trace = _build_skill_trace(
                        "notes",
                        skill_id=notes_skill_id,
                        skill_title=notes_skill_title,
                        loaded=True,
                        fallback_default=False,
                        reason="active",
                    )
                else:
                    print(f"[NotesSkill] Skill {notes_skill_id} has empty content, falling back to default")
                    notes_skill_trace = _build_skill_trace(
                        "notes",
                        skill_id=notes_skill_id,
                        skill_title=notes_skill_title,
                        reason="empty_content",
                    )
            else:
                # Skill 已删除或无效 → 自动回退默认通道
                print(f"[NotesSkill] Skill {notes_skill_id} is deleted/invalid, using default")
                notes_skill_trace = _build_skill_trace("notes", skill_id=notes_skill_id, reason="deleted_or_invalid")
        except Exception as e:
            # Skill 加载异常 → 静默回退默认通道
            print(f"[NotesSkill] Failed to load skill {notes_skill_id}: {e}")
            notes_skill_trace = _build_skill_trace("notes", skill_id=notes_skill_id, reason=f"load_error: {e}")
    else:
        print(f"[NotesSkill] No notes skill configured for this session, using default")

    if not notes_skill_content:
        notes_skill_content = str(skill_mgr.get_defaults().get("notes", {}).get("content", ""))

    notes_map = {}
    evidence_basis_map = {}

    for paper in papers:
        pid = paper.get("paper_id", "")
        if pid not in paper_ids:
            continue

        title = paper.get("title", pid)
        abstract = paper.get("abstract", "")
        source_info = paper.get("source", "")
        paper_path = None
        if source_info == "agent_search":
            paper_path = session_mgr.get_agent_search_paper_path(session_id, pid)
        elif source_info == "user_custom":
            paper_path = session_mgr.get_user_custom_paper_path(session_id, pid)
        elif source_info == "user_upload":
            paper_path = session_mgr.get_user_upload_paper_path(session_id, title)

        try:
            # 使用 RAG 生成深度笔记（Embedding 检索全文 + LLM 逐节生成）
            note_text = rag.generate(
                pdf_path=str(paper_path),
                paper_title=title,
                abstract=abstract,
                topic=topic,
                skill_content=notes_skill_content,
            )
            notes_map[pid] = note_text
            evidence_basis_map[pid] = "full_text" if paper_path and Path(paper_path).exists() else "abstract"
        except Exception:
            notes_map[pid] = f"## 论文笔记：{title}\n\n生成笔记时出错"
            evidence_basis_map[pid] = "generation_error"

    if notes_map:
        session_mgr.batch_update_paper_notes(session_id, notes_map, evidence_basis_map)
        refreshed_papers = {
            paper.get("paper_id"): paper
            for paper in session_mgr.get_papers(session_id)
        }
        scientific = ScientificReviewService(session_mgr)
        protocol = scientific.ensure_protocol(
            session_id,
            topic=topic,
            language=language_from_config(provider_config),
        )
        for paper_id, note_text in notes_map.items():
            paper = refreshed_papers.get(paper_id, {"paper_id": paper_id})
            try:
                extraction, appraisal = _extract_scientific_evidence(
                    llm,
                    topic=topic,
                    paper=paper,
                    notes=note_text,
                    appraisal_profile=protocol.get("appraisal_profile", "general"),
                )
            except Exception:
                extraction = deterministic_evidence_seed(paper)
                appraisal = {
                    "profile": protocol.get("appraisal_profile", "general"),
                    "study_design": None,
                    "domains": [],
                    "overall_judgement": "unclear",
                    "rationale": "Structured appraisal generation failed; human review is required.",
                    "review_status": "generation_error",
                }
            scientific.save_extraction(session_id, paper_id, extraction)
            scientific.save_appraisal(session_id, paper_id, appraisal)
    session_mgr.save_traces(session_id, [notes_skill_trace], append=True)

    return {
        "phase": "notes",
        "notes_map": notes_map,
        "count": len(notes_map),
        "extractions": scientific._read(session_id, "extractions.json", []) if notes_map else [],
        "appraisals": scientific._read(session_id, "appraisals.json", []) if notes_map else [],
        "traces": [notes_skill_trace],
    }

@router.post("/{session_id}/run/notes/revise")
def revise_notes_phase(session_id: str, payload: ReviseNotesRequest) -> dict:
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    provider_config = ensure_provider_available(payload.provider)
    
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
    llm = LLMClient(provider_config)

    rag_context = ""
    try:
        from tools.retriever import iterative_search
        import os as _os
        papers_path = str(session_mgr.root / session_id / "papers")
        passages = iterative_search(session_id, str(papers_path), payload.feedback, top_k=10, max_rounds=2, provider_config=provider_config)
        if passages:
            parts = []
            for p in passages:
                pid_p = p.get("paper_id", "")
                pg = p.get("page", "?")
                tit = ""
                for pp in session.get("papers", []):
                    if pp.get("paper_id") == pid_p:
                        tit = pp.get("title", "")[:60]
                        break
                citation_label = (
                    f"[{tit or pid_p} (page {pg})]"
                    if llm.language == "en"
                    else f"【{tit or pid_p} (第{pg}页)】"
                )
                parts.append(f"{citation_label}\n{p['text']}")
            rag_context = "\n\n---\n\n".join(parts)
    except Exception:
        pass

    if llm.language == "en":
        revise_prompt = f"""Revise the existing research notes according to the user's feedback.

Research topic: {payload.topic}

User feedback:
{payload.feedback}

Existing research notes:
{notes}

Additional retrieved evidence:
{rag_context or "No additional evidence was retrieved."}

Return the complete revised notes in Markdown. Preserve accurate source citations, do not use ellipses
to stand in for unchanged content, and do not add commentary outside the notes."""
        revise_system = "You are a rigorous academic research-note editor. Write the complete result in English."
    else:
        revise_prompt = f"""你是一名严谨的学术研究员。请根据用户的反馈意见，对现有的研究笔记进行修订。
    
研究主题：{payload.topic}

【用户反馈意见】：
{payload.feedback}

【现有研究笔记】：
{notes}

请按照用户的反馈意见修改现有研究笔记，输出修改后的完整笔记内容，不要保留未修改部分的省略号，不要输出额外的解释。
"""
        revise_system = "你是学术笔记修改专家。"
    try:
        new_notes = llm.chat(revise_system, revise_prompt, []).strip()
        
        if is_paper_notes and payload.paper_id:
            session_mgr.batch_update_paper_notes(session_id, {payload.paper_id: new_notes})
        else:
            session_mgr.save_notes(session_id, new_notes)
            
        return {
            "notes": new_notes,
            "message": "Notes revised from your feedback" if llm.language == "en" else "笔记已根据反馈修订",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"笔记修订执行失败: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/{session_id}/run/analyze")
def run_analysis_phase(session_id: str, payload: AnalysisRequest) -> dict:
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    provider_config = ensure_provider_available(payload.provider)

    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic 不能为空")

    try:
        return _run_session_analysis(
            session_id,
            topic,
            payload.analysis_type,
            provider_config,
            payload.paper_ids,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析阶段执行失败: {str(e)}")




def _run_auto_pipeline_in_background(
    session_id: str,
    topic: str,
    max_loops: int,
    min_papers: int,
    provider_config: dict | None = None,
    stop_flag: list[bool] | None = None,
    run_id: str = "",
    resume_from: str = "plan",
) -> None:
    """后台自动执行完整流水线：规划 → 搜索 → 笔记 → 分析 → 综述"""
    import time as _time

    run_key = _run_key(session_id)
    _stop_flag = stop_flag if isinstance(stop_flag, list) else [False]

    def _update_run_status(phase: str, status: str, **kwargs):
        with RUN_LOCK:
            if run_key in RUNS:
                entry = RUNS[run_key]
                entry["phase"] = phase
                entry["status"] = status
                entry["checkpoint"] = phase
                entry["retryable"] = status in {"partial", "error", "interrupted", "cancelled"}
                entry.update(kwargs)
                live_run = dict(entry)
            else:
                live_run = {
                    "run_id": run_id,
                    "session_id": session_id,
                    "kind": "auto",
                    "phase": phase,
                    "status": status,
                    "checkpoint": phase,
                    "retryable": status in {"partial", "error", "interrupted", "cancelled"},
                    **kwargs,
                }
        _persist_run(session_id, live_run)

    try:
        if resume_from == "notes":
            session = session_mgr.load_session(session_id) or {}
            included = _accepted_papers(session)
            paper_ids = [paper.get("paper_id", "") for paper in included]
            if not paper_ids:
                raise ValueError("No studies are present in the confirmed inclusion set")
            _update_run_status(
                "reviewing_notes",
                "running",
                message=f"最终纳入已确认，正在为 {len(paper_ids)} 篇论文生成结构化证据笔记...",
            )
            run_notes_phase(
                session_id,
                RunNotesRequest(topic=topic, paper_ids=paper_ids, provider=provider_config),
            )
            refreshed = session_mgr.load_session(session_id) or {}
            scientific = ScientificReviewService(session_mgr)
            for paper in _accepted_papers(refreshed):
                scientific.save_extraction(
                    session_id,
                    paper.get("paper_id", ""),
                    deterministic_evidence_seed(paper),
                )
            _update_run_status("analysis", "running", message="正在进行证据比较与质量分析...")
            run_analysis_phase(
                session_id,
                AnalysisRequest(
                    topic=topic,
                    analysis_type="all",
                    paper_ids=paper_ids,
                    provider=provider_config,
                ),
            )
            _update_run_status("writing", "running", message="正在按综述模式撰写并审计引用...")
            write_result = run_write_phase(
                session_id,
                RunPhaseRequest(
                    topic=topic,
                    start_phase="write",
                    paper_ids=paper_ids,
                    provider=provider_config,
                ),
            )
            _update_run_status(
                "complete",
                "done",
                message="自动流程已完成：证据笔记、分析和综述草稿均已生成。",
                result=write_result,
            )
            return

        # ━━ 阶段 1：规划 ━━
        _update_run_status("planning", "running", message="正在生成关键词规划...")

        if _stop_flag[0]:
            return

        plan_result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=topic,
            start_phase="plan",
            provider_config=provider_config,
        )
        if plan_result.get("initial_plan"):
            session_mgr.save_initial_plan(session_id, plan_result["initial_plan"])
        if plan_result.get("keywords"):
            session_mgr.save_keywords(session_id, plan_result["keywords"])
            ScientificReviewService(session_mgr).refresh_unstarted_search_queries(session_id)
        if plan_result.get("traces"):
            session_mgr.save_traces(session_id, plan_result["traces"])

        keywords = plan_result.get("keywords", [])
        _update_run_status("planning", "running",
                          message=f"关键词规划完成，共 {len(keywords)} 个候选项，即将开始搜索...",
                          keywords=keywords)

        if _stop_flag[0]:
            return

        # ━━ 阶段 2：搜索 ━━
        try:
            session_mgr.update_session_state(session_id, "searching")
        except ValueError:
            pass

        _update_run_status("searching", "running", message="正在检索论文并收集元数据...")

        # 设置最低论文数
        os.environ["AGENT_MIN_PAPERS"] = str(min_papers)

        _agent_holder = {}

        # 启动周期性 trace 同步线程，将 Agent 实时 traces 同步到 RUNS 供前端轮询
        def _auto_trace_saver():
            while not _stop_flag[0]:
                _time.sleep(3)
                try:
                    agent = _agent_holder.get("agent")
                    traces = list(agent.traces) if agent else []
                    if traces:
                        with RUN_LOCK:
                            if run_key in RUNS:
                                RUNS[run_key]["traces"] = traces
                except Exception:
                    pass

        _auto_saver_thread = threading.Thread(target=_auto_trace_saver, daemon=True)
        _auto_saver_thread.start()

        from backend.session_manager import papers_match
        before_papers = session_mgr.get_papers(session_id)
        search_started_at = datetime.datetime.now().isoformat()
        scientific_service = ScientificReviewService(session_mgr)
        scientific_state = scientific_service.audit_summary(session_id)
        review_protocol = scientific_state.get("protocol") or {}
        search_query_plan = scientific_state.get("search_queries") or []
        search_result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=topic,
            start_phase="search",
            user_keywords=keywords,
            max_loops=max_loops,
            provider_config=provider_config,
            existing_papers=before_papers,
            target_new_papers=min_papers,
            search_mode="incremental" if before_papers else "initial",
            review_protocol=review_protocol,
            search_query_plan=search_query_plan,
            agent_callback=lambda agent, wd: _agent_holder.update({"agent": agent}),
        )

        if _stop_flag[0]:
            return

        if search_result.get("papers"):
            session_mgr.save_papers_list(session_id, search_result["papers"])
        if search_result.get("traces"):
            session_mgr.save_traces(session_id, search_result["traces"], append=True)
        after_papers = session_mgr.get_papers(session_id)
        new_papers = [
            paper for paper in after_papers
            if not any(papers_match(paper, old) for old in before_papers)
        ]
        outcome, outcome_state = classify_search_outcome(len(new_papers), min_papers)
        search_summary = {
            "mode": "incremental" if before_papers else "initial",
            "started_at": search_started_at,
            "finished_at": datetime.datetime.now().isoformat(),
            "keywords": keywords,
            "before_count": len(before_papers),
            "after_count": len(after_papers),
            "new_count": len(new_papers),
            "new_paper_ids": [paper.get("paper_id", "") for paper in new_papers],
            "target_new_papers": min_papers,
            "max_loops": max_loops,
            "stop_reason": _search_stop_reason(search_result.get("traces")),
            "pdf_available_count": _pdf_available_count(session_id, new_papers),
            "outcome": outcome,
            "state": outcome_state,
            "message": _search_outcome_message(
                len(new_papers), min_papers, outcome, language_from_config(provider_config)
            ),
            "retrieval_ledger": _retrieval_ledger(search_result.get("traces")),
        }
        language = language_from_config(provider_config)
        search_summary["message"] += (
            f" PDF available for {search_summary['pdf_available_count']}/{len(new_papers)} papers."
            if language == "en"
            else f" 本轮 PDF 可用 {search_summary['pdf_available_count']}/{len(new_papers)} 篇。"
        )
        if outcome != "complete" and search_summary["stop_reason"] == "budget_exhausted":
            search_summary["message"] += (
                " The execution budget was exhausted; continuing will resume from a new results page."
                if language == "en"
                else " 本轮执行预算已耗尽；继续检索将从新结果页开始。"
            )
        reconciled_queries = scientific_service.reconcile_search_ledger(
            session_id, search_summary["retrieval_ledger"]
        )
        search_summary["protocol_search"] = {
            "completed": sum(item.get("status") == "completed" for item in reconciled_queries),
            "planned": len(reconciled_queries),
            "items": reconciled_queries,
        }
        flow = scientific_service.flow_counts(session_id)
        stopping_condition_met = bool(reconciled_queries) and all(
            item.get("status") == "completed" for item in reconciled_queries
        )
        stopping_condition_met = stopping_condition_met or (
            flow.get("unique_candidates", 0) >= int(review_protocol.get("candidate_cap") or 100)
        )
        if not stopping_condition_met and outcome == "complete":
            outcome = "partial"
            outcome_state = "search_partial"
            search_summary["outcome"] = outcome
            search_summary["state"] = outcome_state
            search_summary["message"] += (
                " The requested batch size was reached, but protocol search coverage remains incomplete."
                if language == "en"
                else " 已达到本轮篇数目标，但协议检索覆盖尚未完成。"
            )
        session_mgr.save_search_run(session_id, search_summary)
        try:
            session_mgr.update_session_state(session_id, outcome_state)
        except ValueError:
            pass

        papers = _accepted_papers(session_mgr.load_session(session_id) or {})
        if outcome != "complete":
            _update_run_status(
                outcome_state,
                "partial" if outcome == "partial" else "error",
                message=search_summary["message"],
                papers=papers,
                search_summary=search_summary,
            )
            return

        _update_run_status(
            "screening",
            "waiting_for_confirmation",
            message=(
                f"搜索完成，本轮新增 {len(new_papers)}/{min_papers} 篇候选文献。"
                "请检查候选记录并确认最终纳入集合。"
            ),
            papers=session_mgr.get_papers(session_id),
            search_summary=search_summary,
            flow=ScientificReviewService(session_mgr).flow_counts(session_id),
            required_action="confirm_inclusion_snapshot",
        )

        if _stop_flag[0]:
            return

        # The automatic pipeline deliberately pauses at the second human
        # checkpoint. Resuming with ``resume_from=notes`` continues from the
        # confirmed inclusion snapshot without repeating discovery.
        return

        # ━━ 阶段 3：生成笔记 ━━
        try:
            session_mgr.update_session_state(session_id, "reviewing_notes")
        except ValueError:
            pass

        _update_run_status("reviewing_notes", "running",
                          message=f"正在为 {len(papers)} 篇论文生成深度笔记...")

        if papers:
            from llms.client import LLMClient
            from tools.rag_note_generator import RAGNoteGenerator
            llm = LLMClient(provider_config)
            rag = RAGNoteGenerator(provider_config)
            notes_map = {}
            evidence_basis_map = {}

            # ━━━ Skill 注入：加载 notes 类型的自定义提示词 ━━━
            _auto_notes_skill = ""
            _auto_notes_trace = _build_skill_trace("notes")
            _auto_session = session_mgr.load_session(session_id)
            if _auto_session:
                _auto_skills = _auto_session.get("skills", {})
                _auto_notes_id = _auto_skills.get("notes")
                _auto_notes_trace = _build_skill_trace("notes", skill_id=_auto_notes_id or "")
                if _auto_notes_id:
                    try:
                        _auto_notes_data = skill_mgr.get_skill(_auto_notes_id)
                        if _auto_notes_data and not _auto_notes_data.get("deleted"):
                            _auto_notes_skill = str(_auto_notes_data.get("content", ""))
                            _auto_notes_title = str(_auto_notes_data.get("title", "") or "")
                            if _auto_notes_skill:
                                print(f"[NotesSkill] Auto-pipeline loaded skill {_auto_notes_id}: len={len(_auto_notes_skill)}")
                                _auto_notes_trace = _build_skill_trace(
                                    "notes",
                                    skill_id=_auto_notes_id,
                                    skill_title=_auto_notes_title,
                                    loaded=True,
                                    fallback_default=False,
                                    reason="active",
                                )
                            else:
                                print(f"[NotesSkill] Auto-pipeline skill {_auto_notes_id} has empty content, using default")
                                _auto_notes_trace = _build_skill_trace(
                                    "notes",
                                    skill_id=_auto_notes_id,
                                    skill_title=_auto_notes_title,
                                    reason="empty_content",
                                )
                        else:
                            print(f"[NotesSkill] Auto-pipeline skill {_auto_notes_id} deleted/invalid, using default")
                            _auto_notes_trace = _build_skill_trace("notes", skill_id=_auto_notes_id, reason="deleted_or_invalid")
                    except Exception as e:
                        print(f"[NotesSkill] Auto-pipeline failed to load skill {_auto_notes_id}: {e}")
                        _auto_notes_trace = _build_skill_trace("notes", skill_id=_auto_notes_id, reason=f"load_error: {e}")
            else:
                print(f"[NotesSkill] Auto-pipeline: no notes skill configured, using default")
            if not _auto_notes_skill:
                _auto_notes_skill = str(skill_mgr.get_defaults().get("notes", {}).get("content", ""))
            session_mgr.save_traces(session_id, [_auto_notes_trace], append=True)
            with RUN_LOCK:
                existing_traces = RUNS.get(run_key, {}).get("traces", [])
                RUNS[run_key]["traces"] = existing_traces + [_auto_notes_trace]

            for idx, paper in enumerate(papers):
                if _stop_flag[0]:
                    break
                pid = paper.get("paper_id", "")
                title = paper.get("title", pid)
                abstract = paper.get("abstract", "")
                source_info = paper.get("source", "")

                _update_run_status("reviewing_notes", "running",
                                  message=f"正在生成笔记 ({idx+1}/{len(papers)})：{title[:50]}...")

                try:
                    paper_path = None
                    if source_info == "agent_search":
                        paper_path = session_mgr.get_agent_search_paper_path(session_id, pid)
                    elif source_info == "user_custom":
                        paper_path = session_mgr.get_user_custom_paper_path(session_id, pid)
                    elif source_info == "user_upload":
                        paper_path = session_mgr.get_user_upload_paper_path(session_id, title)

                    note_text = rag.generate(
                        pdf_path=str(paper_path) if paper_path else "",
                        paper_title=title,
                        abstract=abstract,
                        topic=topic,
                        skill_content=_auto_notes_skill,
                    )
                    notes_map[pid] = note_text
                    evidence_basis_map[pid] = "full_text" if paper_path and Path(paper_path).exists() else "abstract"
                except Exception as exc:
                    notes_map[pid] = f"## 论文笔记：{title}\n\n生成笔记时出错：{str(exc)}"
                    evidence_basis_map[pid] = "generation_error"

            if notes_map:
                session_mgr.batch_update_paper_notes(session_id, notes_map, evidence_basis_map)

        _update_run_status("reviewing_notes", "running",
                          message=f"笔记生成完成，共 {len(notes_map) if papers else 0} 篇，即将生成深度分析...")

        if _stop_flag[0]:
            return

        # Generate analysis before writing so the final review can use it.
        try:
            _update_run_status("analysis", "running", message="正在生成深度分析报告...")
            analysis_result = _run_session_analysis(
                session_id,
                topic,
                "all",
                provider_config,
                [paper.get("paper_id", "") for paper in papers],
            )
            _update_run_status(
                "analysis",
                "running",
                message="深度分析报告已生成，即将撰写综述...",
                analysis=analysis_result,
            )
        except Exception as exc:
            _update_run_status(
                "analysis",
                "running",
                message=f"深度分析生成失败，将继续撰写综述：{str(exc)}",
                analysis_error=str(exc),
            )

        if _stop_flag[0]:
            return

        # ━━ 阶段 4：撰写综述 ━━
        try:
            session_mgr.update_session_state(session_id, "writing")
        except ValueError:
            pass

        _update_run_status("writing", "running", message="正在撰写综述草稿...")

        # 重新加载 session 获取最新笔记
        session = session_mgr.load_session(session_id)
        papers_data = _accepted_papers(session or {})
        aggregated = []
        for p in papers_data:
            pn = (p.get("notes") or "").strip()
            if pn:
                aggregated.append(f"## {p.get('title', p.get('paper_id', ''))}\n\n{pn}")
        notes = "\n\n---\n\n".join(aggregated)

        if notes.strip():
            from main import run_write_from_notes  # noqa
            selected_ids = [paper.get("paper_id", "") for paper in papers_data]
            analysis_context = _load_analysis_context_for_writing(session_id, selected_ids)
            write_result = run_write_from_notes(
                user_topic=topic,
                notes_content=notes,
                session_id=session_id,
                analysis_context=analysis_context,
                provider_config=provider_config,
                papers_list=papers_data,
                repository_sources=session.get("repositories", []),
            )
            if write_result.get("review"):
                session_mgr.save_review(session_id, write_result["review"], referenced_papers=selected_ids)
                quality_path = session_mgr.root / session_id / "review" / "quality.json"
                session_mgr._write_json(quality_path, write_result.get("quality", {}))
            if write_result.get("traces"):
                session_mgr.save_traces(session_id, write_result["traces"], append=True)
                with RUN_LOCK:
                    existing_traces = RUNS.get(run_key, {}).get("traces", [])
                    RUNS[run_key]["traces"] = existing_traces + write_result["traces"]
            # 状态机要求 writing → reviewing_draft → complete，不能直接跳
            try:
                session_mgr.update_session_state(session_id, "reviewing_draft")
            except ValueError:
                pass
            try:
                session_mgr.update_session_state(session_id, "complete")
            except ValueError:
                pass

        # ━━ 完成 ━━
        _update_run_status("complete", "done",
                          message="🎉 自动流程全部完成！综述已生成，可在右侧查看。",
                          result={"phase": "complete"})

    except Exception as exc:
        _update_run_status("failed", "error",
                          message=f"自动流程失败：{str(exc)}",
                          error=str(exc), error_code="auto_pipeline_failed", retryable=True)
        current_session = session_mgr.load_session(session_id) or {}
        if current_session.get("state") == "searching":
            try:
                session_mgr.update_session_state(session_id, "search_failed")
            except ValueError:
                pass
    finally:
        _stop_flag[0] = True


@router.post("/{session_id}/run/auto")
def run_auto_pipeline(session_id: str, payload: AutoRunRequest) -> dict:
    """【自动模式】一键触发 规划→搜索→笔记→分析→综述 全流程自动执行"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    provider_config = ensure_provider_available(payload.provider)

    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="主题不能为空")
    if payload.resume_from not in {"plan", "notes"}:
        raise HTTPException(status_code=400, detail="resume_from 必须是 plan 或 notes")
    scientific = ScientificReviewService(session_mgr)
    protocol = scientific.ensure_protocol(
        session_id,
        topic=topic,
        language=language_from_config(provider_config),
    )
    if protocol.get("status") != "confirmed":
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "protocol_confirmation_required",
                "message": "请先确认研究协议，再启动自动流程",
                "protocol": protocol,
                "retryable": False,
            },
        )
    inclusion_snapshot = scientific.latest_inclusion_snapshot(session_id)
    if payload.resume_from == "notes" and not inclusion_snapshot:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "inclusion_confirmation_required",
                "message": "请先确认最终纳入论文，再继续自动生成",
                "retryable": False,
            },
        )
    max_loops = effective_search_loop_budget(payload.max_loops, payload.min_papers)

    run_key = _run_key(session_id)

    # 检查是否已有任务在运行
    with RUN_LOCK:
        existing = RUNS.get(run_key)
        if existing and existing.get("status") == "running":
            raise HTTPException(status_code=409, detail="该 Session 已有正在运行的任务，请等待完成或取消后再试")

    # 初始化运行状态；持久化 payload 会自动移除 API Key。
    _stop_flag = [False]
    run = _create_run(session_id, "auto", {
        "topic": topic,
        "max_loops": max_loops,
        "min_papers": payload.min_papers,
        "provider": provider_config,
        "language": language_from_config(provider_config),
        "resume_from": payload.resume_from,
        "protocol_version": protocol.get("version"),
        "inclusion_snapshot_id": (inclusion_snapshot or {}).get("snapshot_id"),
    })
    with RUN_LOCK:
        RUNS[run_key].update({
            "run_id": run["run_id"],
            "session_id": session_id,
            "kind": "auto",
            "status": "running",
            "phase": "queued",
            "checkpoint": "queued",
            "retryable": False,
            "message": "自动流程已启动...",
            "_stop_flag": _stop_flag,
        })
        live_run = dict(RUNS[run_key])
    _persist_run(session_id, live_run)

    # 后台执行
    worker = _tenant_worker(
        _run_auto_pipeline_in_background,
        session_id, topic, max_loops, payload.min_papers, provider_config,
        _stop_flag, run["run_id"], payload.resume_from,
    )
    worker.start()

    return {
        "session_id": session_id,
        "run_id": run["run_id"],
        "status": "started",
        "resume_from": payload.resume_from,
        "protocol_version": protocol.get("version"),
        "max_loops": max_loops,
        "message": "自动流程已启动，请通过 GET /api/sessions/{session_id}/run/status 轮询进度",
    }


