"""Scientific review workflow and auditable evidence state.

The existing agent remains responsible for discovery and language generation.
This module owns the deterministic research-method state that must not be
invented by an LLM: protocol versions, candidate records, screening decisions,
evidence cards, appraisal records, inclusion snapshots, claims and quality
gates.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend.session_manager import paper_identity_keys, papers_match


REVIEW_MODES = {
    "rapid": {
        "label_zh": "快速证据综述",
        "label_en": "Rapid evidence review",
        "default_candidate_cap": 100,
        "min_candidate_cap": 30,
        "max_candidate_cap": 300,
        "can_claim_systematic": False,
    },
    "systematic": {
        "label_zh": "严格系统综述",
        "label_en": "Systematic review",
        "default_candidate_cap": 500,
        "min_candidate_cap": 100,
        "max_candidate_cap": 2000,
        "can_claim_systematic": True,
    },
    "scoping": {
        "label_zh": "范围综述 / 系统映射",
        "label_en": "Scoping review / systematic mapping",
        "default_candidate_cap": 500,
        "min_candidate_cap": 100,
        "max_candidate_cap": 2000,
        "can_claim_systematic": False,
    },
    "technical": {
        "label_zh": "计算机与 AI 技术综述",
        "label_en": "Computer science and AI technical survey",
        "default_candidate_cap": 300,
        "min_candidate_cap": 50,
        "max_candidate_cap": 1000,
        "can_claim_systematic": False,
    },
}

PROTOCOL_DEFAULTS = {
    "sources": ["arXiv", "OpenAlex", "Crossref", "Semantic Scholar", "DBLP"],
    "languages": ["en", "zh"],
    "document_types": ["journal_article", "conference_paper", "preprint"],
    "search_field_scope": ["title", "abstract", "keywords"],
    "evidence_hierarchy_policy": {
        "primary_support_types": [
            "primary_study",
            "benchmark",
            "framework",
            "dataset_or_resource",
        ],
        "secondary_support_types": [
            "systematic_or_scoping_review",
            "narrative_survey",
        ],
        "secondary_allowed_claim_types": [
            "background",
            "taxonomy",
            "research_landscape",
        ],
    },
    "screening_policy": {
        "strategy": "single_human_plus_independent_ai",
        "ai_blinded_to_human": True,
        "conflict_resolution": "human_adjudication",
        "cochrane_dual_human_compliant": False,
    },
    "inclusion_criteria": [
        "The study directly addresses the research question.",
        "The record reports a research method, empirical result, or substantive scholarly synthesis.",
        "Enough metadata or full text is available to assess relevance.",
    ],
    "exclusion_criteria": [
        "The record is outside the stated population, problem, or technical scope.",
        "The item is a duplicate, editorial, slide deck, or non-scholarly page.",
        "The available text is insufficient to verify relevance.",
    ],
    "extraction_fields": [
        "study_design",
        "population_or_dataset",
        "intervention_or_method",
        "comparator_or_baseline",
        "sample_size",
        "outcomes_and_metrics",
        "main_results",
        "uncertainty",
        "limitations",
        "funding_and_conflicts",
        "evidence_locations",
    ],
}

SCREENING_STAGES = {"title_abstract", "full_text"}
SCREENING_DECISIONS = {"include", "exclude", "uncertain"}
EXCLUSION_CODES = {
    "not_relevant",
    "wrong_population_or_problem",
    "wrong_method_or_intervention",
    "wrong_outcome",
    "wrong_document_type",
    "duplicate",
    "insufficient_information",
    "full_text_unavailable",
    "other",
}

STUDY_OR_ARTICLE_TYPES = {
    "primary_study",
    "benchmark",
    "framework",
    "dataset_or_resource",
    "systematic_or_scoping_review",
    "narrative_survey",
    "editorial_or_commentary",
    "other",
    "unclear",
}
PRIMARY_EVIDENCE_TYPES = {
    "primary_study",
    "benchmark",
    "framework",
    "dataset_or_resource",
}
SECONDARY_EVIDENCE_TYPES = {
    "systematic_or_scoping_review",
    "narrative_survey",
}
SECONDARY_ALLOWED_CLAIMS = {"background", "taxonomy", "research_landscape"}
NORMATIVE_CLAIM_PATTERN = re.compile(
    r"(?:应当|应该|应采用|优先(?:采用|微调|选择)|必须|普遍有效|最佳实践|"
    r"\bshould\b|\bmust\b|\bprefer\b|\balways\b|\bbest practice\b)",
    re.IGNORECASE,
)
AGENTIC_TERM_PATTERN = re.compile(r"(?:智能代理|自主代理|\bagentic\b|\bagent\b)", re.IGNORECASE)


SCIENTIFIC_SKILL_MANIFESTS = [
    {
        "id": "protocol",
        "version": "2.0.0",
        "stage": "protocol",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "ReviewQuestion",
        "output_schema": "ReviewProtocol",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["candidate_cap", "criteria_nonempty", "sources_nonempty"],
        "immutable_constraints": ["protocol_must_be_confirmed_before_search"],
    },
    {
        "id": "query_design",
        "version": "2.0.0",
        "stage": "search",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "LockedReviewProtocol",
        "output_schema": "SearchQueryPlan",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["english_database_queries", "source_specific_queries", "fields_filters_dates_recorded"],
        "immutable_constraints": ["query_and_source_ledger_required", "executed_query_must_be_preserved"],
    },
    {
        "id": "title_abstract_screen",
        "version": "2.0.0",
        "stage": "screen",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "CandidateAndProtocol",
        "output_schema": "ScreeningDecision",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["criterion_level_judgements", "uncertainty_allowed", "actor_and_blinding_recorded"],
        "immutable_constraints": ["no_direct_final_inclusion", "ai_must_not_read_human_vote"],
    },
    {
        "id": "fulltext_screen",
        "version": "2.0.0",
        "stage": "screen",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "FullTextCandidateAndProtocol",
        "output_schema": "ScreeningDecision",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["exclusion_reason_required", "evidence_location_required", "conflicts_adjudicated"],
        "immutable_constraints": ["human_inclusion_snapshot_required", "ai_must_not_read_human_vote"],
    },
    {
        "id": "evidence_extract",
        "version": "2.0.0",
        "stage": "read",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "IncludedStudyFullText",
        "output_schema": "ExtractionRecord",
        "model_requirements": ["chat", "structured_output"],
        "validators": [
            "source_location", "basis_label", "required_fields",
            "evidence_level", "quantitative_context", "technical_mechanism",
        ],
        "immutable_constraints": [
            "missing_information_must_not_be_inferred",
            "secondary_evidence_cannot_support_primary_performance_claims",
        ],
    },
    {
        "id": "study_appraise",
        "version": "2.0.0",
        "stage": "analysis",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "ExtractionRecord",
        "output_schema": "StudyAppraisal",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["domain_level_reasons", "tool_matches_design", "technical_domains_complete"],
        "immutable_constraints": ["no_unexplained_single_quality_score"],
    },
    {
        "id": "evidence_synthesize",
        "version": "2.0.0",
        "stage": "analysis",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "EvidenceMatrix",
        "output_schema": "SynthesisGroups",
        "model_requirements": ["chat", "structured_output"],
        "validators": [
            "comparability_assessed", "conflicts_preserved",
            "mechanism_conditions_failures_costs", "secondary_primary_separated",
        ],
        "immutable_constraints": ["no_meta_analysis_without_compatible_effects"],
    },
    {
        "id": "review_outline",
        "version": "2.0.0",
        "stage": "write",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "SynthesisGroupsAndProtocol",
        "output_schema": "ReviewOutline",
        "model_requirements": ["chat"],
        "validators": ["mode_specific_sections"],
        "immutable_constraints": ["organize_by_synthesis_not_by_paper"],
    },
    {
        "id": "review_write",
        "version": "2.0.0",
        "stage": "write",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "VerifiedSynthesisPackage",
        "output_schema": "ReviewDraft",
        "model_requirements": ["chat"],
        "validators": [
            "citation_ids", "methods_from_ledger", "numeric_context",
            "normative_claim_strength", "required_technical_tables",
        ],
        "immutable_constraints": ["no_posthoc_citation_invention"],
    },
    {
        "id": "citation_audit",
        "version": "2.0.0",
        "stage": "audit",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "ReviewDraftAndEvidence",
        "output_schema": "ClaimAudit",
        "model_requirements": [],
        "validators": [
            "reference_exists", "source_in_snapshot", "claim_basis",
            "evidence_type_fit", "numeric_context", "internal_consistency",
        ],
        "immutable_constraints": ["zero_phantom_references"],
    },
    {
        "id": "methodology_audit",
        "version": "2.0.0",
        "stage": "audit",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "CompleteResearchLedger",
        "output_schema": "MethodologyAudit",
        "model_requirements": [],
        "validators": [
            "flow_counts_reconcile", "protocol_version_matches",
            "search_reporting_complete", "screening_conflicts_resolved",
        ],
        "immutable_constraints": ["incomplete_work_cannot_claim_systematic"],
    },
]

_SKILL_PROMPTS = {
    "protocol": {
        "zh-CN": "把研究问题转换为可确认的综述协议；缺失信息标记为待确认，禁止自行扩大研究范围。",
        "en": "Convert the question into a confirmable review protocol; mark missing information as unresolved and never broaden scope silently.",
    },
    "query_design": {
        "zh-CN": "按已锁定协议为每个数据源生成英文检索式、字段映射、过滤器、分页及引用追踪计划；实际执行式和日期必须原样入账。",
        "en": "Create source-specific English queries, field mappings, filters, pagination and citation chasing; preserve exact executed queries and dates.",
    },
    "title_abstract_screen": {
        "zh-CN": "逐条依据纳排标准筛选标题摘要，输出判断、证据、理由和置信度；信息不足时必须输出不确定。",
        "en": "Screen title and abstract against every criterion; return judgements, evidence, rationale and confidence, using uncertain when information is insufficient.",
    },
    "fulltext_screen": {
        "zh-CN": "仅依据全文证据作纳入判断；排除必须给出标准化理由与页码/章节，不可读取全文时标记不确定。",
        "en": "Decide from full-text evidence only; exclusions require a standard reason and page/section, while unavailable text remains uncertain.",
    },
    "evidence_extract": {
        "zh-CN": "区分一级与二级证据；从全文提取机制输入、状态、决策、阈值、粒度、动作、失效传播及带完整语境的定量结果，未报告字段保持空值。",
        "en": "Separate primary from secondary evidence; extract mechanism inputs, state, decisions, thresholds, granularity, actions, failures and fully contextualized quantitative results.",
    },
    "study_appraise": {
        "zh-CN": "选择匹配研究设计的评价规则，逐域给出判断与依据，禁止用无解释的总分替代质量评价。",
        "en": "Apply an appraisal rule matched to study design with domain-level judgements and reasons; never substitute an unexplained score.",
    },
    "evidence_synthesize": {
        "zh-CN": "先判断可比性并分离一级与二级证据，再解释为何有效、何时失效、适用任务、冲突、工程代价和证据边界。",
        "en": "Assess comparability and separate primary/secondary evidence before explaining why methods work, when they fail, applicable tasks, conflicts, cost and boundaries.",
    },
    "review_outline": {
        "zh-CN": "依据协议和综合单元建立综述大纲，按研究问题与主题组织，不按论文逐篇罗列。",
        "en": "Build a mode-specific outline from the protocol and synthesis groups, organized by questions and themes rather than papers.",
    },
    "review_write": {
        "zh-CN": "仅依据经验证综合单元写研究底稿；方法、表格和图由结构化账本生成。数字必须包含数据集、模型、基线、指标和变化类型，规范性建议必须条件化。",
        "en": "Write only from verified synthesis units; derive methods, tables and figures from the ledger. Contextualize every number and condition every normative recommendation.",
    },
    "citation_audit": {
        "zh-CN": "确定性核验引用标识、纳入快照和论断证据位置；不得补造参考文献。",
        "en": "Deterministically verify citation identifiers, the inclusion snapshot and claim locations; never invent references.",
    },
    "methodology_audit": {
        "zh-CN": "对账协议、检索、去重、筛选、提取、评价和写作版本；未满足门禁时只允许未完成草稿。",
        "en": "Reconcile protocol, search, deduplication, screening, extraction, appraisal and writing versions; failed gates permit only an incomplete draft.",
    },
}

_SCHEMA_REQUIRED = {
    "protocol": (["research_question", "mode"], ["protocol_id", "version", "status"]),
    "query_design": (["protocol_id", "sources"], ["queries"]),
    "title_abstract_screen": (["candidate", "protocol"], ["decision", "criterion_judgements"]),
    "fulltext_screen": (["candidate", "protocol", "full_text"], ["decision", "reason_code", "evidence"]),
    "evidence_extract": (["paper_id", "full_text", "fields"], ["paper_id", "fields", "evidence_locations"]),
    "study_appraise": (["paper_id", "extraction"], ["tool", "domains", "overall_judgement"]),
    "evidence_synthesize": (["extractions", "appraisals"], ["groups", "comparability"]),
    "review_outline": (["protocol", "synthesis_groups"], ["sections"]),
    "review_write": (["protocol", "inclusion_snapshot", "outline", "evidence"], ["draft", "claims"]),
    "citation_audit": (["draft", "inclusion_snapshot", "evidence"], ["passed", "claims", "invalid_citations"]),
    "methodology_audit": (["protocol", "search_ledger", "screening", "extractions"], ["passed", "blockers", "output_label"]),
}

for _manifest in SCIENTIFIC_SKILL_MANIFESTS:
    _required_input, _required_output = _SCHEMA_REQUIRED[_manifest["id"]]
    _manifest["input_json_schema"] = {
        "type": "object",
        "required": _required_input,
        "additionalProperties": True,
    }
    _manifest["output_json_schema"] = {
        "type": "object",
        "required": _required_output,
        "additionalProperties": True,
    }
    _manifest["prompt_templates"] = _SKILL_PROMPTS[_manifest["id"]]
    _manifest["failure_states"] = [
        "invalid_input",
        "model_error",
        "schema_validation_failed",
        "evidence_unavailable",
    ]
    _manifest["uncertainty_states"] = [
        "uncertain",
        "requires_human_review",
        "abstract_only",
    ]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _slug_hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:20]


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _cursor_identity(source: str, value: Any) -> str:
    if value in {None, "", "first"}:
        return "1" if str(source).lower() == "openalex" else "0"
    try:
        return str(max(0, int(value)))
    except (TypeError, ValueError):
        return str(value)


def normalize_study_or_article_type(value: Any, title: str = "") -> str:
    raw = f"{value or ''} {title or ''}".strip().lower()
    if any(token in raw for token in ("systematic review", "scoping review", "meta-analysis")):
        return "systematic_or_scoping_review"
    if any(token in raw for token in ("survey", "narrative review", "literature review")):
        return "narrative_survey"
    if any(token in raw for token in ("benchmark", "evaluation suite")):
        return "benchmark"
    if "dataset" in raw:
        return "dataset_or_resource"
    if any(token in raw for token in ("framework", "method proposal", "technical paper")):
        return "framework"
    if any(token in raw for token in ("empirical", "experiment", "case study", "primary")):
        return "primary_study"
    return str(value) if value in STUDY_OR_ARTICLE_TYPES else "unclear"


def quantitative_result_context(result: dict) -> dict:
    """Return deterministic completeness information for a reported number."""
    result = _dict(result)
    required = {
        "dataset_or_task": result.get("dataset_or_task") or result.get("dataset"),
        "base_model": result.get("base_model") or result.get("model"),
        "baseline": result.get("baseline"),
        "metric": result.get("metric"),
        "effect_type": result.get("effect_type"),
        "evidence_location": (
            result.get("evidence_location")
            or result.get("location")
            or result.get("page")
        ),
    }
    has_value = any(
        result.get(key) is not None
        for key in ("baseline_value", "method_value", "effect_value", "value")
    )
    missing = [key for key, value in required.items() if value in (None, "", [])]
    if not has_value:
        missing.append("numeric_value")
    return {
        "complete": not missing,
        "missing_fields": missing,
        "eligible_for_summary": not missing,
        "eligible_for_cross_study_comparison": (
            not missing
            and bool(result.get("aggregation"))
            and result.get("statistical_significance") not in (None, "", "unknown")
        ),
    }


@dataclass
class ScientificReviewService:
    session_manager: Any

    def _dir(self, session_id: str) -> Path:
        path = self.session_manager.root / session_id / "methodology"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _read(self, session_id: str, name: str, default: Any) -> Any:
        value = self.session_manager._read_json(self._dir(session_id) / name)
        return default if value is None else value

    def _write(self, session_id: str, name: str, value: Any) -> None:
        self.session_manager._write_json(self._dir(session_id) / name, value)
        self.session_manager._touch_metadata(self.session_manager.root / session_id)

    def ensure_protocol(
        self,
        session_id: str,
        *,
        topic: str = "",
        mode: str = "rapid",
        language: str = "zh-CN",
    ) -> dict:
        protocols = _list(self._read(session_id, "protocols.json", []))
        if protocols:
            current_id = _dict(self._read(session_id, "current_protocol.json", {})).get("protocol_id")
            current = next((item for item in protocols if item.get("protocol_id") == current_id), protocols[-1])
            if int(current.get("methodology_schema_version") or 1) < 2:
                upgraded = {
                    **current,
                    "methodology_schema_version": 2,
                    "legacy_incomplete_methodology": True,
                    "search_field_scope": _list(current.get("search_field_scope"))
                    or list(PROTOCOL_DEFAULTS["search_field_scope"]),
                    "search_strategy": {
                        "field_scope": _list(current.get("search_field_scope"))
                        or list(PROTOCOL_DEFAULTS["search_field_scope"]),
                        "language_limits": _list(current.get("languages")),
                        "document_type_limits": _list(current.get("document_types")),
                        "date_from": current.get("date_from"),
                        "date_to": current.get("date_to"),
                        "query_peer_reviewed": False,
                        "historical_details_complete": False,
                    },
                    "screening_policy": dict(PROTOCOL_DEFAULTS["screening_policy"]),
                    "evidence_hierarchy_policy": dict(PROTOCOL_DEFAULTS["evidence_hierarchy_policy"]),
                }
                protocols = [
                    upgraded if item.get("protocol_id") == upgraded.get("protocol_id") else item
                    for item in protocols
                ]
                self._write(session_id, "protocols.json", protocols)
                current = upgraded
            return current
        protocol = self.create_protocol(session_id, topic=topic, mode=mode, language=language)
        papers = self.session_manager.get_papers(session_id)
        migrated = False
        for paper in papers:
            if paper.get("status") != "accepted":
                continue
            paper["legacy_status"] = "accepted"
            paper["status"] = "pending"
            paper["screening_stage"] = "title_abstract"
            paper["screening_decision"] = "uncertain"
            self.register_candidate(session_id, paper, source_run_id="legacy_migration")
            self.record_screening(
                session_id,
                paper_id=str(paper.get("paper_id") or ""),
                stage="title_abstract",
                decision="uncertain",
                reason="Legacy accepted record migrated without a historical screening trail; reconfirmation is required.",
                confidence=0.0,
                reviewer="migration",
            )
            migrated = True
        if migrated:
            self.session_manager.save_papers_list(session_id, papers)
        return protocol

    def create_protocol(
        self,
        session_id: str,
        *,
        topic: str,
        mode: str = "rapid",
        language: str = "zh-CN",
        candidate_cap: int | None = None,
        base_protocol_id: str | None = None,
    ) -> dict:
        if mode not in REVIEW_MODES:
            raise ValueError(f"Unsupported review mode: {mode}")
        config = REVIEW_MODES[mode]
        cap = int(candidate_cap or config["default_candidate_cap"])
        if cap < config["min_candidate_cap"] or cap > config["max_candidate_cap"]:
            raise ValueError(
                f"candidate_cap must be between {config['min_candidate_cap']} and {config['max_candidate_cap']}"
            )
        protocols = _list(self._read(session_id, "protocols.json", []))
        version = max([int(item.get("version", 0)) for item in protocols] or [0]) + 1
        is_en = str(language).lower().startswith("en")
        protocol = {
            "protocol_id": f"protocol_{uuid.uuid4().hex[:12]}",
            "version": version,
            "status": "draft",
            "methodology_schema_version": 2,
            "legacy_incomplete_methodology": False,
            "mode": mode,
            "language": "en" if is_en else "zh-CN",
            "research_question": topic.strip(),
            "framework": "PICOC" if mode == "technical" else ("PCC" if mode == "scoping" else "general"),
            "candidate_cap": cap,
            "sources": list(PROTOCOL_DEFAULTS["sources"]),
            "languages": list(PROTOCOL_DEFAULTS["languages"]),
            "document_types": list(PROTOCOL_DEFAULTS["document_types"]),
            "search_field_scope": list(PROTOCOL_DEFAULTS["search_field_scope"]),
            "date_from": None,
            "date_to": None,
            "search_strategy": {
                "field_scope": list(PROTOCOL_DEFAULTS["search_field_scope"]),
                "language_limits": list(PROTOCOL_DEFAULTS["languages"]),
                "document_type_limits": list(PROTOCOL_DEFAULTS["document_types"]),
                "date_from": None,
                "date_to": None,
                "query_peer_reviewed": False,
            },
            "screening_policy": dict(PROTOCOL_DEFAULTS["screening_policy"]),
            "evidence_hierarchy_policy": dict(PROTOCOL_DEFAULTS["evidence_hierarchy_policy"]),
            "inclusion_criteria": list(PROTOCOL_DEFAULTS["inclusion_criteria"]),
            "exclusion_criteria": list(PROTOCOL_DEFAULTS["exclusion_criteria"]),
            "extraction_fields": list(PROTOCOL_DEFAULTS["extraction_fields"]),
            "primary_outcomes": [],
            "comparison_dimensions": (
                ["method_family", "dataset", "baseline", "metric", "reproducibility", "compute_cost"]
                if mode == "technical"
                else ["study_design", "population", "outcome", "context"]
            ),
            "appraisal_profile": "computer_ai" if mode == "technical" else "general",
            "synthesis_method": "systematic_mapping" if mode == "scoping" else "SWiM_or_thematic",
            "base_protocol_id": base_protocol_id,
            "created_at": _now(),
            "updated_at": _now(),
            "confirmed_at": None,
        }
        protocols.append(protocol)
        self._write(session_id, "protocols.json", protocols)
        self._write(session_id, "current_protocol.json", {"protocol_id": protocol["protocol_id"]})
        return protocol

    def update_protocol(self, session_id: str, changes: dict) -> dict:
        protocol = self.ensure_protocol(session_id)
        if protocol.get("status") == "confirmed":
            self.create_protocol(
                session_id,
                topic=str(changes.get("research_question") or protocol.get("research_question") or ""),
                mode=str(changes.get("mode") or protocol.get("mode") or "rapid"),
                language=str(changes.get("language") or protocol.get("language") or "zh-CN"),
                candidate_cap=changes.get("candidate_cap") or protocol.get("candidate_cap"),
                base_protocol_id=protocol.get("protocol_id"),
            )
            return self.update_protocol(session_id, changes)
        allowed = {
            "mode", "language", "research_question", "framework", "candidate_cap",
            "sources", "languages", "document_types", "date_from", "date_to",
            "search_field_scope", "search_strategy", "screening_policy",
            "evidence_hierarchy_policy",
            "inclusion_criteria", "exclusion_criteria", "extraction_fields",
            "primary_outcomes", "comparison_dimensions", "appraisal_profile",
            "synthesis_method",
        }
        next_value = dict(protocol)
        next_value.update({key: value for key, value in changes.items() if key in allowed})
        mode = next_value.get("mode", "rapid")
        if mode not in REVIEW_MODES:
            raise ValueError(f"Unsupported review mode: {mode}")
        cap = int(next_value.get("candidate_cap") or REVIEW_MODES[mode]["default_candidate_cap"])
        cfg = REVIEW_MODES[mode]
        if not cfg["min_candidate_cap"] <= cap <= cfg["max_candidate_cap"]:
            raise ValueError(f"candidate_cap must be between {cfg['min_candidate_cap']} and {cfg['max_candidate_cap']}")
        next_value["candidate_cap"] = cap
        next_value["search_strategy"] = {
            **_dict(protocol.get("search_strategy")),
            **_dict(next_value.get("search_strategy")),
            "field_scope": _list(next_value.get("search_field_scope"))
            or _list(_dict(next_value.get("search_strategy")).get("field_scope")),
            "language_limits": _list(next_value.get("languages")),
            "document_type_limits": _list(next_value.get("document_types")),
            "date_from": next_value.get("date_from"),
            "date_to": next_value.get("date_to"),
        }
        next_value["updated_at"] = _now()
        protocols = _list(self._read(session_id, "protocols.json", []))
        protocols = [next_value if item.get("protocol_id") == protocol.get("protocol_id") else item for item in protocols]
        self._write(session_id, "protocols.json", protocols)
        return next_value

    def confirm_protocol(self, session_id: str) -> dict:
        protocol = self.ensure_protocol(session_id)
        required = {
            "research_question": protocol.get("research_question"),
            "sources": protocol.get("sources"),
            "search_field_scope": protocol.get("search_field_scope"),
            "languages": protocol.get("languages"),
            "document_types": protocol.get("document_types"),
            "inclusion_criteria": protocol.get("inclusion_criteria"),
            "exclusion_criteria": protocol.get("exclusion_criteria"),
            "extraction_fields": protocol.get("extraction_fields"),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(f"Protocol is incomplete: {', '.join(missing)}")
        if protocol.get("date_from") and protocol.get("date_to"):
            if str(protocol["date_from"]) > str(protocol["date_to"]):
                raise ValueError("date_from must not be later than date_to")
        protocol = dict(protocol)
        protocol["status"] = "confirmed"
        protocol["confirmed_at"] = _now()
        protocol["updated_at"] = protocol["confirmed_at"]
        protocols = _list(self._read(session_id, "protocols.json", []))
        protocols = [protocol if item.get("protocol_id") == protocol.get("protocol_id") else item for item in protocols]
        self._write(session_id, "protocols.json", protocols)
        self._initialize_search_queries(session_id, protocol)
        return protocol

    def _initialize_search_queries(self, session_id: str, protocol: dict) -> list[dict]:
        session = self.session_manager.load_session(session_id) or {}
        keywords = _list(session.get("keywords"))
        query_groups = []
        for item in keywords:
            if isinstance(item, dict):
                primary = str(item.get("english") or item.get("original") or "").strip()
                synonyms = [
                    value.strip()
                    for value in re.split(r"[,;|]", str(item.get("synonyms") or ""))
                    if value.strip()
                ]
                terms = list(dict.fromkeys([primary, *synonyms]))
            else:
                terms = [str(item).strip()]
            phrases = [f'"{term}"' if " " in term else term for term in terms[:5] if term]
            if phrases:
                query_groups.append({
                    "concept": primary if isinstance(item, dict) else terms[0],
                    "boolean": " OR ".join(phrases),
                    "compact": " ".join(term.strip('"') for term in phrases),
                })
        if not query_groups:
            question = str(protocol.get("research_question") or "").strip()
            query_groups = [{"concept": question, "boolean": f'"{question}"', "compact": question}]
        source_tools = {
            "arxiv": "arxiv",
            "openalex": "openalex",
            "crossref": "crossref",
            "semantic scholar": "semantic_scholar",
            "dblp": "dblp",
            "pubmed": "pubmed",
            "europe pmc": "europe_pmc",
        }
        plans = []
        required_pages = {
            "rapid": 1,
            "systematic": 3,
            "scoping": 3,
            "technical": 2,
        }.get(protocol.get("mode"), 1)
        for source in protocol.get("sources") or []:
            tool_source = source_tools.get(str(source).strip().lower())
            if not tool_source:
                continue
            pagination_parameter = {
                "arxiv": "start",
                "openalex": "page",
                "crossref": "offset",
                "semantic_scholar": "offset",
                "dblp": "offset",
            }.get(tool_source)
            for group_index, group in enumerate(query_groups, start=1):
                query = group["compact"] if tool_source in {"crossref", "dblp"} else group["boolean"]
                plans.append({
                    "search_query_id": f"query_{uuid.uuid4().hex[:12]}",
                    "protocol_id": protocol.get("protocol_id"),
                    "protocol_version": protocol.get("version"),
                    "source": tool_source,
                    "concept_id": f"concept_{group_index}",
                    "concept": group["concept"],
                    "query": query,
                    "original_query": group["boolean"],
                    "compiled_query": query,
                    "query_syntax": "bibliographic_terms" if tool_source in {"crossref", "dblp"} else "boolean_or",
                    "field_scope": _list(protocol.get("search_field_scope")),
                    "filters": {
                        "date_from": protocol.get("date_from"),
                        "date_to": protocol.get("date_to"),
                        "languages": _list(protocol.get("languages")),
                        "document_types": _list(protocol.get("document_types")),
                    },
                    "pagination_parameter": pagination_parameter,
                    "required_pages": required_pages,
                    "status": "pending",
                    "pages": [],
                    "hit_count": None,
                    "attempt_count": 0,
                    "executed_at": None,
                    "last_updated_at": None,
                    "last_error": None,
                    "created_at": _now(),
                    "completed_at": None,
                })
        if protocol.get("mode") in {"systematic", "scoping"} and any(
            str(source).strip().lower() == "openalex"
            for source in protocol.get("sources") or []
        ):
            for direction in ("cited_by", "references"):
                plans.append({
                    "search_query_id": f"query_{uuid.uuid4().hex[:12]}",
                    "protocol_id": protocol.get("protocol_id"),
                    "protocol_version": protocol.get("version"),
                    "source": "openalex_citations",
                    "query": "",
                    "original_query": "",
                    "compiled_query": "",
                    "field_scope": ["citation_graph"],
                    "filters": {},
                    "stage": "citation_chasing",
                    "direction": direction,
                    "required_pages": 1,
                    "status": "pending",
                    "pages": [],
                    "hit_count": None,
                    "attempt_count": 0,
                    "executed_at": None,
                    "last_updated_at": None,
                    "last_error": None,
                    "created_at": _now(),
                    "completed_at": None,
                })
        self._write(session_id, "search_queries.json", plans)
        return plans

    def refresh_unstarted_search_queries(self, session_id: str) -> list[dict]:
        """Refresh query text after keyword planning without erasing real progress."""
        protocol = self.ensure_protocol(session_id)
        current = [
            item for item in _list(self._read(session_id, "search_queries.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
        ]
        if any(
            item.get("executed_queries")
            or item.get("status") not in {None, "pending"}
            for item in current
        ):
            return current
        return self._initialize_search_queries(session_id, protocol)

    def reconcile_search_ledger(self, session_id: str, retrieval_ledger: dict) -> list[dict]:
        protocol = self.ensure_protocol(session_id)
        plans = [
            item for item in _list(self._read(session_id, "search_queries.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
        ]
        observed = _list(_dict(retrieval_ledger).get("queries"))
        def query_matches(planned: str, executed: str) -> bool:
            planned_tokens = {
                token for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", planned.lower())
                if token not in {"and", "or", "not"}
            }
            executed_tokens = {
                token for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", executed.lower())
                if token not in {"and", "or", "not"}
            }
            if not planned_tokens or not executed_tokens:
                return False
            overlap = len(planned_tokens.intersection(executed_tokens))
            return overlap >= max(1, min(len(planned_tokens), len(executed_tokens)) // 3)
        for plan in plans:
            attempts = [
                item for item in observed
                if str(item.get("source") or "").strip().lower() == str(plan.get("source") or "").lower()
                and (
                    (
                        plan.get("stage") == "citation_chasing"
                        and str(item.get("direction") or "cited_by") == str(plan.get("direction") or "cited_by")
                    )
                    or query_matches(str(plan.get("query") or ""), str(item.get("query") or ""))
                )
            ]
            matches = [item for item in attempts if item.get("success") is not False]
            if attempts:
                plan["attempt_count"] = int(plan.get("attempt_count") or 0) + len(attempts)
                plan["last_updated_at"] = _now()
                plan["executed_at"] = plan.get("executed_at") or _now()
                plan["execution_metadata"] = {
                    "actual_queries": list(dict.fromkeys(
                        str(item.get("query") or "") for item in attempts
                    )),
                    "pages_or_cursors": [
                        item.get("page") if item.get("page") is not None else item.get("cursor")
                        for item in attempts
                    ],
                    "field_scope": _list(plan.get("field_scope")),
                    "filters": _dict(plan.get("filters")),
                }
            if matches:
                prior = _list(plan.get("executed_queries"))
                combined = prior + matches
                unique_attempts = []
                seen_attempts = set()
                for item in combined:
                    identity = _cursor_identity(str(plan.get("source") or ""), item.get("page"))
                    if identity in seen_attempts:
                        continue
                    seen_attempts.add(identity)
                    unique_attempts.append(item)
                required = int(plan.get("required_pages") or 1)
                plan["status"] = "completed" if len(unique_attempts) >= required else "partial"
                plan["executed_queries"] = unique_attempts
                plan["pages"] = [item.get("page") for item in unique_attempts]
                hit_counts = [
                    int(item.get("result_count") or item.get("hit_count") or 0)
                    for item in unique_attempts
                    if item.get("result_count") is not None or item.get("hit_count") is not None
                ]
                plan["hit_count"] = sum(hit_counts) if hit_counts else plan.get("hit_count")
                plan["completed_at"] = _now() if plan["status"] == "completed" else None
                plan["last_error"] = None
            elif attempts:
                plan["status"] = "failed"
                plan["last_error"] = next(
                    (str(item.get("error") or "") for item in reversed(attempts) if item.get("error")),
                    "Search source returned an unsuccessful attempt.",
                )
        self._write(session_id, "search_queries.json", plans)
        return plans

    def version_for_mode(
        self,
        session_id: str,
        *,
        mode: str,
        candidate_cap: int | None = None,
        language: str | None = None,
    ) -> dict:
        current = self.ensure_protocol(session_id)
        next_protocol = self.create_protocol(
            session_id,
            topic=current.get("research_question", ""),
            mode=mode,
            candidate_cap=candidate_cap,
            language=language or current.get("language", "zh-CN"),
            base_protocol_id=current.get("protocol_id"),
        )
        decisions = _list(self._read(session_id, "screening_decisions.json", []))
        for decision in decisions:
            if decision.get("protocol_id") == next_protocol["protocol_id"]:
                continue
        return next_protocol

    def register_candidate(self, session_id: str, paper: dict, *, source_run_id: str = "") -> dict:
        protocol = self.ensure_protocol(
            session_id,
            topic=(self.session_manager.load_session(session_id) or {}).get("topic", ""),
        )
        candidates = _list(self._read(session_id, "candidates.json", []))
        existing = next((item for item in candidates if papers_match(item, paper)), None)
        if existing:
            sources = list(dict.fromkeys(_list(existing.get("sources")) + [paper.get("source_type") or paper.get("source")]))
            existing["sources"] = [item for item in sources if item]
            existing["duplicate_count"] = int(existing.get("duplicate_count", 0)) + 1
            existing["updated_at"] = _now()
            self._write(session_id, "candidates.json", candidates)
            return existing
        cap = int(protocol.get("candidate_cap", 100))
        if len(candidates) >= cap:
            raise ValueError(f"Candidate cap reached ({cap})")
        candidate = {
            **paper,
            "candidate_id": f"candidate_{uuid.uuid4().hex[:12]}",
            "protocol_id": protocol.get("protocol_id"),
            "protocol_version": protocol.get("version"),
            "status": "candidate",
            "screening_stage": "discovered",
            "sources": [item for item in [paper.get("source_type") or paper.get("source")] if item],
            "source_run_ids": [source_run_id] if source_run_id else [],
            "identity_keys": sorted(paper_identity_keys(paper)),
            "duplicate_count": 0,
            "discovered_at": _now(),
            "updated_at": _now(),
        }
        candidates.append(candidate)
        self._write(session_id, "candidates.json", candidates)
        return candidate

    def record_screening(
        self,
        session_id: str,
        *,
        paper_id: str,
        stage: str,
        decision: str,
        reason_code: str | None = None,
        reason: str = "",
        criterion_judgements: list[dict] | None = None,
        evidence: list[dict] | None = None,
        confidence: float | None = None,
        reviewer: str = "human",
        actor_type: str | None = None,
        actor_id: str | None = None,
        model_version: str | None = None,
        blinded_to_peer: bool = False,
        supersedes_decision_id: str | None = None,
    ) -> dict:
        if stage not in SCREENING_STAGES:
            raise ValueError(f"Unsupported screening stage: {stage}")
        if decision not in SCREENING_DECISIONS:
            raise ValueError(f"Unsupported screening decision: {decision}")
        if decision == "exclude" and reason_code not in EXCLUSION_CODES:
            raise ValueError("A standard exclusion reason is required")
        resolved_actor_type = actor_type or ("ai" if reviewer == "ai" else "human")
        if resolved_actor_type not in {"human", "ai", "adjudicator", "migration"}:
            raise ValueError("actor_type must be human, ai, adjudicator, or migration")
        protocol = self.ensure_protocol(session_id)
        candidates = _list(self._read(session_id, "candidates.json", []))
        candidate = next(
            (item for item in candidates if item.get("paper_id") == paper_id or item.get("candidate_id") == paper_id),
            None,
        )
        if not candidate:
            paper = next((item for item in self.session_manager.get_papers(session_id) if item.get("paper_id") == paper_id), None)
            if not paper:
                raise ValueError(f"Paper {paper_id} does not exist")
            candidate = self.register_candidate(session_id, paper)
            candidates = _list(self._read(session_id, "candidates.json", []))
        record = {
            "decision_id": f"decision_{uuid.uuid4().hex[:12]}",
            "candidate_id": candidate.get("candidate_id"),
            "paper_id": candidate.get("paper_id"),
            "protocol_id": protocol.get("protocol_id"),
            "protocol_version": protocol.get("version"),
            "stage": stage,
            "decision": decision,
            "reason_code": reason_code,
            "reason": reason.strip(),
            "criterion_judgements": criterion_judgements or [],
            "evidence": evidence or [],
            "confidence": confidence,
            "reviewer": reviewer,
            "actor_type": resolved_actor_type,
            "actor_id": actor_id or reviewer,
            "model_version": model_version,
            "blinded_to_peer": bool(blinded_to_peer),
            "supersedes_decision_id": supersedes_decision_id,
            "created_at": _now(),
        }
        decisions = _list(self._read(session_id, "screening_decisions.json", []))
        decisions.append(record)
        self._write(session_id, "screening_decisions.json", decisions)
        resolved = self._resolved_screening_decisions(session_id).get(
            (str(candidate.get("candidate_id") or candidate.get("paper_id")), stage),
            record,
        )
        for item in candidates:
            if item.get("candidate_id") == candidate.get("candidate_id"):
                item["screening_stage"] = stage
                item["screening_decision"] = resolved.get("decision")
                item["status"] = (
                    "accepted" if stage == "full_text" and resolved.get("decision") == "include"
                    else "rejected" if resolved.get("decision") == "exclude"
                    else "pending"
                )
                item["updated_at"] = _now()
        self._write(session_id, "candidates.json", candidates)
        return record

    def screening_conflicts(self, session_id: str) -> list[dict]:
        """Return unresolved human/AI disagreements without leaking peer votes."""
        protocol = self.ensure_protocol(session_id)
        decisions = [
            item for item in _list(self._read(session_id, "screening_decisions.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
        ]
        resolutions = {
            (str(item.get("candidate_id")), str(item.get("stage"))): item
            for item in decisions
            if item.get("actor_type") == "adjudicator"
        }
        grouped: dict[tuple[str, str], dict[str, dict]] = {}
        for item in decisions:
            actor_type = str(item.get("actor_type") or "")
            if actor_type not in {"human", "ai"}:
                continue
            key = (str(item.get("candidate_id")), str(item.get("stage")))
            grouped.setdefault(key, {})[actor_type] = item
        conflicts = []
        for key, votes in grouped.items():
            if set(votes) != {"human", "ai"}:
                continue
            human = votes["human"]
            ai = votes["ai"]
            if human.get("decision") == ai.get("decision"):
                continue
            resolution = resolutions.get(key)
            conflicts.append({
                "candidate_id": key[0],
                "paper_id": human.get("paper_id") or ai.get("paper_id"),
                "stage": key[1],
                "human_decision_id": human.get("decision_id"),
                "ai_decision_id": ai.get("decision_id"),
                "human_decision": human.get("decision"),
                "ai_decision": ai.get("decision"),
                "status": "resolved" if resolution else "unresolved",
                "resolution": resolution,
            })
        return conflicts

    def resolve_screening_conflict(
        self,
        session_id: str,
        *,
        paper_id: str,
        stage: str,
        decision: str,
        reason_code: str | None,
        reason: str,
        actor_id: str = "human",
    ) -> dict:
        conflicts = [
            item for item in self.screening_conflicts(session_id)
            if item.get("paper_id") == paper_id
            and item.get("stage") == stage
            and item.get("status") == "unresolved"
        ]
        if not conflicts:
            raise ValueError("No unresolved human/AI screening conflict exists")
        if not reason.strip():
            raise ValueError("An adjudication rationale is required")
        return self.record_screening(
            session_id,
            paper_id=paper_id,
            stage=stage,
            decision=decision,
            reason_code=reason_code,
            reason=reason,
            confidence=1.0,
            reviewer="adjudicator",
            actor_type="adjudicator",
            actor_id=actor_id,
            blinded_to_peer=False,
        )

    def confirm_inclusion_snapshot(self, session_id: str, paper_ids: Iterable[str]) -> dict:
        protocol = self.ensure_protocol(session_id)
        if protocol.get("status") != "confirmed":
            raise ValueError("Confirm the review protocol before confirming included studies")
        unique_ids = list(dict.fromkeys(str(item).strip() for item in paper_ids if str(item).strip()))
        if not unique_ids:
            raise ValueError("At least one paper is required in the final inclusion set")
        papers = self.session_manager.get_papers(session_id)
        missing = [paper_id for paper_id in unique_ids if not any(item.get("paper_id") == paper_id for item in papers)]
        if missing:
            raise ValueError(f"Unknown paper ids: {', '.join(missing)}")
        decisions = _list(self._read(session_id, "screening_decisions.json", []))
        latest_title_by_paper: dict[str, dict] = {}
        for item in decisions:
            if item.get("stage") == "title_abstract":
                latest_title_by_paper[str(item.get("paper_id") or "")] = item
        title_included_ids = {
            paper_id
            for paper_id, item in latest_title_by_paper.items()
            if item.get("decision") == "include"
        }
        for paper_id in unique_ids:
            self.record_screening(
                session_id,
                paper_id=paper_id,
                stage="full_text",
                decision="include",
                reason="Confirmed by the user for the final inclusion set.",
                confidence=1.0,
                reviewer="human",
            )
        for paper_id in sorted(title_included_ids.difference(unique_ids)):
            self.record_screening(
                session_id,
                paper_id=paper_id,
                stage="full_text",
                decision="exclude",
                reason_code="other",
                reason="Not selected by the user at the final full-text inclusion checkpoint.",
                confidence=1.0,
                reviewer="human",
            )
        snapshots = _list(self._read(session_id, "inclusion_snapshots.json", []))
        snapshot = {
            "snapshot_id": f"inclusion_{uuid.uuid4().hex[:12]}",
            "version": len(snapshots) + 1,
            "protocol_id": protocol.get("protocol_id"),
            "protocol_version": protocol.get("version"),
            "paper_ids": unique_ids,
            "confirmed_by": "human",
            "confirmed_at": _now(),
        }
        snapshots.append(snapshot)
        self._write(session_id, "inclusion_snapshots.json", snapshots)
        return snapshot

    def latest_inclusion_snapshot(self, session_id: str) -> dict | None:
        snapshots = _list(self._read(session_id, "inclusion_snapshots.json", []))
        protocol = self.ensure_protocol(session_id)
        matching = [item for item in snapshots if item.get("protocol_id") == protocol.get("protocol_id")]
        return matching[-1] if matching else None

    def save_extraction(self, session_id: str, paper_id: str, fields: dict) -> dict:
        protocol = self.ensure_protocol(session_id)
        papers = self.session_manager.get_papers(session_id)
        paper = next((item for item in papers if item.get("paper_id") == paper_id), None)
        if not paper:
            raise ValueError(f"Paper {paper_id} does not exist")
        basis = fields.get("evidence_basis") or paper.get("evidence_basis") or (
            "full_text" if paper.get("pdf_status") == "available" else "abstract"
        )
        article_type = normalize_study_or_article_type(
            fields.get("study_or_article_type") or fields.get("study_design"),
            str(paper.get("title") or ""),
        )
        quantitative_results = []
        for item in _list(fields.get("quantitative_results")):
            if not isinstance(item, dict):
                continue
            quantitative_results.append({
                **item,
                "context_validation": quantitative_result_context(item),
            })
        technical_mechanism = {
            "inputs": [],
            "internal_state": None,
            "decision_rule": None,
            "thresholds": [],
            "trigger_granularity": None,
            "actions": [],
            "fusion_strategy": None,
            "failure_propagation": [],
            "applicability_conditions": [],
            **_dict(fields.get("technical_mechanism")),
        }
        record = {
            "extraction_id": f"extract_{uuid.uuid4().hex[:12]}",
            "paper_id": paper_id,
            "protocol_id": protocol.get("protocol_id"),
            "protocol_version": protocol.get("version"),
            "study_design": fields.get("study_design"),
            "study_or_article_type": article_type,
            "evidence_level": (
                "primary" if article_type in PRIMARY_EVIDENCE_TYPES
                else "secondary" if article_type in SECONDARY_EVIDENCE_TYPES
                else "unclear"
            ),
            "population_or_dataset": fields.get("population_or_dataset"),
            "intervention_or_method": fields.get("intervention_or_method"),
            "comparator_or_baseline": fields.get("comparator_or_baseline"),
            "sample_size": fields.get("sample_size"),
            "outcomes_and_metrics": _list(fields.get("outcomes_and_metrics")),
            "main_results": _list(fields.get("main_results")),
            "quantitative_results": quantitative_results,
            "technical_mechanism": technical_mechanism,
            "uncertainty": fields.get("uncertainty"),
            "limitations": _list(fields.get("limitations")),
            "funding_and_conflicts": fields.get("funding_and_conflicts"),
            "evidence_locations": _list(fields.get("evidence_locations")),
            "computer_ai": _dict(fields.get("computer_ai")),
            "evidence_basis": basis,
            "confidence": fields.get("confidence"),
            "review_status": fields.get("review_status", "ai_draft"),
            "schema_version": 2,
            "created_at": _now(),
            "updated_at": _now(),
        }
        records = _list(self._read(session_id, "extractions.json", []))
        records = [item for item in records if not (
            item.get("paper_id") == paper_id and item.get("protocol_id") == protocol.get("protocol_id")
        )]
        records.append(record)
        self._write(session_id, "extractions.json", records)
        return record

    def save_appraisal(self, session_id: str, paper_id: str, appraisal: dict) -> dict:
        protocol = self.ensure_protocol(session_id)
        domains = _list(appraisal.get("domains"))
        required_technical_domains = {
            "baseline_fairness",
            "data_leakage",
            "statistical_sufficiency",
            "ablation",
            "reproducibility",
            "external_validity",
            "compute_cost",
        }
        observed_domains = {
            str(item.get("id") or item.get("name") or "").strip().lower().replace(" ", "_")
            for item in domains if isinstance(item, dict)
        }
        missing_domains = sorted(
            required_technical_domains - observed_domains
            if protocol.get("mode") == "technical"
            else set()
        )
        record = {
            "appraisal_id": f"appraisal_{uuid.uuid4().hex[:12]}",
            "paper_id": paper_id,
            "protocol_id": protocol.get("protocol_id"),
            "protocol_version": protocol.get("version"),
            "profile": appraisal.get("profile") or protocol.get("appraisal_profile"),
            "study_design": appraisal.get("study_design"),
            "domains": domains,
            "overall_judgement": appraisal.get("overall_judgement", "unclear"),
            "rationale": appraisal.get("rationale", ""),
            "review_status": appraisal.get("review_status", "ai_draft"),
            "completeness": {
                "required_domains": sorted(required_technical_domains)
                if protocol.get("mode") == "technical" else [],
                "missing_domains": missing_domains,
                "complete": not missing_domains,
            },
            "schema_version": 2,
            "created_at": _now(),
        }
        records = _list(self._read(session_id, "appraisals.json", []))
        records = [item for item in records if not (
            item.get("paper_id") == paper_id and item.get("protocol_id") == protocol.get("protocol_id")
        )]
        records.append(record)
        self._write(session_id, "appraisals.json", records)
        return record

    def _resolved_screening_decisions(self, session_id: str) -> dict[tuple[str, str], dict]:
        protocol = self.ensure_protocol(session_id)
        decisions = [
            item for item in _list(self._read(session_id, "screening_decisions.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
        ]
        grouped: dict[tuple[str, str], dict[str, dict]] = {}
        for item in decisions:
            key = (
                str(item.get("candidate_id") or item.get("paper_id") or ""),
                str(item.get("stage") or ""),
            )
            grouped.setdefault(key, {})[str(item.get("actor_type") or item.get("reviewer") or "human")] = item
        resolved: dict[tuple[str, str], dict] = {}
        for key, votes in grouped.items():
            if votes.get("adjudicator"):
                resolved[key] = votes["adjudicator"]
                continue
            human = votes.get("human")
            ai = votes.get("ai")
            if human and ai:
                if human.get("decision") == ai.get("decision"):
                    resolved[key] = human
                else:
                    resolved[key] = {
                        **human,
                        "decision": "uncertain",
                        "reason": "Unresolved disagreement between human and independent AI screening.",
                        "conflict": True,
                    }
                continue
            resolved[key] = human or ai or list(votes.values())[-1]
        return resolved

    def flow_counts(self, session_id: str) -> dict:
        candidates = _list(self._read(session_id, "candidates.json", []))
        decisions = list(self._resolved_screening_decisions(session_id).values())
        unique_candidates = len(candidates)
        duplicates = sum(int(item.get("duplicate_count", 0)) for item in candidates)
        title_latest: dict[str, dict] = {}
        full_latest: dict[str, dict] = {}
        for item in decisions:
            target = title_latest if item.get("stage") == "title_abstract" else full_latest
            target[str(item.get("candidate_id") or item.get("paper_id"))] = item
        latest_snapshot = self.latest_inclusion_snapshot(session_id)
        protocol = self.ensure_protocol(session_id)
        query_plans = [
            item for item in _list(self._read(session_id, "search_queries.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
        ]
        unresolved = 0
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id") or candidate.get("paper_id"))
            title = title_latest.get(candidate_id)
            full = full_latest.get(candidate_id)
            if not title or title.get("decision") == "uncertain":
                unresolved += 1
            elif title.get("decision") == "include" and (
                not full or full.get("decision") == "uncertain"
            ):
                unresolved += 1
        return {
            "discovered": unique_candidates + duplicates,
            "duplicates_removed": duplicates,
            "unique_candidates": unique_candidates,
            "title_abstract_screened": len(title_latest),
            "title_abstract_included": sum(1 for item in title_latest.values() if item.get("decision") == "include"),
            "title_abstract_excluded": sum(1 for item in title_latest.values() if item.get("decision") == "exclude"),
            "full_text_assessed": len(full_latest),
            "full_text_excluded": sum(1 for item in full_latest.values() if item.get("decision") == "exclude"),
            "included": len(_list((latest_snapshot or {}).get("paper_ids"))),
            "unresolved": unresolved,
            "queries_planned": len(query_plans),
            "queries_completed": sum(1 for item in query_plans if item.get("status") == "completed"),
            "screening_conflicts": len([
                item for item in self.screening_conflicts(session_id)
                if item.get("status") == "unresolved"
            ]),
        }

    def build_methodology_context(self, session_id: str, language: str = "zh-CN") -> str:
        report = self.methodology_report(session_id)
        protocol = self.ensure_protocol(session_id)
        is_en = str(language).lower().startswith("en")
        if is_en:
            return (
                "## Verified methodology ledger (deterministic; do not alter)\n"
                f"{json.dumps(report, ensure_ascii=False, indent=2)}\n"
                "- Only these values may be reported as methods or flow counts. Missing values must be labelled not recorded.\n"
            )
        return (
            "## 已核验的方法学账本（确定性生成，不得改写数字）\n"
            f"{json.dumps(report, ensure_ascii=False, indent=2)}\n"
            "- 方法和流程数字只能引用以上账本；缺失值必须写“未记录”。\n"
        )

    def methodology_report(self, session_id: str) -> dict:
        protocol = self.ensure_protocol(session_id)
        flow = self.flow_counts(session_id)
        plans = [
            item for item in _list(self._read(session_id, "search_queries.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
        ]
        decisions = list(self._resolved_screening_decisions(session_id).values())
        exclusion_reasons: dict[str, int] = {}
        for item in decisions:
            if item.get("decision") != "exclude":
                continue
            key = str(item.get("reason_code") or "other")
            exclusion_reasons[key] = exclusion_reasons.get(key, 0) + 1
        reconciliation = {
            "discovery_reconciles": (
                flow.get("discovered", 0) - flow.get("duplicates_removed", 0)
                == flow.get("unique_candidates", 0)
            ),
            "title_abstract_reconciles": (
                flow.get("title_abstract_screened", 0)
                == flow.get("title_abstract_included", 0)
                + flow.get("title_abstract_excluded", 0)
                + sum(
                    1 for item in decisions
                    if item.get("stage") == "title_abstract"
                    and item.get("decision") == "uncertain"
                )
            ),
            "full_text_reconciles": (
                flow.get("full_text_assessed", 0)
                == flow.get("included", 0)
                + flow.get("full_text_excluded", 0)
                + sum(
                    1 for item in decisions
                    if item.get("stage") == "full_text"
                    and item.get("decision") == "uncertain"
                )
            ),
        }
        policy = {
            **dict(PROTOCOL_DEFAULTS["screening_policy"]),
            **_dict(protocol.get("screening_policy")),
        }
        return {
            "schema_version": 2,
            "protocol": {
                "protocol_id": protocol.get("protocol_id"),
                "version": protocol.get("version"),
                "status": protocol.get("status"),
                "mode": protocol.get("mode"),
                "research_question": protocol.get("research_question"),
                "sources": _list(protocol.get("sources")),
                "field_scope": _list(protocol.get("search_field_scope")),
                "date_from": protocol.get("date_from"),
                "date_to": protocol.get("date_to"),
                "languages": _list(protocol.get("languages")),
                "document_types": _list(protocol.get("document_types")),
                "inclusion_criteria": _list(protocol.get("inclusion_criteria")),
                "exclusion_criteria": _list(protocol.get("exclusion_criteria")),
            },
            "screening_policy": policy,
            "ai_participation_disclosure": (
                "One human reviewer plus an independent AI screen; disagreements require human adjudication. "
                "This is not dual-human Cochrane-compliant screening."
            ),
            "search_queries": [
                {
                    "search_query_id": item.get("search_query_id"),
                    "source": item.get("source"),
                    "original_query": item.get("original_query", item.get("query")),
                    "compiled_query": item.get("compiled_query", item.get("query")),
                    "field_scope": _list(item.get("field_scope")),
                    "filters": _dict(item.get("filters")),
                    "executed_at": item.get("executed_at"),
                    "completed_at": item.get("completed_at"),
                    "status": item.get("status"),
                    "pages_or_cursors": _list(item.get("pages")),
                    "hit_count": item.get("hit_count"),
                    "attempt_count": int(item.get("attempt_count") or 0),
                    "last_error": item.get("last_error"),
                }
                for item in plans
            ],
            "flow": flow,
            "exclusion_reason_counts": exclusion_reasons,
            "reconciliation": reconciliation,
            "reconciled": all(reconciliation.values()),
            "unresolved_conflicts": [
                item for item in self.screening_conflicts(session_id)
                if item.get("status") == "unresolved"
            ],
            "inclusion_snapshot": self.latest_inclusion_snapshot(session_id),
        }

    def build_synthesis_groups(self, session_id: str, paper_ids: Iterable[str]) -> list[dict]:
        """Create conservative comparability groups from typed extraction fields."""
        protocol = self.ensure_protocol(session_id)
        snapshot = self.latest_inclusion_snapshot(session_id) or {}
        selected = set(paper_ids)
        extractions = [
            item for item in _list(self._read(session_id, "extractions.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
            and item.get("paper_id") in selected
        ]
        buckets: dict[str, list[dict]] = {}
        for item in extractions:
            method = str(item.get("intervention_or_method") or "").strip()
            design = str(item.get("study_design") or "").strip()
            population = str(item.get("population_or_dataset") or "").strip()
            raw_key = method or design or population or "unclassified"
            key = re.sub(r"\s+", " ", raw_key.lower())[:160]
            buckets.setdefault(key, []).append(item)
        groups = []
        for key, items in buckets.items():
            compatible = len(items) > 1 and all(
                item.get("outcomes_and_metrics") for item in items
            )
            groups.append({
                "synthesis_group_id": f"group_{_slug_hash(protocol.get('protocol_id', '') + key)}",
                "protocol_id": protocol.get("protocol_id"),
                "inclusion_snapshot_id": snapshot.get("snapshot_id"),
                "label": key,
                "paper_ids": [item.get("paper_id") for item in items],
                "primary_paper_ids": [
                    item.get("paper_id") for item in items
                    if item.get("study_or_article_type") in PRIMARY_EVIDENCE_TYPES
                ],
                "secondary_paper_ids": [
                    item.get("paper_id") for item in items
                    if item.get("study_or_article_type") in SECONDARY_EVIDENCE_TYPES
                ],
                "comparability": "potentially_comparable" if compatible else "narrative_only",
                "synthesis_method": (
                    "SWiM_or_thematic" if not compatible
                    else protocol.get("synthesis_method", "SWiM_or_thematic")
                ),
                "meta_analysis_allowed": False,
                "agreements": [],
                "conflicts": [],
                "possible_explanations": [],
                "why_it_works": [
                    _dict(item.get("technical_mechanism")).get("decision_rule")
                    for item in items
                    if _dict(item.get("technical_mechanism")).get("decision_rule")
                ],
                "failure_conditions": [
                    condition
                    for item in items
                    for condition in _list(
                        _dict(item.get("technical_mechanism")).get("failure_propagation")
                    )
                ],
                "applicable_tasks_or_conditions": [
                    condition
                    for item in items
                    for condition in _list(
                        _dict(item.get("technical_mechanism")).get("applicability_conditions")
                    )
                ],
                "engineering_costs": [
                    _dict(item.get("computer_ai")).get("compute_cost")
                    for item in items
                    if _dict(item.get("computer_ai")).get("compute_cost")
                ],
                "evidence_gaps": [],
                "applicability_boundaries": [],
                "certainty": "not_assessed",
                "created_at": _now(),
            })
        self._write(session_id, "synthesis_groups.json", groups)
        return groups

    def quality_gate(self, session_id: str, *, requested_paper_ids: Iterable[str] | None = None) -> dict:
        protocol = self.ensure_protocol(session_id)
        snapshot = self.latest_inclusion_snapshot(session_id)
        selected = list(dict.fromkeys(requested_paper_ids or []))
        snapshot_ids = _list((snapshot or {}).get("paper_ids"))
        search_runs = _list((self.session_manager.load_session(session_id) or {}).get("search_runs"))
        extractions = _list(self._read(session_id, "extractions.json", []))
        appraisals = _list(self._read(session_id, "appraisals.json", []))
        current_extractions = {
            item.get("paper_id"): item
            for item in extractions
            if item.get("protocol_id") == protocol.get("protocol_id")
        }
        blockers = []
        warnings = []
        dimensions = {
            "methodology_completeness": {"passed": True, "issues": []},
            "evidence_fit": {"passed": True, "issues": []},
            "quantitative_context": {"passed": True, "issues": []},
            "internal_consistency": {"passed": True, "issues": []},
            "citation_integrity": {"passed": True, "issues": []},
            "claim_strength": {"passed": True, "issues": []},
            "artifact_completeness": {"passed": True, "issues": []},
            "reference_hygiene": {"passed": True, "issues": []},
        }
        methodology = self.methodology_report(session_id)
        if protocol.get("status") != "confirmed":
            blockers.append("protocol_not_confirmed")
            dimensions["methodology_completeness"]["issues"].append("protocol_not_confirmed")
        if protocol.get("legacy_incomplete_methodology"):
            if protocol.get("mode") in {"systematic", "technical"}:
                blockers.append("legacy_incomplete_methodology")
            else:
                warnings.append("legacy_incomplete_methodology")
            dimensions["methodology_completeness"]["issues"].append("legacy_incomplete_methodology")
        if not search_runs:
            warnings.append("search_ledger_empty")
        if not methodology.get("reconciled"):
            issue = "flow_counts_do_not_reconcile"
            if protocol.get("mode") in {"systematic", "technical"}:
                blockers.append(issue)
            else:
                warnings.append(issue)
            dimensions["methodology_completeness"]["issues"].append(issue)
        flow = self.flow_counts(session_id)
        if (
            protocol.get("mode") == "systematic"
            and flow.get("queries_completed", 0) < flow.get("queries_planned", 0)
        ):
            blockers.append("configured_search_queries_incomplete")
            dimensions["methodology_completeness"]["issues"].append(
                "configured_search_queries_incomplete"
            )
        if protocol.get("mode") == "systematic":
            incomplete_query_metadata = [
                item.get("search_query_id")
                for item in methodology.get("search_queries", [])
                if item.get("status") == "completed"
                and (
                    not item.get("compiled_query")
                    or not item.get("executed_at")
                    or not item.get("field_scope")
                )
            ]
            if incomplete_query_metadata:
                blockers.append("search_reporting_metadata_incomplete")
                dimensions["methodology_completeness"]["issues"].append(
                    "search_reporting_metadata_incomplete"
                )
        if not snapshot:
            blockers.append("inclusion_snapshot_not_confirmed")
        elif selected and sorted(selected) != sorted(snapshot_ids):
            blockers.append("selection_differs_from_inclusion_snapshot")
        missing_extractions = [paper_id for paper_id in snapshot_ids if paper_id not in current_extractions]
        if missing_extractions:
            blockers.append("evidence_extraction_incomplete")
            dimensions["evidence_fit"]["issues"].append("evidence_extraction_incomplete")
        abstract_only = [
            paper_id for paper_id in snapshot_ids
            if _dict(current_extractions.get(paper_id)).get("evidence_basis") == "abstract"
        ]
        if abstract_only:
            warnings.append("abstract_only_evidence_present")
            if protocol.get("mode") == "systematic":
                blockers.append("full_text_required_for_systematic_review")
        appraisal_ids = {
            item.get("paper_id")
            for item in appraisals
            if item.get("protocol_id") == protocol.get("protocol_id")
        }
        missing_appraisals = [paper_id for paper_id in snapshot_ids if paper_id not in appraisal_ids]
        if missing_appraisals:
            if protocol.get("mode") in {"systematic", "technical"}:
                blockers.append("study_appraisal_incomplete")
            else:
                warnings.append("study_appraisal_incomplete")
            dimensions["evidence_fit"]["issues"].append("study_appraisal_incomplete")
        incomplete_appraisals = [
            item.get("paper_id")
            for item in appraisals
            if item.get("protocol_id") == protocol.get("protocol_id")
            and item.get("paper_id") in snapshot_ids
            and not _dict(item.get("completeness")).get("complete", True)
        ]
        if incomplete_appraisals and protocol.get("mode") == "technical":
            blockers.append("technical_appraisal_domains_incomplete")
            dimensions["evidence_fit"]["issues"].append(
                "technical_appraisal_domains_incomplete"
            )
        incomplete_numbers = [
            {
                "paper_id": paper_id,
                "missing_fields": _dict(item.get("context_validation")).get("missing_fields", []),
            }
            for paper_id, extraction in current_extractions.items()
            for item in _list(extraction.get("quantitative_results"))
            if not _dict(item.get("context_validation")).get("complete")
        ]
        if incomplete_numbers:
            warnings.append("quantitative_results_require_context")
            dimensions["quantitative_context"]["issues"].append(
                "quantitative_results_require_context"
            )
        if flow.get("unresolved", 0):
            if protocol.get("mode") == "systematic":
                blockers.append("screening_decisions_unresolved")
            else:
                warnings.append("screening_decisions_unresolved")
            dimensions["methodology_completeness"]["issues"].append(
                "screening_decisions_unresolved"
            )
        unresolved_conflicts = [
            item for item in self.screening_conflicts(session_id)
            if item.get("status") == "unresolved"
        ]
        if unresolved_conflicts:
            blockers.append("screening_conflicts_unresolved")
            dimensions["methodology_completeness"]["issues"].append(
                "screening_conflicts_unresolved"
            )
        if protocol.get("mode") == "systematic":
            decisions = [
                item for item in _list(self._read(session_id, "screening_decisions.json", []))
                if item.get("protocol_id") == protocol.get("protocol_id")
                and item.get("stage") == "full_text"
            ]
            by_candidate: dict[str, set[str]] = {}
            for item in decisions:
                by_candidate.setdefault(
                    str(item.get("candidate_id") or item.get("paper_id")),
                    set(),
                ).add(str(item.get("actor_type") or item.get("reviewer")))
            missing_independent_ai = [
                key for key, actors in by_candidate.items()
                if not {"human", "ai"}.issubset(actors)
                and "adjudicator" not in actors
            ]
            if missing_independent_ai or not by_candidate:
                blockers.append("independent_ai_fulltext_screen_missing")
                dimensions["methodology_completeness"]["issues"].append(
                    "independent_ai_fulltext_screen_missing"
                )
        can_claim_systematic = bool(
            REVIEW_MODES.get(protocol.get("mode"), {}).get("can_claim_systematic")
            and not blockers
            and search_runs
        )
        for dimension in dimensions.values():
            dimension["issues"] = list(dict.fromkeys(dimension["issues"]))
            dimension["passed"] = not dimension["issues"]
        output_label = (
            "ai_assisted_systematic_review_draft"
            if can_claim_systematic
            else "technical_evidence_review_draft"
            if protocol.get("mode") == "technical" and not blockers
            else "scoping_review_draft"
            if protocol.get("mode") == "scoping" and not blockers
            else "rapid_evidence_review_draft"
            if protocol.get("mode") == "rapid" and not blockers
            else "incomplete_research_draft"
        )
        return {
            "ok": not blockers,
            "output_label": output_label,
            "can_claim_systematic": can_claim_systematic,
            "blockers": blockers,
            "warnings": warnings,
            "missing_extraction_paper_ids": missing_extractions,
            "abstract_only_paper_ids": abstract_only,
            "missing_appraisal_paper_ids": missing_appraisals,
            "incomplete_appraisal_paper_ids": incomplete_appraisals,
            "quantitative_context_issues": incomplete_numbers,
            "screening_conflicts": unresolved_conflicts,
            "dimensions": dimensions,
            "methodology_report": methodology,
            "protocol_id": protocol.get("protocol_id"),
            "protocol_version": protocol.get("version"),
            "inclusion_snapshot_id": (snapshot or {}).get("snapshot_id"),
            "skill_versions": {item["id"]: item["version"] for item in SCIENTIFIC_SKILL_MANIFESTS},
        }

    def audit_summary(self, session_id: str) -> dict:
        protocol = self.ensure_protocol(session_id)
        gate = self.quality_gate(session_id)
        return {
            "protocol": protocol,
            "flow": self.flow_counts(session_id),
            "quality_gate": gate,
            "methodology_report": self.methodology_report(session_id),
            "screening_conflicts": self.screening_conflicts(session_id),
            "inclusion_snapshot": self.latest_inclusion_snapshot(session_id),
            "search_queries": _list(self._read(session_id, "search_queries.json", [])),
            "extractions": _list(self._read(session_id, "extractions.json", [])),
            "appraisals": _list(self._read(session_id, "appraisals.json", [])),
            "claims": _list(self._read(session_id, "claims.json", [])),
            "skill_manifests": SCIENTIFIC_SKILL_MANIFESTS,
        }

    def write_review_version(self, session_id: str, review: str, gate: dict) -> dict:
        versions = _list(self._read(session_id, "review_versions.json", []))
        record = {
            "review_version_id": f"review_{uuid.uuid4().hex[:12]}",
            "version": len(versions) + 1,
            "protocol_id": gate.get("protocol_id"),
            "protocol_version": gate.get("protocol_version"),
            "inclusion_snapshot_id": gate.get("inclusion_snapshot_id"),
            "skill_versions": gate.get("skill_versions", {}),
            "output_label": gate.get("output_label"),
            "content_sha256": hashlib.sha256(review.encode("utf-8")).hexdigest(),
            "created_at": _now(),
        }
        versions.append(record)
        self._write(session_id, "review_versions.json", versions)
        return record

    def audit_review_claims(self, session_id: str, review: str, papers: list[dict]) -> dict:
        """Build a deterministic sentence/paragraph-level claim ledger."""
        protocol = self.ensure_protocol(session_id)
        snapshot = self.latest_inclusion_snapshot(session_id) or {}
        source_map = {
            f"P{index}": paper.get("paper_id")
            for index, paper in enumerate(papers, start=1)
        }
        extraction_by_paper = {
            str(item.get("paper_id") or ""): item
            for item in _list(self._read(session_id, "extractions.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
        }
        claims = []
        invalid_citations = set()
        supported = 0
        unsupported = 0
        evidence_mismatches = []
        quantitative_context_issues = []
        normative_strength_issues = []
        terminology_issues = []
        blocks = re.split(r"\n\s*\n", review)
        for block in blocks:
            text = re.sub(r"\s+", " ", block).strip()
            if (
                len(text) < 45
                or text.startswith(("#", "|", "- "))
                or re.match(r"^\[\w+\]\s", text)
            ):
                continue
            citation_ids = re.findall(r"\[(P\d+)\]", text, flags=re.I)
            normalized = [item.upper() for item in citation_ids]
            paper_ids = [source_map[item] for item in normalized if item in source_map]
            invalid = [item for item in normalized if item not in source_map]
            invalid_citations.update(invalid)
            marked_synthesis = bool(re.search(
                r"(?:\[author synthesis\]|\[researcher synthesis\]|【作者综合判断】|【研究者综合判断】)",
                text,
                flags=re.I,
            ))
            status = "supported" if paper_ids and not invalid else (
                "invalid_citation" if invalid else (
                    "author_synthesis_marked" if marked_synthesis else "author_synthesis_unverified"
                )
            )
            evidence_locations = [
                {
                    "paper_id": paper_id,
                    **location,
                }
                for paper_id in paper_ids
                for location in _list(_dict(extraction_by_paper.get(str(paper_id))).get("evidence_locations"))
            ]
            cited_extractions = [
                _dict(extraction_by_paper.get(str(paper_id)))
                for paper_id in paper_ids
            ]
            source_types = [
                normalize_study_or_article_type(
                    extraction.get("study_or_article_type")
                    or extraction.get("study_design"),
                    next(
                        (
                            str(paper.get("title") or "")
                            for paper in papers
                            if paper.get("paper_id") == extraction.get("paper_id")
                        ),
                        "",
                    ),
                )
                for extraction in cited_extractions
            ]
            numeric_claim = bool(re.search(
                r"(?:\d+(?:\.\d+)?\s*%|\b0\.\d+\b|\b\d+(?:\.\d+)?\s*(?:ms|s|秒|FLOPs?|个百分点)\b)",
                text,
                flags=re.I,
            ))
            normative_claim = bool(NORMATIVE_CLAIM_PATTERN.search(text))
            taxonomy_claim = bool(re.search(
                r"(?:分类|谱系|路线|范式|taxonomy|landscape|paradigm)",
                text,
                flags=re.I,
            ))
            claim_type = (
                "practice_recommendation" if normative_claim
                else "quantitative_performance" if numeric_claim
                else "taxonomy" if taxonomy_claim
                else "technical_or_empirical"
            )
            primary_support = sum(
                1 for item in source_types if item in PRIMARY_EVIDENCE_TYPES
            )
            secondary_only = bool(source_types) and all(
                item in SECONDARY_EVIDENCE_TYPES for item in source_types
            )
            evidence_fit = not (
                secondary_only
                and claim_type not in SECONDARY_ALLOWED_CLAIMS
            )
            if not evidence_fit:
                evidence_mismatches.append({
                    "claim": text[:400],
                    "claim_type": claim_type,
                    "citation_ids": normalized,
                    "source_types": source_types,
                })
            complete_results = [
                result
                for extraction in cited_extractions
                for result in _list(extraction.get("quantitative_results"))
                if _dict(result.get("context_validation")).get("complete")
            ]
            numeric_context_complete = not numeric_claim or bool(complete_results)
            if not numeric_context_complete:
                quantitative_context_issues.append({
                    "claim": text[:400],
                    "citation_ids": normalized,
                    "reason": "No cited structured quantitative result contains the required context.",
                })
            normative_strength_ok = not normative_claim or (
                primary_support >= 2
                and not secondary_only
                and bool(re.search(
                    r"(?:在.*条件|对于.*任务|现有证据|可能|建议考虑|"
                    r"under .* conditions|available evidence|may|could|consider)",
                    text,
                    flags=re.I,
                ))
            )
            if not normative_strength_ok:
                normative_strength_issues.append({
                    "claim": text[:400],
                    "citation_ids": normalized,
                    "primary_support_count": primary_support,
                })
            agentic_criteria_met = any(
                _dict(extraction.get("technical_mechanism")).get("agentic_criteria_met")
                for extraction in cited_extractions
            )
            if AGENTIC_TERM_PATTERN.search(text) and not agentic_criteria_met:
                terminology_issues.append({
                    "claim": text[:400],
                    "term": "agentic",
                    "reason": "No cited evidence card verifies goal, state, action and feedback-loop criteria.",
                })
            support_strength = (
                "located_full_text_evidence"
                if evidence_locations
                else "source_linked_without_location"
                if paper_ids
                else "unverified_author_synthesis"
            )
            supported += int(status == "supported")
            unsupported += int(status in {"invalid_citation", "author_synthesis_unverified"})
            claims.append({
                "claim_id": f"claim_{uuid.uuid4().hex[:12]}",
                "protocol_id": protocol.get("protocol_id"),
                "inclusion_snapshot_id": snapshot.get("snapshot_id"),
                "claim_text": text[:4000],
                "citation_ids": normalized,
                "paper_ids": paper_ids,
                "evidence_locations": evidence_locations,
                "support_strength": support_strength,
                "support_status": status,
                "claim_type": claim_type,
                "source_types": source_types,
                "evidence_level": (
                    "primary" if primary_support
                    else "secondary" if source_types
                    else "unverified"
                ),
                "allowed_support_types": (
                    sorted(SECONDARY_EVIDENCE_TYPES | PRIMARY_EVIDENCE_TYPES)
                    if claim_type in SECONDARY_ALLOWED_CLAIMS
                    else sorted(PRIMARY_EVIDENCE_TYPES)
                ),
                "evidence_fit": evidence_fit,
                "numeric_context_complete": numeric_context_complete,
                "normative_strength_ok": normative_strength_ok,
                "verified": (
                    status == "author_synthesis_marked"
                    or (
                        status == "supported"
                        and bool(evidence_locations)
                        and evidence_fit
                        and numeric_context_complete
                        and normative_strength_ok
                    )
                ),
                "created_at": _now(),
            })
        self._write(session_id, "claims.json", claims)
        internal_consistency_issues = self._audit_internal_consistency(review, source_map)
        artifact_audit = self._audit_required_artifacts(review, protocol.get("mode"))
        reference_audit = self._audit_reference_hygiene(review, papers)
        passed = not any([
            invalid_citations,
            unsupported,
            evidence_mismatches,
            quantitative_context_issues,
            normative_strength_issues,
            terminology_issues,
            internal_consistency_issues,
            not artifact_audit["passed"],
            not reference_audit["passed"],
        ])
        return {
            "total_claim_blocks": len(claims),
            "supported_claim_blocks": supported,
            "unverified_claim_blocks": unsupported,
            "invalid_citation_ids": sorted(invalid_citations),
            "evidence_mismatches": evidence_mismatches,
            "quantitative_context_issues": quantitative_context_issues,
            "normative_strength_issues": normative_strength_issues,
            "terminology_issues": terminology_issues,
            "internal_consistency_issues": internal_consistency_issues,
            "artifact_audit": artifact_audit,
            "reference_audit": reference_audit,
            "passed": passed,
        }

    def _audit_internal_consistency(self, review: str, source_map: dict[str, Any]) -> list[dict]:
        issues = []
        sentences = [
            item.strip()
            for item in re.split(r"(?<=[。！？.!?])\s*", review)
            if item.strip()
        ]
        for citation_id in source_map:
            cited = [
                sentence for sentence in sentences
                if f"[{citation_id}]" in sentence
            ]
            has_time_value = any(re.search(
                r"\b\d+(?:\.\d+)?\s*(?:ms|s)\b|(?:执行|推理|运行)时间",
                sentence,
                flags=re.I,
            ) for sentence in cited)
            denies_latency = any(re.search(
                r"(?:未提供|缺乏|没有).{0,12}(?:延迟|执行时间|推理时间)|"
                r"(?:no|without|lacks?).{0,12}(?:latency|execution time)",
                sentence,
                flags=re.I,
            ) for sentence in cited)
            if has_time_value and denies_latency:
                issues.append({
                    "citation_id": citation_id,
                    "type": "latency_reporting_conflict",
                    "sentences": cited[:6],
                })
        return issues

    def _audit_required_artifacts(self, review: str, mode: str) -> dict:
        if mode != "technical":
            return {"passed": True, "required_tables": 0, "table_count": 0, "concept_figure": False}
        table_count = len(re.findall(
            r"(?m)^\|(?:\s*:?-{3,}:?\s*\|){2,}\s*$",
            review,
        ))
        concept_figure = bool(
            re.search(r"```mermaid[\s\S]+?```", review, flags=re.I)
            or re.search(r"(?:概念图|Conceptual architecture).{0,100}(?:→|-->)", review, flags=re.I)
        )
        return {
            "passed": table_count >= 3 and concept_figure,
            "required_tables": 3,
            "table_count": table_count,
            "concept_figure": concept_figure,
        }

    def _audit_reference_hygiene(self, review: str, papers: list[dict]) -> dict:
        section = re.search(
            r"(?ms)^##\s+(?:参考来源|参考文献|References)\s*(.*)$",
            review,
        )
        body = section.group(1) if section else ""
        found = set(re.findall(r"(?m)^\s*(?:-\s*)?\[(P\d+)\]", body, flags=re.I))
        expected = {f"P{index}" for index in range(1, len(papers) + 1)}
        malformed_author_fragments = re.findall(
            r"\b[A-Z]\.\s+[A-Za-z-]+,\s+[A-Za-z]+(?:,\s+[A-Za-z]+){2,}",
            body,
        )
        return {
            "passed": bool(section) and found == expected and not malformed_author_fragments,
            "missing_reference_ids": sorted(expected - found),
            "unexpected_reference_ids": sorted(found - expected),
            "malformed_author_fragments": malformed_author_fragments[:20],
            "style": "IEEE",
        }

    def build_methodology_markdown(self, session_id: str, language: str = "zh-CN") -> str:
        report = self.methodology_report(session_id)
        protocol = report["protocol"]
        flow = report["flow"]
        is_en = str(language).lower().startswith("en")
        if is_en:
            lines = [
                "## Methods",
                "",
                (
                    f"This {protocol.get('mode')} review used protocol v{protocol.get('version')} "
                    f"({protocol.get('status')}). Sources were "
                    f"{', '.join(protocol.get('sources') or []) or 'not recorded'}; searches covered "
                    f"{', '.join(protocol.get('field_scope') or []) or 'not recorded'} fields, "
                    f"{', '.join(protocol.get('languages') or []) or 'not recorded'} languages, "
                    f"and the date range {protocol.get('date_from') or 'not restricted'} to "
                    f"{protocol.get('date_to') or 'not restricted'}."
                ),
                "",
                (
                    f"The flow contained {flow.get('discovered', 0)} discovered records, "
                    f"{flow.get('duplicates_removed', 0)} duplicates, "
                    f"{flow.get('unique_candidates', 0)} unique candidates, "
                    f"{flow.get('title_abstract_screened', 0)} title/abstract decisions, "
                    f"{flow.get('full_text_assessed', 0)} full-text decisions, and "
                    f"{flow.get('included', 0)} finally included records."
                ),
                "",
                f"Screening disclosure: {report['ai_participation_disclosure']}",
                "",
                "### Eligibility criteria",
                "",
                "**Include:** " + "; ".join(protocol.get("inclusion_criteria") or ["not recorded"]),
                "",
                "**Exclude:** " + "; ".join(protocol.get("exclusion_criteria") or ["not recorded"]),
            ]
        else:
            lines = [
                "## 方法",
                "",
                (
                    f"本综述按协议 v{protocol.get('version')}（{protocol.get('status')}）执行，"
                    f"模式为 {protocol.get('mode')}。配置数据源为"
                    f"{'、'.join(protocol.get('sources') or []) or '未记录'}；检索字段为"
                    f"{'、'.join(protocol.get('field_scope') or []) or '未记录'}；语言限制为"
                    f"{'、'.join(protocol.get('languages') or []) or '未记录'}；时间范围为"
                    f"{protocol.get('date_from') or '未限制'}至{protocol.get('date_to') or '未限制'}。"
                ),
                "",
                (
                    f"流程共发现{flow.get('discovered', 0)}条记录，移除"
                    f"{flow.get('duplicates_removed', 0)}条重复记录，得到"
                    f"{flow.get('unique_candidates', 0)}条唯一候选；完成"
                    f"{flow.get('title_abstract_screened', 0)}条标题摘要判断和"
                    f"{flow.get('full_text_assessed', 0)}条全文判断，最终纳入"
                    f"{flow.get('included', 0)}条记录。"
                ),
                "",
                (
                    "筛选披露：由一名研究者与AI独立复核，AI在判断时不可见人工决定，"
                    "分歧由研究者裁决；该流程不等同于两名人类独立筛选的Cochrane标准。"
                ),
                "",
                "### 纳入与排除标准",
                "",
                "**纳入：** " + "；".join(protocol.get("inclusion_criteria") or ["未记录"]),
                "",
                "**排除：** " + "；".join(protocol.get("exclusion_criteria") or ["未记录"]),
            ]
        lines.extend(["", "### Search strategies" if is_en else "### 完整检索式", ""])
        lines.extend([
            "| Source | Query | Fields | Filters | Executed | Hits | Status |"
            if is_en else
            "| 数据源 | 实际检索式 | 字段 | 过滤条件 | 执行时间 | 命中数 | 状态 |",
            "|---|---|---|---|---|---:|---|",
        ])
        for query in report["search_queries"]:
            filters = ", ".join(
                f"{key}={value}"
                for key, value in query.get("filters", {}).items()
                if value not in (None, "", [])
            ) or ("none" if is_en else "无")
            values = [
                query.get("source") or "",
                str(query.get("compiled_query") or "not recorded").replace("|", "\\|"),
                ", ".join(query.get("field_scope") or []) or "not recorded",
                filters.replace("|", "\\|"),
                query.get("executed_at") or "not recorded",
                query.get("hit_count") if query.get("hit_count") is not None else "not recorded",
                query.get("status") or "pending",
            ]
            lines.append("| " + " | ".join(str(item) for item in values) + " |")
        lines.extend(["", "### Flow and exclusions" if is_en else "### 流程与排除原因", ""])
        lines.append("```mermaid")
        lines.append("flowchart TD")
        lines.append(
            f"  A[\"Discovered: {flow.get('discovered', 0)}\"] --> "
            f"B[\"Duplicates removed: {flow.get('duplicates_removed', 0)}\"]"
        )
        lines.append(
            f"  B --> C[\"Unique candidates: {flow.get('unique_candidates', 0)}\"]"
        )
        lines.append(
            f"  C --> D[\"Title/abstract screened: {flow.get('title_abstract_screened', 0)}\"]"
        )
        lines.append(
            f"  D --> E[\"Full text assessed: {flow.get('full_text_assessed', 0)}\"]"
        )
        lines.append(f"  E --> F[\"Included: {flow.get('included', 0)}\"]")
        lines.append("```")
        lines.append("")
        reasons = report.get("exclusion_reason_counts") or {}
        lines.append(
            ("Exclusion reasons: " if is_en else "排除原因统计：")
            + (
                "; ".join(f"{key}={value}" for key, value in sorted(reasons.items()))
                if reasons else ("not recorded" if is_en else "未记录")
            )
        )
        return "\n".join(lines).strip()

    def build_technical_artifacts_markdown(
        self,
        session_id: str,
        papers: list[dict],
        language: str = "zh-CN",
    ) -> str:
        protocol = self.ensure_protocol(session_id)
        if protocol.get("mode") != "technical":
            return ""
        extractions = {
            str(item.get("paper_id")): item
            for item in _list(self._read(session_id, "extractions.json", []))
            if item.get("protocol_id") == protocol.get("protocol_id")
        }
        is_en = str(language).lower().startswith("en")
        lines = [
            "## Structured technical evidence" if is_en else "## 结构化技术证据",
            "",
            "### Included-study characteristics" if is_en else "### 表1：纳入研究基本信息",
            "",
            "| ID | Year | Evidence type | Task or dataset | Base model | Method family |"
            if is_en else
            "| 文献 | 年份 | 证据类型 | 任务或数据集 | 基础模型 | 方法族 |",
            "|---|---:|---|---|---|---|",
        ]
        for index, paper in enumerate(papers, start=1):
            extraction = extractions.get(str(paper.get("paper_id")), {})
            computer_ai = _dict(extraction.get("computer_ai"))
            datasets = extraction.get("population_or_dataset") or computer_ai.get("datasets") or "未报告"
            if isinstance(datasets, list):
                datasets = ", ".join(str(item) for item in datasets[:4])
            model = computer_ai.get("base_model") or computer_ai.get("models") or "未报告"
            if isinstance(model, list):
                model = ", ".join(str(item) for item in model[:4])
            mechanism = _dict(extraction.get("technical_mechanism"))
            family = mechanism.get("method_family") or extraction.get("intervention_or_method") or "未分类"
            values = [
                f"P{index}",
                paper.get("published_year") or paper.get("year") or "未记录",
                extraction.get("study_or_article_type") or "unclear",
                datasets,
                model,
                family,
            ]
            lines.append("| " + " | ".join(
                str(item).replace("|", "\\|").replace("\n", " ")[:240]
                for item in values
            ) + " |")
        lines.extend([
            "",
            "### Architecture mechanisms" if is_en else "### 表2：架构机制比较",
            "",
            "| ID | Inputs | Trigger or decision | Granularity | Actions or fusion | Failure boundary |"
            if is_en else
            "| 文献 | 输入 | 触发或决策机制 | 粒度 | 后续动作或融合 | 失效边界 |",
            "|---|---|---|---|---|---|",
        ])
        for index, paper in enumerate(papers, start=1):
            extraction = extractions.get(str(paper.get("paper_id")), {})
            mechanism = _dict(extraction.get("technical_mechanism"))
            values = [
                f"P{index}",
                ", ".join(str(item) for item in _list(mechanism.get("inputs"))) or "未报告",
                mechanism.get("decision_rule") or "未报告",
                mechanism.get("trigger_granularity") or "未报告",
                ", ".join(str(item) for item in _list(mechanism.get("actions")))
                or mechanism.get("fusion_strategy") or "未报告",
                ", ".join(str(item) for item in _list(mechanism.get("failure_propagation")))
                or "未报告",
            ]
            lines.append("| " + " | ".join(
                str(item).replace("|", "\\|").replace("\n", " ")[:260]
                for item in values
            ) + " |")
        lines.extend([
            "",
            "### Metrics and evidence boundaries" if is_en else "### 表3：评价指标、结果与证据边界",
            "",
            "| ID | Dataset/task | Model | Baseline | Metric | Result | Effect type | Context |"
            if is_en else
            "| 文献 | 数据集/任务 | 模型 | 基线 | 指标 | 结果 | 变化类型 | 语境完整性 |",
            "|---|---|---|---|---|---|---|---|",
        ])
        for index, paper in enumerate(papers, start=1):
            extraction = extractions.get(str(paper.get("paper_id")), {})
            results = _list(extraction.get("quantitative_results"))
            if not results:
                lines.append(
                    f"| P{index} | 未报告 | 未报告 | 未报告 | 未报告 | 未报告 | 未报告 | 不完整 |"
                )
                continue
            for result in results[:6]:
                validation = _dict(result.get("context_validation"))
                display_result = (
                    f"{result.get('baseline_value', '未报告')} → {result.get('method_value', result.get('value', '未报告'))}"
                )
                values = [
                    f"P{index}",
                    result.get("dataset_or_task") or result.get("dataset") or "未报告",
                    result.get("base_model") or result.get("model") or "未报告",
                    result.get("baseline") or "未报告",
                    result.get("metric") or "未报告",
                    display_result,
                    result.get("effect_type") or "未报告",
                    "完整" if validation.get("complete") else (
                        "缺少：" + ", ".join(validation.get("missing_fields") or [])
                    ),
                ]
                lines.append("| " + " | ".join(
                    str(item).replace("|", "\\|").replace("\n", " ")[:240]
                    for item in values
                ) + " |")
        question = str(protocol.get("research_question") or "").lower()
        lines.extend(["", "### Conceptual architecture" if is_en else "### 概念图：技术控制闭环", "", "```mermaid", "flowchart LR"])
        if "rag" in question or "retrieval" in question or "检索增强" in question:
            lines.extend([
                '  A["Static retrieval"] --> B["Iterative retrieval"]',
                '  B --> C["On-demand retrieval"]',
                '  C --> D["Retrieval evaluation"]',
                '  D --> E["Correction and feedback"]',
                '  E -. evidence feedback .-> C',
            ])
        else:
            families = []
            for extraction in extractions.values():
                family = _dict(extraction.get("technical_mechanism")).get("method_family")
                if family and family not in families:
                    families.append(str(family))
            families = families[:5] or ["Problem", "Method", "Evaluation", "Feedback"]
            for index, family in enumerate(families):
                lines.append(f'  N{index}["{family.replace(chr(34), chr(39))[:80]}"]')
                if index:
                    lines.append(f"  N{index - 1} --> N{index}")
        lines.append("```")
        lines.append("")
        lines.append(
            "The diagram is generated from the structured taxonomy and denotes control flow, not a universal performance ranking."
            if is_en else
            "该图由结构化分类确定性生成，表示控制流程，不表示普遍性能排序。"
        )
        return "\n".join(lines).strip()

    def format_ieee_references(self, papers: list[dict], language: str = "zh-CN") -> str:
        is_en = str(language).lower().startswith("en")
        lines = ["## References" if is_en else "## 参考文献", ""]
        for index, paper in enumerate(papers, start=1):
            authors = self._normalize_author_names(paper.get("authors"))
            author_text = ", ".join(authors) if authors else ("Unknown author" if is_en else "作者未记录")
            title = str(paper.get("title") or "Untitled").strip()
            venue = str(paper.get("venue") or paper.get("journal") or "").strip()
            year = paper.get("published_year") or paper.get("year") or "n.d."
            identifier = (
                paper.get("doi")
                or paper.get("source_url")
                or paper.get("url")
                or paper.get("pdf_url")
                or ""
            )
            suffix = f", {venue}" if venue else ""
            if identifier:
                suffix += f", {identifier}"
            lines.append(f"- [P{index}] {author_text}, “{title}”{suffix}, {year}.")
        return "\n".join(lines).strip()

    def _normalize_author_names(self, authors: Any) -> list[str]:
        if isinstance(authors, list):
            values = []
            for author in authors:
                if isinstance(author, dict):
                    name = author.get("display_name") or author.get("name")
                else:
                    name = author
                if str(name or "").strip():
                    values.append(str(name).strip())
        else:
            values = [
                item.strip()
                for item in re.split(r"\s*;\s*|\s*,\s*", str(authors or ""))
                if item.strip()
            ]
        repaired = []
        index = 0
        while index < len(values):
            current = values[index]
            if (
                len(current.split()) == 1
                and index + 1 < len(values)
                and len(values[index + 1].split()) == 1
            ):
                repaired.append(f"{values[index + 1]} {current}")
                index += 2
            else:
                repaired.append(current)
                index += 1
        normalized = []
        for name in repaired:
            parts = [item for item in re.split(r"\s+", name.strip()) if item]
            if len(parts) <= 1:
                normalized.append(name)
            else:
                initials = " ".join(f"{part[0].upper()}." for part in parts[:-1] if part)
                normalized.append(f"{initials} {parts[-1]}")
        return normalized

    def inject_deterministic_review_sections(
        self,
        session_id: str,
        review: str,
        papers: list[dict],
        language: str = "zh-CN",
    ) -> str:
        """Replace mutable methods/references and insert schema-derived artifacts."""
        method = self.build_methodology_markdown(session_id, language)
        review = re.sub(
            r"(?ms)^##\s+(?:方法|Methods)\s*.*?(?=^##\s+|\Z)",
            method + "\n\n",
            review,
            count=1,
        )
        if not re.search(r"(?m)^##\s+(?:方法|Methods)\s*$", review):
            heading = re.search(r"(?m)^##\s+(?:结果|Results|主题|Evidence)", review)
            if heading:
                review = review[:heading.start()] + method + "\n\n" + review[heading.start():]
            else:
                review = review.rstrip() + "\n\n" + method
        artifacts = self.build_technical_artifacts_markdown(session_id, papers, language)
        review = re.sub(
            r"(?ms)^##\s+(?:结构化技术证据|Structured technical evidence)\s*.*?(?=^##\s+|\Z)",
            "",
            review,
        )
        review = re.sub(
            r"(?ms)^##\s+(?:参考来源|参考文献|References)\s*.*$",
            "",
            review,
        ).rstrip()
        if artifacts:
            review += "\n\n" + artifacts
        review += "\n\n" + self.format_ieee_references(papers, language) + "\n"
        return review

    def enforce_review_label(self, session_id: str, review: str, gate: dict, language: str) -> str:
        """Prevent an incomplete or rapid draft from presenting itself as systematic."""
        protocol = self.ensure_protocol(session_id)
        lines = review.splitlines()
        if not gate.get("can_claim_systematic"):
            for index, line in enumerate(lines[:12]):
                if line.lstrip().startswith("#"):
                    if str(language).lower().startswith("en"):
                        lines[index] = re.sub(
                            r"\bsystematic review\b",
                            "rapid evidence review" if protocol.get("mode") == "rapid" else "evidence review",
                            line,
                            flags=re.I,
                        )
                    else:
                        lines[index] = line.replace(
                            "系统综述",
                            "快速证据综述" if protocol.get("mode") == "rapid" else "证据综述",
                        )
                    break
            if protocol.get("mode") == "technical" and gate.get("ok"):
                notice = (
                    "> **Document status:** Computer science and AI technical evidence review draft; it is not a systematic review."
                    if str(language).lower().startswith("en")
                    else "> **文档状态：** 计算机与AI技术证据综述研究草稿；不属于严格系统综述。"
                )
            else:
                notice = (
                    "> **Document status:** Pre-submission research draft. The methodology gate does not permit a systematic-review claim."
                    if str(language).lower().startswith("en")
                    else "> **文档状态：** 投稿前研究底稿；当前方法学门禁不允许将其声明为严格系统综述。"
                )
            if notice not in lines[:8]:
                insert_at = 1 if lines and lines[0].lstrip().startswith("#") else 0
                lines[insert_at:insert_at] = ["", notice, ""]
        else:
            notice = (
                "> **Screening disclosure:** AI-assisted systematic-review research draft. One human reviewer and an independent AI screened records; disagreements were adjudicated by the human. This is not dual-human Cochrane-compliant screening."
                if str(language).lower().startswith("en")
                else "> **筛选披露：** AI辅助系统综述研究草稿；一名研究者与AI独立筛选，分歧由研究者裁决，不等同于两名人类独立筛选的Cochrane标准。"
            )
            if notice not in lines[:10]:
                insert_at = 1 if lines and lines[0].lstrip().startswith("#") else 0
                lines[insert_at:insert_at] = ["", notice, ""]
        return "\n".join(lines)


def deterministic_evidence_seed(paper: dict) -> dict:
    """Create a conservative extraction draft without inventing paper facts."""
    notes = str(paper.get("notes") or "")
    abstract = str(paper.get("abstract") or "")
    basis = paper.get("evidence_basis") or ("full_text" if paper.get("pdf_status") == "available" else "abstract")
    limitations = []
    for line in notes.splitlines():
        if re.search(r"limit|局限|偏倚|threat", line, re.I):
            cleaned = re.sub(r"^[#*\-\s]+", "", line).strip()
            if cleaned:
                limitations.append(cleaned[:1000])
    result_lines = []
    for line in notes.splitlines():
        if re.search(r"result|finding|结果|发现|结论", line, re.I):
            cleaned = re.sub(r"^[#*\-\s]+", "", line).strip()
            if cleaned:
                result_lines.append({"statement": cleaned[:1600], "location": None})
    return {
        "study_design": None,
        "study_or_article_type": normalize_study_or_article_type(
            paper.get("study_or_article_type") or paper.get("document_type"),
            str(paper.get("title") or ""),
        ),
        "population_or_dataset": None,
        "intervention_or_method": None,
        "comparator_or_baseline": None,
        "sample_size": None,
        "outcomes_and_metrics": [],
        "main_results": result_lines[:8],
        "quantitative_results": [],
        "technical_mechanism": {
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
        "limitations": limitations[:8],
        "funding_and_conflicts": None,
        "evidence_locations": [],
        "computer_ai": {},
        "evidence_basis": basis,
        "confidence": 0.35 if basis == "abstract" else 0.55,
        "review_status": "ai_draft",
        "source_excerpt": abstract[:2000] if not notes else notes[:4000],
    }
