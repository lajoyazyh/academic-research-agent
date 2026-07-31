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


SCIENTIFIC_SKILL_MANIFESTS = [
    {
        "id": "protocol",
        "version": "1.0.0",
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
        "version": "1.0.0",
        "stage": "search",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "LockedReviewProtocol",
        "output_schema": "SearchQueryPlan",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["english_database_queries", "source_specific_queries"],
        "immutable_constraints": ["query_and_source_ledger_required"],
    },
    {
        "id": "title_abstract_screen",
        "version": "1.0.0",
        "stage": "screen",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "CandidateAndProtocol",
        "output_schema": "ScreeningDecision",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["criterion_level_judgements", "uncertainty_allowed"],
        "immutable_constraints": ["no_direct_final_inclusion"],
    },
    {
        "id": "fulltext_screen",
        "version": "1.0.0",
        "stage": "screen",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "FullTextCandidateAndProtocol",
        "output_schema": "ScreeningDecision",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["exclusion_reason_required", "evidence_location_required"],
        "immutable_constraints": ["human_inclusion_snapshot_required"],
    },
    {
        "id": "evidence_extract",
        "version": "1.0.0",
        "stage": "read",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "IncludedStudyFullText",
        "output_schema": "ExtractionRecord",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["source_location", "basis_label", "required_fields"],
        "immutable_constraints": ["missing_information_must_not_be_inferred"],
    },
    {
        "id": "study_appraise",
        "version": "1.0.0",
        "stage": "analysis",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "ExtractionRecord",
        "output_schema": "StudyAppraisal",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["domain_level_reasons", "tool_matches_design"],
        "immutable_constraints": ["no_unexplained_single_quality_score"],
    },
    {
        "id": "evidence_synthesize",
        "version": "1.0.0",
        "stage": "analysis",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "EvidenceMatrix",
        "output_schema": "SynthesisGroups",
        "model_requirements": ["chat", "structured_output"],
        "validators": ["comparability_assessed", "conflicts_preserved"],
        "immutable_constraints": ["no_meta_analysis_without_compatible_effects"],
    },
    {
        "id": "review_outline",
        "version": "1.0.0",
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
        "version": "1.0.0",
        "stage": "write",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "VerifiedSynthesisPackage",
        "output_schema": "ReviewDraft",
        "model_requirements": ["chat"],
        "validators": ["citation_ids", "methods_from_ledger"],
        "immutable_constraints": ["no_posthoc_citation_invention"],
    },
    {
        "id": "citation_audit",
        "version": "1.0.0",
        "stage": "audit",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "ReviewDraftAndEvidence",
        "output_schema": "ClaimAudit",
        "model_requirements": [],
        "validators": ["reference_exists", "source_in_snapshot", "claim_basis"],
        "immutable_constraints": ["zero_phantom_references"],
    },
    {
        "id": "methodology_audit",
        "version": "1.0.0",
        "stage": "audit",
        "review_modes": list(REVIEW_MODES),
        "locales": ["zh-CN", "en"],
        "input_schema": "CompleteResearchLedger",
        "output_schema": "MethodologyAudit",
        "model_requirements": [],
        "validators": ["flow_counts_reconcile", "protocol_version_matches"],
        "immutable_constraints": ["incomplete_work_cannot_claim_systematic"],
    },
]

