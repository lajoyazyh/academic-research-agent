import pytest
import shutil
from fastapi import HTTPException

from backend.scientific_review import (
    REVIEW_MODES,
    SCIENTIFIC_SKILL_MANIFESTS,
    ScientificReviewService,
    deterministic_evidence_seed,
)
from backend.session_manager import SessionManager
from backend.routes.models import RunPhaseRequest
from backend.routes import agent as agent_routes


def _service(tmp_path, topic="Graph neural network reproducibility"):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session(topic)
    return manager, session, ScientificReviewService(manager)


def test_new_project_starts_with_unconfirmed_rapid_protocol(tmp_path):
    manager, session, _service_obj = _service(tmp_path)
    loaded = manager.load_session(session["session_id"])

    assert loaded["workflow_version"] == 2
    assert loaded["review_protocol"]["mode"] == "rapid"
    assert loaded["review_protocol"]["candidate_cap"] == 100
    assert loaded["review_protocol"]["status"] == "draft"


def test_legacy_accepted_papers_require_reconfirmation(tmp_path):
    manager, session, _service_obj = _service(tmp_path)
    session_id = session["session_id"]
    manager.add_paper(
        session_id,
        {"paper_id": "legacy-1", "title": "Legacy paper", "status": "accepted"},
    )
    shutil.rmtree(manager.root / session_id / "methodology")

    service = ScientificReviewService(manager)
    service.ensure_protocol(session_id, topic=session["topic"])

    paper = manager.get_papers(session_id)[0]
    assert paper["legacy_status"] == "accepted"
    assert paper["status"] == "pending"
    assert paper["screening_decision"] == "uncertain"
    assert service.flow_counts(session_id)["unresolved"] == 1


def test_review_mode_caps_are_validated_and_mode_switch_versions_protocol(tmp_path):
    _manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    first = service.confirm_protocol(session_id)

    switched = service.version_for_mode(
        session_id,
        mode="systematic",
        candidate_cap=500,
    )

    assert switched["version"] == first["version"] + 1
    assert switched["base_protocol_id"] == first["protocol_id"]
    assert switched["status"] == "draft"
    with pytest.raises(ValueError):
        service.update_protocol(session_id, {"candidate_cap": 50})


def test_candidate_deduplication_keeps_source_provenance(tmp_path):
    _manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    first = service.register_candidate(session_id, {
        "paper_id": "2401.12345",
        "title": "A reproducibility study",
        "source": "agent_search",
        "source_type": "arxiv",
    })
    second = service.register_candidate(session_id, {
        "paper_id": "10.1000/example",
        "doi": "10.1000/example",
        "title": "A reproducibility study",
        "source": "agent_search",
        "source_type": "doi",
    })

    assert second["candidate_id"] == first["candidate_id"]
    assert second["duplicate_count"] == 1
    assert service.flow_counts(session_id)["unique_candidates"] == 1
    assert service.flow_counts(session_id)["duplicates_removed"] == 1