_SKILL_PROMPTS = {
    "protocol": {
        "zh-CN": "把研究问题转换为可确认的综述协议；缺失信息标记为待确认，禁止自行扩大研究范围。",
        "en": "Convert the question into a confirmable review protocol; mark missing information as unresolved and never broaden scope silently.",
    },
    "query_design": {
        "zh-CN": "按已锁定协议为每个数据源生成英文检索式、同义词、分页及引用追踪计划。",
        "en": "Create source-specific English queries, synonyms, pagination and citation-chasing tasks from the locked protocol.",
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
        "zh-CN": "从全文提取结构化研究证据，每个事实附页码、章节和原文片段；未报告字段保持空值。",
        "en": "Extract structured study evidence from full text with page, section and source excerpts; leave unreported fields null.",
    },
    "study_appraise": {
        "zh-CN": "选择匹配研究设计的评价规则，逐域给出判断与依据，禁止用无解释的总分替代质量评价。",
        "en": "Apply an appraisal rule matched to study design with domain-level judgements and reasons; never substitute an unexplained score.",
    },
    "evidence_synthesize": {
        "zh-CN": "先评价研究可比性，再分组综合一致结果、冲突、解释、证据缺口与适用边界。",
        "en": "Assess comparability before grouping evidence into agreements, conflicts, explanations, gaps and applicability boundaries.",
    },
    "review_outline": {
        "zh-CN": "依据协议和综合单元建立综述大纲，按研究问题与主题组织，不按论文逐篇罗列。",
        "en": "Build a mode-specific outline from the protocol and synthesis groups, organized by questions and themes rather than papers.",
    },
    "review_write": {
        "zh-CN": "仅依据经验证综合单元写投稿前研究底稿；方法来自检索账本，每个实质论断绑定有效来源。",
        "en": "Write a pre-submission research draft only from verified synthesis units; derive methods from the ledger and bind each substantive claim to a valid source.",
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
            return next((item for item in protocols if item.get("protocol_id") == current_id), protocols[-1])
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
            "mode": mode,
            "language": "en" if is_en else "zh-CN",
            "research_question": topic.strip(),
            "framework": "PICOC" if mode == "technical" else ("PCC" if mode == "scoping" else "general"),
            "candidate_cap": cap,
            "sources": list(PROTOCOL_DEFAULTS["sources"]),
            "languages": list(PROTOCOL_DEFAULTS["languages"]),
            "document_types": list(PROTOCOL_DEFAULTS["document_types"]),
            "date_from": None,
            "date_to": None,
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
            "inclusion_criteria": protocol.get("inclusion_criteria"),
            "exclusion_criteria": protocol.get("exclusion_criteria"),
            "extraction_fields": protocol.get("extraction_fields"),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(f"Protocol is incomplete: {', '.join(missing)}")
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
                    "query_syntax": "bibliographic_terms" if tool_source in {"crossref", "dblp"} else "boolean_or",
                    "pagination_parameter": pagination_parameter,
                    "required_pages": required_pages,
                    "status": "pending",
                    "pages": [],
                    "hit_count": None,
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
                    "stage": "citation_chasing",
                    "direction": direction,
                    "required_pages": 1,
                    "status": "pending",
                    "pages": [],
                    "hit_count": None,
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
    ) -> dict:
        if stage not in SCREENING_STAGES:
            raise ValueError(f"Unsupported screening stage: {stage}")
        if decision not in SCREENING_DECISIONS:
            raise ValueError(f"Unsupported screening decision: {decision}")
        if decision == "exclude" and reason_code not in EXCLUSION_CODES:
            raise ValueError("A standard exclusion reason is required")
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
            "created_at": _now(),
        }
        decisions = _list(self._read(session_id, "screening_decisions.json", []))
        decisions.append(record)
        self._write(session_id, "screening_decisions.json", decisions)
        for item in candidates:
            if item.get("candidate_id") == candidate.get("candidate_id"):
                item["screening_stage"] = stage
                item["screening_decision"] = decision
                item["status"] = (
                    "accepted" if stage == "full_text" and decision == "include"
                    else "rejected" if decision == "exclude"
                    else "pending"
                )
                item["updated_at"] = _now()
        self._write(session_id, "candidates.json", candidates)
        return record

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
        record = {
            "extraction_id": f"extract_{uuid.uuid4().hex[:12]}",
            "paper_id": paper_id,
            "protocol_id": protocol.get("protocol_id"),
            "protocol_version": protocol.get("version"),
            "study_design": fields.get("study_design"),
            "population_or_dataset": fields.get("population_or_dataset"),
            "intervention_or_method": fields.get("intervention_or_method"),
            "comparator_or_baseline": fields.get("comparator_or_baseline"),
            "sample_size": fields.get("sample_size"),
            "outcomes_and_metrics": _list(fields.get("outcomes_and_metrics")),
            "main_results": _list(fields.get("main_results")),
            "uncertainty": fields.get("uncertainty"),
            "limitations": _list(fields.get("limitations")),
            "funding_and_conflicts": fields.get("funding_and_conflicts"),
            "evidence_locations": _list(fields.get("evidence_locations")),
            "computer_ai": _dict(fields.get("computer_ai")),
            "evidence_basis": basis,
            "confidence": fields.get("confidence"),
            "review_status": fields.get("review_status", "ai_draft"),
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
        record = {
            "appraisal_id": f"appraisal_{uuid.uuid4().hex[:12]}",
            "paper_id": paper_id,
            "protocol_id": protocol.get("protocol_id"),
            "protocol_version": protocol.get("version"),
            "profile": appraisal.get("profile") or protocol.get("appraisal_profile"),
            "study_design": appraisal.get("study_design"),
            "domains": _list(appraisal.get("domains")),
            "overall_judgement": appraisal.get("overall_judgement", "unclear"),
            "rationale": appraisal.get("rationale", ""),
            "review_status": appraisal.get("review_status", "ai_draft"),
            "created_at": _now(),
        }
        records = _list(self._read(session_id, "appraisals.json", []))
        records = [item for item in records if not (
            item.get("paper_id") == paper_id and item.get("protocol_id") == protocol.get("protocol_id")
        )]
        records.append(record)
        self._write(session_id, "appraisals.json", records)
        return record

    def flow_counts(self, session_id: str) -> dict:
        candidates = _list(self._read(session_id, "candidates.json", []))
        decisions = _list(self._read(session_id, "screening_decisions.json", []))
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
        }

    def build_methodology_context(self, session_id: str, language: str = "zh-CN") -> str:
        protocol = self.ensure_protocol(session_id)
        flow = self.flow_counts(session_id)
        search_runs = _list((self.session_manager.load_session(session_id) or {}).get("search_runs"))
        latest_snapshot = self.latest_inclusion_snapshot(session_id)
        completed_sources = sorted({
            str(query.get("source") or query.get("tool") or "")
            for run in search_runs
            for query in _list(_dict(run.get("retrieval_ledger")).get("queries"))
            if query.get("source") or query.get("tool")
        })
        is_en = str(language).lower().startswith("en")
        if is_en:
            return (
                "## Verified methodology ledger (deterministic; do not alter)\n"
                f"- Review mode: {protocol.get('mode')}\n"
                f"- Protocol version: {protocol.get('version')} ({protocol.get('status')})\n"
                f"- Research question: {protocol.get('research_question')}\n"
                f"- Configured sources: {', '.join(protocol.get('sources') or [])}\n"
                f"- Sources recorded in executed queries: {', '.join(completed_sources) or 'not recorded'}\n"
                f"- Candidate cap: {protocol.get('candidate_cap')}\n"
                f"- Flow counts: {json.dumps(flow, ensure_ascii=False)}\n"
                f"- Final inclusion snapshot: {(latest_snapshot or {}).get('snapshot_id') or 'not confirmed'}\n"
                "- Only these values may be reported as methods or flow counts. Missing values must be labelled not recorded.\n"
            )
        return (
            "## 已核验的方法学账本（确定性生成，不得改写数字）\n"
            f"- 综述模式：{protocol.get('mode')}\n"
            f"- 协议版本：{protocol.get('version')}（{protocol.get('status')}）\n"
            f"- 研究问题：{protocol.get('research_question')}\n"
            f"- 配置的数据源：{', '.join(protocol.get('sources') or [])}\n"
            f"- 执行轨迹中记录的数据源：{', '.join(completed_sources) or '未记录'}\n"
            f"- 候选文献上限：{protocol.get('candidate_cap')}\n"
            f"- 流程计数：{json.dumps(flow, ensure_ascii=False)}\n"
            f"- 最终纳入快照：{(latest_snapshot or {}).get('snapshot_id') or '尚未确认'}\n"
            "- 方法和流程数字只能引用以上账本；缺失值必须写“未记录”。\n"
        )

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
                "comparability": "potentially_comparable" if compatible else "narrative_only",
                "synthesis_method": (
                    "SWiM_or_thematic" if not compatible
                    else protocol.get("synthesis_method", "SWiM_or_thematic")
                ),
                "meta_analysis_allowed": False,
                "agreements": [],
                "conflicts": [],
                "possible_explanations": [],
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
        if protocol.get("status") != "confirmed":
            blockers.append("protocol_not_confirmed")
        if not search_runs:
            warnings.append("search_ledger_empty")
        flow = self.flow_counts(session_id)
        if (
            protocol.get("mode") == "systematic"
            and flow.get("queries_completed", 0) < flow.get("queries_planned", 0)
        ):
            blockers.append("configured_search_queries_incomplete")
        if not snapshot:
            blockers.append("inclusion_snapshot_not_confirmed")
        elif selected and sorted(selected) != sorted(snapshot_ids):
            blockers.append("selection_differs_from_inclusion_snapshot")
        missing_extractions = [paper_id for paper_id in snapshot_ids if paper_id not in current_extractions]
        if missing_extractions:
            blockers.append("evidence_extraction_incomplete")
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
            if protocol.get("mode") == "systematic":
                blockers.append("study_appraisal_incomplete")
            else:
                warnings.append("study_appraisal_incomplete")
        if flow.get("unresolved", 0):
            if protocol.get("mode") == "systematic":
                blockers.append("screening_decisions_unresolved")
            else:
                warnings.append("screening_decisions_unresolved")
        can_claim_systematic = bool(
            REVIEW_MODES.get(protocol.get("mode"), {}).get("can_claim_systematic")
            and not blockers
            and search_runs
        )
        return {
            "ok": not blockers,
            "output_label": "systematic_review_draft" if can_claim_systematic else "incomplete_research_draft",
            "can_claim_systematic": can_claim_systematic,
            "blockers": blockers,
            "warnings": warnings,
            "missing_extraction_paper_ids": missing_extractions,
            "abstract_only_paper_ids": abstract_only,
            "missing_appraisal_paper_ids": missing_appraisals,
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
                "verified": (
                    status == "author_synthesis_marked"
                    or (status == "supported" and bool(evidence_locations))
                ),
                "created_at": _now(),
            })
        self._write(session_id, "claims.json", claims)
        return {
            "total_claim_blocks": len(claims),
            "supported_claim_blocks": supported,
            "unverified_claim_blocks": unsupported,
            "invalid_citation_ids": sorted(invalid_citations),
            "passed": not invalid_citations and unsupported == 0,
        }

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
            notice = (
                "> **Document status:** Pre-submission research draft. The methodology gate does not permit a systematic-review claim."
                if str(language).lower().startswith("en")
                else "> **文档状态：** 投稿前研究底稿；当前方法学门禁不允许将其声明为严格系统综述。"
            )
            if notice not in lines[:8]:
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
        "population_or_dataset": None,
        "intervention_or_method": None,
        "comparator_or_baseline": None,
        "sample_size": None,
        "outcomes_and_metrics": [],
        "main_results": result_lines[:8],
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