def test_screening_requires_reason_for_exclusion(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    manager.add_paper(session_id, {"paper_id": "p1", "title": "Paper", "status": "pending"})
    service.register_candidate(session_id, manager.get_papers(session_id)[0])

    with pytest.raises(ValueError):
        service.record_screening(
            session_id,
            paper_id="p1",
            stage="full_text",
            decision="exclude",
        )

    decision = service.record_screening(
        session_id,
        paper_id="p1",
        stage="full_text",
        decision="exclude",
        reason_code="wrong_outcome",
        reason="The paper does not report the protocol outcome.",
    )
    assert decision["reason_code"] == "wrong_outcome"


def test_final_inclusion_checkpoint_resolves_unselected_screened_candidates(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    for paper_id in ("p1", "p2"):
        paper = {"paper_id": paper_id, "title": paper_id, "status": "pending"}
        manager.add_paper(session_id, paper)
        service.register_candidate(session_id, paper)
        service.record_screening(
            session_id,
            paper_id=paper_id,
            stage="title_abstract",
            decision="include",
            reason="Relevant at title/abstract stage.",
            reviewer="human",
        )

    service.confirm_inclusion_snapshot(session_id, ["p1"])
    decisions = service._read(session_id, "screening_decisions.json", [])
    p2_fulltext = [
        item for item in decisions
        if item["paper_id"] == "p2" and item["stage"] == "full_text"
    ][-1]

    assert p2_fulltext["decision"] == "exclude"
    assert p2_fulltext["reason_code"] == "other"
    assert service.flow_counts(session_id)["unresolved"] == 0


def test_systematic_gate_requires_completed_configured_queries(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.update_protocol(session_id, {"mode": "systematic", "candidate_cap": 500})
    service.confirm_protocol(session_id)
    manager.add_paper(session_id, {
        "paper_id": "p1",
        "title": "Paper",
        "status": "accepted",
        "notes": "Results: a reproducible benchmark result.",
    })
    service.register_candidate(session_id, manager.get_papers(session_id)[0])
    service.confirm_inclusion_snapshot(session_id, ["p1"])
    service.save_extraction(
        session_id,
        "p1",
        deterministic_evidence_seed(manager.get_papers(session_id)[0]),
    )

    gate = service.quality_gate(session_id, requested_paper_ids=["p1"])

    assert gate["ok"] is False
    assert "configured_search_queries_incomplete" in gate["blockers"]
    assert gate["can_claim_systematic"] is False


def test_systematic_protocol_plans_pagination_and_citation_chasing(tmp_path):
    _manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.update_protocol(
        session_id,
        {
            "mode": "systematic",
            "candidate_cap": 500,
            "sources": ["arXiv", "OpenAlex"],
        },
    )
    service.confirm_protocol(session_id)

    plans = service.audit_summary(session_id)["search_queries"]
    source_plans = {plan["source"]: plan for plan in plans}
    citation_plans = [plan for plan in plans if plan["source"] == "openalex_citations"]

    assert source_plans["arxiv"]["required_pages"] == 3
    assert source_plans["openalex"]["required_pages"] == 3
    assert all(plan["stage"] == "citation_chasing" for plan in citation_plans)
    assert {plan["direction"] for plan in citation_plans} == {"cited_by", "references"}


def test_query_design_keeps_confirmed_concepts_as_separate_source_queries(tmp_path):
    manager = SessionManager(str(tmp_path))
    session = manager.create_session(
        "Review reporting frameworks",
        keywords=[
            {"english": "PRISMA 2020", "synonyms": "systematic review reporting"},
            {"english": "SWiM", "synonyms": "synthesis without meta-analysis"},
        ],
    )
    service = ScientificReviewService(manager)
    service.update_protocol(session["session_id"], {"sources": ["Europe PMC"]})
    service.confirm_protocol(session["session_id"])

    plans = service.audit_summary(session["session_id"])["search_queries"]

    assert len(plans) == 2
    assert {plan["concept"] for plan in plans} == {"PRISMA 2020", "SWiM"}
    assert any('"PRISMA 2020" OR "systematic review reporting"' == plan["query"] for plan in plans)
    assert any('SWiM OR "synthesis without meta-analysis"' == plan["query"] for plan in plans)


def test_search_ledger_requires_distinct_pages_before_completion(tmp_path):
    _manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.update_protocol(
        session_id,
        {
            "mode": "systematic",
            "candidate_cap": 500,
            "sources": ["OpenAlex"],
        },
    )
    service.confirm_protocol(session_id)
    plan = next(
        item
        for item in service.audit_summary(session_id)["search_queries"]
        if item["source"] == "openalex"
    )

    first_pass = service.reconcile_search_ledger(
        session_id,
        {
            "queries": [
                {
                    "source": "openalex",
                    "query": plan["query"],
                    "page": 1,
                    "success": True,
                }
            ]
        },
    )
    assert next(item for item in first_pass if item["source"] == "openalex")["status"] == "partial"

    duplicate_first_page = service.reconcile_search_ledger(
        session_id,
        {
            "queries": [
                {
                    "source": "openalex",
                    "query": plan["query"] + " benchmark",
                    "page": 1,
                    "success": True,
                }
            ]
        },
    )
    assert next(
        item for item in duplicate_first_page if item["source"] == "openalex"
    )["status"] == "partial"

    completed = service.reconcile_search_ledger(
        session_id,
        {
            "queries": [
                {
                    "source": "openalex",
                    "query": plan["query"],
                    "page": 2,
                    "success": True,
                },
                {
                    "source": "openalex",
                    "query": plan["query"],
                    "page": 3,
                    "success": True,
                },
            ]
        },
    )
    assert next(item for item in completed if item["source"] == "openalex")["status"] == "completed"


def test_failed_search_attempt_is_not_marked_completed(tmp_path):
    _manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.update_protocol(session_id, {"sources": ["arXiv"]})
    service.confirm_protocol(session_id)
    plan = service.audit_summary(session_id)["search_queries"][0]

    plans = service.reconcile_search_ledger(
        session_id,
        {
            "queries": [
                {
                    "source": "arxiv",
                    "query": plan["query"],
                    "page": 0,
                    "success": False,
                    "error": "HTTP 429",
                }
            ]
        },
    )

    assert plans[0]["status"] == "failed"
    assert plans[0]["last_error"] == "HTTP 429"


def test_rapid_review_is_never_labelled_systematic(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    manager.add_paper(session_id, {
        "paper_id": "p1",
        "title": "Paper",
        "status": "accepted",
        "notes": "Result: supported evidence.",
    })
    service.register_candidate(session_id, manager.get_papers(session_id)[0])
    service.confirm_inclusion_snapshot(session_id, ["p1"])
    service.save_extraction(
        session_id,
        "p1",
        deterministic_evidence_seed(manager.get_papers(session_id)[0]),
    )

    gate = service.quality_gate(session_id, requested_paper_ids=["p1"])

    assert gate["ok"] is True
    assert gate["can_claim_systematic"] is False
    assert gate["output_label"] == "rapid_evidence_review_draft"


def test_claim_audit_rejects_phantom_source_ids(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    manager.add_paper(session_id, {"paper_id": "p1", "title": "Paper", "status": "accepted"})
    service.register_candidate(session_id, manager.get_papers(session_id)[0])
    service.confirm_inclusion_snapshot(session_id, ["p1"])

    audit = service.audit_review_claims(
        session_id,
        "## Results\n\nThe method improved performance on the benchmark [P9].",
        [{"paper_id": "p1", "title": "Paper"}],
    )

    assert audit["passed"] is False
    assert audit["invalid_citation_ids"] == ["P9"]


def test_write_endpoint_stops_before_human_inclusion_checkpoint(tmp_path, monkeypatch):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    manager.add_paper(session_id, {
        "paper_id": "p1",
        "title": "Paper",
        "status": "accepted",
        "notes": "Evidence",
    })
    monkeypatch.setattr(agent_routes, "session_mgr", manager)
    monkeypatch.setattr(agent_routes, "ensure_provider_available", lambda _provider: {})

    with pytest.raises(HTTPException) as exc:
        agent_routes.run_write_phase(
            session_id,
            RunPhaseRequest(topic=session["topic"], paper_ids=["p1"]),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "inclusion_confirmation_required"


def test_scientific_skill_pipeline_is_typed_versioned_and_bilingual():
    ids = [item["id"] for item in SCIENTIFIC_SKILL_MANIFESTS]
    assert ids == [
        "protocol",
        "query_design",
        "title_abstract_screen",
        "fulltext_screen",
        "evidence_extract",
        "study_appraise",
        "evidence_synthesize",
        "review_outline",
        "review_write",
        "citation_audit",
        "methodology_audit",
    ]
    assert all(item["version"] and item["input_schema"] and item["output_schema"] for item in SCIENTIFIC_SKILL_MANIFESTS)
    assert all(set(item["locales"]) == {"zh-CN", "en"} for item in SCIENTIFIC_SKILL_MANIFESTS)
    assert all(item["input_json_schema"]["type"] == "object" for item in SCIENTIFIC_SKILL_MANIFESTS)
    assert all(item["output_json_schema"]["required"] for item in SCIENTIFIC_SKILL_MANIFESTS)
    assert all(set(item["prompt_templates"]) == {"zh-CN", "en"} for item in SCIENTIFIC_SKILL_MANIFESTS)
    assert all(item["failure_states"] and item["uncertainty_states"] for item in SCIENTIFIC_SKILL_MANIFESTS)
    assert REVIEW_MODES["systematic"]["default_candidate_cap"] == 500


def test_scientific_migration_declares_workflow_tables():
    migration = (
        __import__("pathlib").Path(__file__).parents[1]
        / "supabase"
        / "migrations"
        / "003_scientific_review_workflow.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "review_protocols",
        "review_search_queries",
        "research_candidates",
        "screening_decisions",
        "evidence_extractions",
        "study_appraisals",
        "inclusion_snapshots",
        "synthesis_groups",
        "review_claims",
        "review_versions",
    ):
        assert f"public.{table}" in migration


def test_protocol_v2_records_search_scope_filters_and_screening_policy(tmp_path):
    _manager, session, service = _service(tmp_path)
    protocol = service.update_protocol(
        session["session_id"],
        {
            "sources": ["OpenAlex"],
            "search_field_scope": ["title", "abstract"],
            "languages": ["en"],
            "document_types": ["conference_paper"],
            "date_from": "2020-01-01",
            "date_to": "2025-12-31",
        },
    )
    service.confirm_protocol(session["session_id"])
    query = service.audit_summary(session["session_id"])["search_queries"][0]

    assert protocol["methodology_schema_version"] == 2
    assert protocol["screening_policy"]["strategy"] == "single_human_plus_independent_ai"
    assert query["field_scope"] == ["title", "abstract"]
    assert query["filters"]["languages"] == ["en"]
    assert query["filters"]["date_from"] == "2020-01-01"


def test_search_execution_metadata_is_preserved_for_reproducibility(tmp_path):
    _manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.update_protocol(session_id, {"sources": ["OpenAlex"]})
    service.confirm_protocol(session_id)
    plan = service.audit_summary(session_id)["search_queries"][0]
    result = service.reconcile_search_ledger(
        session_id,
        {
            "queries": [{
                "source": "openalex",
                "query": plan["query"],
                "page": 1,
                "success": True,
                "result_count": 37,
            }]
        },
    )[0]

    assert result["executed_at"]
    assert result["attempt_count"] == 1
    assert result["hit_count"] == 37
    assert result["execution_metadata"]["actual_queries"] == [plan["query"]]


def test_human_ai_disagreement_requires_adjudication(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    paper = {"paper_id": "p1", "title": "Paper", "status": "pending"}
    manager.add_paper(session_id, paper)
    service.register_candidate(session_id, paper)
    service.record_screening(
        session_id,
        paper_id="p1",
        stage="full_text",
        decision="include",
        reason="Meets all criteria.",
        reviewer="human",
        actor_type="human",
    )
    service.record_screening(
        session_id,
        paper_id="p1",
        stage="full_text",
        decision="exclude",
        reason_code="wrong_outcome",
        reason="Outcome does not match.",
        reviewer="ai",
        actor_type="ai",
        blinded_to_peer=True,
    )

    assert service.flow_counts(session_id)["screening_conflicts"] == 1
    assert service.flow_counts(session_id)["unresolved"] == 1

    service.resolve_screening_conflict(
        session_id,
        paper_id="p1",
        stage="full_text",
        decision="include",
        reason_code=None,
        reason="Human adjudication verified the primary outcome.",
    )

    assert service.flow_counts(session_id)["screening_conflicts"] == 0
    assert service._resolved_screening_decisions(session_id)[
        (service._read(session_id, "candidates.json", [])[0]["candidate_id"], "full_text")
    ]["decision"] == "include"


def test_secondary_evidence_cannot_support_performance_claim(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.update_protocol(session_id, {"mode": "technical", "candidate_cap": 300})
    service.confirm_protocol(session_id)
    paper = {
        "paper_id": "survey-1",
        "title": "A Survey on Retrieval-Augmented Generation",
        "authors": ["Survey Author"],
        "status": "accepted",
    }
    manager.add_paper(session_id, paper)
    service.register_candidate(session_id, paper)
    service.confirm_inclusion_snapshot(session_id, ["survey-1"])
    service.save_extraction(
        session_id,
        "survey-1",
        {
            "study_or_article_type": "narrative_survey",
            "evidence_basis": "full_text",
            "evidence_locations": [{"page": 4, "section": "Results"}],
        },
    )

    audit = service.audit_review_claims(
        session_id,
        (
            "## 结果\n\n该方法在统一基准中显著提高了事实准确率，并且因此应当作为"
            "所有生产系统的默认技术路线 [P1]。"
        ),
        [paper],
    )

    assert audit["passed"] is False
    assert audit["evidence_mismatches"]
    assert audit["normative_strength_issues"]


def test_quantitative_result_requires_full_context(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    paper = {"paper_id": "p1", "title": "Benchmark", "status": "accepted"}
    manager.add_paper(session_id, paper)
    service.register_candidate(session_id, paper)
    extraction = service.save_extraction(
        session_id,
        "p1",
        {
            "study_or_article_type": "benchmark",
            "evidence_basis": "full_text",
            "quantitative_results": [{
                "metric": "accuracy",
                "method_value": 0.97,
                "effect_type": "absolute",
                "page": 8,
            }],
        },
    )

    validation = extraction["quantitative_results"][0]["context_validation"]
    assert validation["complete"] is False
    assert {"dataset_or_task", "base_model", "baseline"} <= set(validation["missing_fields"])


def test_technical_review_injects_method_tables_figure_and_ieee_references(tmp_path):
    manager, session, service = _service(tmp_path, topic="Retrieval augmented generation")
    session_id = session["session_id"]
    service.update_protocol(
        session_id,
        {
            "mode": "technical",
            "candidate_cap": 300,
            "sources": ["OpenAlex"],
        },
    )
    service.confirm_protocol(session_id)
    paper = {
        "paper_id": "p1",
        "title": "Corrective Retrieval Augmented Generation",
        "authors": "Shi-Qi Yan, Jia-Chen Gu",
        "published_year": 2024,
        "doi": "10.0000/example",
        "status": "accepted",
    }
    manager.add_paper(session_id, paper)
    service.register_candidate(session_id, paper)
    service.confirm_inclusion_snapshot(session_id, ["p1"])
    service.save_extraction(
        session_id,
        "p1",
        {
            "study_or_article_type": "framework",
            "population_or_dataset": "PopQA",
            "intervention_or_method": "CRAG",
            "technical_mechanism": {
                "method_family": "Corrective RAG",
                "inputs": ["retrieved passages"],
                "decision_rule": "retrieval evaluator",
                "trigger_granularity": "retrieval step",
                "actions": ["web search", "knowledge refinement"],
                "failure_propagation": ["evaluator errors trigger wrong action"],
            },
            "quantitative_results": [{
                "dataset_or_task": "PopQA",
                "base_model": "LLaMA2-7B",
                "baseline": "RAG",
                "metric": "accuracy",
                "baseline_value": 0.40,
                "method_value": 0.47,
                "effect_type": "absolute",
                "aggregation": "test-set accuracy",
                "statistical_significance": "not reported",
                "evidence_location": {"page": 8, "table": 1},
            }],
            "evidence_locations": [{"page": 8, "section": "Results"}],
        },
    )

    review = service.inject_deterministic_review_sections(
        session_id,
        "# RAG\n\n## 方法\n\n模型生成的方法描述。\n\n## 结果\n\n证据综合。",
        [paper],
    )

    assert "模型生成的方法描述" not in review
    assert review.count("|---") >= 4
    assert "```mermaid" in review
    assert "表1：纳入研究基本信息" in review
    assert "## 参考文献" in review
    assert "[P1]" in review


def test_methodology_report_reconciles_flow_and_reports_exclusions(tmp_path):
    manager, session, service = _service(tmp_path)
    session_id = session["session_id"]
    service.confirm_protocol(session_id)
    for paper_id in ("p1", "p2"):
        paper = {"paper_id": paper_id, "title": paper_id, "status": "pending"}
        manager.add_paper(session_id, paper)
        service.register_candidate(session_id, paper)
    service.record_screening(
        session_id,
        paper_id="p1",
        stage="title_abstract",
        decision="include",
        reason="Relevant.",
    )
    service.record_screening(
        session_id,
        paper_id="p2",
        stage="title_abstract",
        decision="exclude",
        reason_code="not_relevant",
        reason="Not relevant.",
    )
    service.confirm_inclusion_snapshot(session_id, ["p1"])

    report = service.methodology_report(session_id)

    assert report["reconciled"] is True
    assert report["exclusion_reason_counts"]["not_relevant"] == 1
    assert "not dual-human" in report["ai_participation_disclosure"].lower()


def test_methodology_depth_migration_declares_new_columns():
    migration = (
        __import__("pathlib").Path(__file__).parents[1]
        / "supabase"
        / "migrations"
        / "004_review_methodology_depth.sql"
    ).read_text(encoding="utf-8")
    for column in (
        "compiled_query",
        "executed_at",
        "actor_type",
        "blinded_to_peer",
        "study_or_article_type",
        "quantitative_results",
        "technical_mechanism",
        "numeric_context_complete",
    ):
        assert column in migration
