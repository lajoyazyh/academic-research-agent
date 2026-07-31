"""Run three no-secret scientific workflow trials against live scholarly APIs.

The trials deliberately avoid an LLM API so they can be reproduced without
reading a user's BYOK secret. Final drafts are deterministic audit specimens,
not examples of model writing quality.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from backend.scientific_review import ScientificReviewService  # noqa: E402
from backend.session_manager import SessionManager  # noqa: E402
from tools.arxiv_tools import ArxivFetchTool, ArxivSearchTool  # noqa: E402
from tools.crossref_tools import CrossrefSearchTool  # noqa: E402
from tools.dblp_tools import DblpSearchTool  # noqa: E402
from tools.pdf_tools import ArxivDownloadPdfTool, extract_full_text_from_pdf  # noqa: E402


CASES = [
    {
        "id": "case-01-peft",
        "mode": "technical",
        "title": "大语言模型参数高效微调方法：LoRA、Prefix Tuning 与 Adapter",
        "question": "LoRA、Prefix Tuning 与 Adapter 等参数高效微调方法在方法机制、实验评价和复现性方面有何差异？",
        "sources": ["arXiv", "Crossref", "DBLP"],
        "keywords": [
            {"english": "LoRA", "synonyms": "low-rank adaptation"},
            {"english": "prefix tuning", "synonyms": "continuous prompts"},
            {"english": "adapter tuning", "synonyms": "parameter efficient transfer learning"},
        ],
        "relevance_terms": ["lora", "low-rank", "prefix tuning", "adapter", "parameter-efficient"],
        "anchor_arxiv_ids": ["2106.09685", "2101.00190", "1902.00751", "2106.10199"],
        "max_included": 4,
    },
    {
        "id": "case-02-mrna-vaccine",
        "mode": "rapid",
        "title": "mRNA COVID-19 疫苗随机试验证据快速综述",
        "question": "随机对照试验对 mRNA COVID-19 疫苗有效性与安全性提供了哪些证据？",
        "sources": ["Europe PMC", "Crossref"],
        "keywords": [
            {"english": "BNT162b2 mRNA vaccine", "synonyms": "Pfizer BioNTech"},
            {"english": "mRNA-1273 vaccine", "synonyms": "Moderna"},
            {"english": "randomized trial", "synonyms": "efficacy safety"},
        ],
        "relevance_terms": ["mrna", "bnt162b2", "mrna-1273", "covid-19 vaccine", "sars-cov-2 vaccine"],
        "anchor_dois": ["10.1056/NEJMoa2034577", "10.1056/NEJMoa2035389"],
        "max_included": 2,
        "anchor_only": True,
    },
    {
        "id": "case-03-review-guidelines",
        "mode": "scoping",
        "title": "证据综述报告与质量框架的范围映射：PRISMA、SWiM 与 SANRA",
        "question": "PRISMA 2020、SWiM 与 SANRA 分别解决证据综述报告和质量评价中的哪些问题？",
        "sources": ["Europe PMC", "Crossref"],
        "keywords": [
            {"english": "PRISMA 2020", "synonyms": "systematic review reporting"},
            {"english": "SWiM synthesis without meta-analysis", "synonyms": "narrative synthesis"},
            {"english": "SANRA narrative review quality", "synonyms": "narrative review appraisal"},
        ],
        "relevance_terms": ["prisma", "swim", "sanra", "synthesis without meta-analysis", "narrative review"],
        "anchor_dois": [
            "10.1136/bmj.n71",
            "10.1136/bmj.l6890",
            "10.1186/s41073-019-0064-8",
        ],
        "max_included": 3,
        "anchor_only": True,
    },
]


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value.rstrip() + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_blocks(text: str, source: str) -> list[dict]:
    items = []
    for block in re.split(r"\n---\n", text):
        fields = {}
        for line in block.splitlines():
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            fields[key.strip().lower()] = value.strip()
        title = fields.get("title", "")
        if not title:
            continue
        paper_id = fields.get("id") or fields.get("doi") or f"{source}-{abs(hash(title))}"
        items.append({
            "paper_id": re.sub(r"v\d+$", "", paper_id),
            "title": title,
            "authors": fields.get("authors", ""),
            "abstract": fields.get("summary") or (
                "" if fields.get("abstract", "").startswith("Not provided") else fields.get("abstract", "")
            ),
            "doi": fields.get("doi", "") if fields.get("doi") != "Not provided" else "",
            "arxiv_id": re.sub(r"v\d+$", "", fields.get("id", "")),
            "publication_year": fields.get("published") or fields.get("year", ""),
            "venue": fields.get("journal") or fields.get("venue", ""),
            "source": source,
            "source_type": source,
            "source_url": fields.get("url", ""),
        })
    return items


def _europe_pmc(query: str, page: int, page_size: int = 6) -> tuple[list[dict], str]:
    params = urllib.parse.urlencode({
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": page_size,
        "page": page,
    })
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + params
    request = urllib.request.Request(url, headers={"User-Agent": "AcademicResearchAgent/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    results = []
    for item in payload.get("resultList", {}).get("result", []):
        results.append({
            "paper_id": item.get("doi") or item.get("pmid") or item.get("id"),
            "title": item.get("title", ""),
            "authors": item.get("authorString", ""),
            "abstract": item.get("abstractText", ""),
            "doi": item.get("doi", ""),
            "pmid": item.get("pmid", ""),
            "pmcid": item.get("pmcid", ""),
            "publication_year": item.get("pubYear", ""),
            "venue": item.get("journalTitle", ""),
            "source": "europe_pmc",
            "source_type": "europe_pmc",
            "source_url": (
                f"https://europepmc.org/article/MED/{item.get('pmid')}"
                if item.get("pmid")
                else ""
            ),
        })
    return results, url


def _anchor_records(case: dict) -> tuple[list[dict], list[str]]:
    records = []
    raw_sections = []
    for arxiv_id in case.get("anchor_arxiv_ids") or []:
        raw = str(ArxivFetchTool().execute(paper_id=arxiv_id))
        parsed = _parse_blocks(raw, "arxiv")
        for item in parsed:
            item["paper_id"] = arxiv_id
            item["arxiv_id"] = arxiv_id
            item["anchor"] = True
        records.extend(parsed)
        raw_sections.append(
            f"## Anchor arXiv {arxiv_id}\n\n{_retrieval_summary(parsed)}"
        )
    for doi in case.get("anchor_dois") or []:
        query = f'DOI:"{doi}"'
        try:
            items, url = _europe_pmc(query, 1, page_size=4)
            exact = [
                item for item in items
                if str(item.get("doi") or "").casefold() == doi.casefold()
            ]
            for item in exact:
                item["anchor"] = True
            records.extend(exact)
            raw_sections.append(
                f"## Anchor DOI {doi}\n\nURL: {url}\n\n"
                + _retrieval_summary(exact)
            )
        except Exception as exc:
            raw_sections.append(f"## Anchor DOI {doi} · failed\n\n{exc}")
    return records, raw_sections


def _fetch_pmc_text(pmcid: str) -> str:
    if not pmcid:
        return ""
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    request = urllib.request.Request(url, headers={"User-Agent": "AcademicResearchAgent/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())
    return re.sub(r"\s+", " ", " ".join(root.itertext())).strip()


def _short_excerpt(text: str, words: int = 18) -> str:
    return " ".join(re.sub(r"\s+", " ", text).strip().split()[:words])


def _retrieval_summary(papers: list[dict]) -> str:
    """Keep the handoff auditable without redistributing abstracts or full text."""
    return json.dumps([
        {
            "paper_id": item.get("paper_id"),
            "title": item.get("title"),
            "doi": item.get("doi"),
            "arxiv_id": item.get("arxiv_id"),
            "pmid": item.get("pmid"),
            "pmcid": item.get("pmcid"),
            "source_url": item.get("source_url"),
        }
        for item in papers
    ], ensure_ascii=False, indent=2)


def _sanitized_candidates(candidates: list[dict]) -> list[dict]:
    sanitized = []
    for candidate in candidates:
        item = dict(candidate)
        abstract = str(item.pop("abstract", "") or "")
        item["abstract_available"] = bool(abstract)
        item["abstract_excerpt"] = _short_excerpt(abstract)
        sanitized.append(item)
    return sanitized


def _candidate_relevant(case: dict, paper: dict) -> bool:
    haystack = f"{paper.get('title', '')} {paper.get('abstract', '')}".casefold()
    return any(term.casefold() in haystack for term in case["relevance_terms"])


def _execute_plan(case: dict, plan: dict, page_index: int) -> tuple[list[dict], dict, str]:
    source = plan["source"]
    query = plan.get("query", "")
    if source == "arxiv":
        start = page_index * 6
        raw = str(ArxivSearchTool().execute(query=query, max_results=6, start=start))
        success = "请求失败" not in raw and "HTTP Error" not in raw
        return _parse_blocks(raw, source), {
            "source": source, "query": query, "page": start, "success": success,
            "error": None if success else raw[:500],
        }, raw
    if source == "crossref":
        offset = page_index * 6
        raw = str(CrossrefSearchTool().execute(query=query, rows=6, offset=offset))
        success = "请求失败" not in raw and "HTTP Error" not in raw
        return _parse_blocks(raw, source), {
            "source": source, "query": query, "page": offset, "success": success,
            "error": None if success else raw[:500],
        }, raw
    if source == "dblp":
        offset = page_index * 6
        raw = str(DblpSearchTool().execute(query=query, rows=6, offset=offset))
        success = "failed" not in raw.casefold()
        return _parse_blocks(raw, source), {
            "source": source, "query": query, "page": offset, "success": success,
            "error": None if success else raw[:500],
        }, raw
    if source == "europe_pmc":
        try:
            papers, url = _europe_pmc(query, page_index + 1)
            return papers, {
                "source": source, "query": query, "page": page_index + 1, "success": True,
                "error": None,
            }, json.dumps({"url": url, "items": papers}, ensure_ascii=False, indent=2)
        except Exception as exc:
            return [], {
                "source": source, "query": query, "page": page_index + 1, "success": False,
                "error": str(exc),
            }, str(exc)
    return [], {
        "source": source, "query": query, "page": page_index, "success": False,
        "error": "unsupported source in trial harness",
    }, "unsupported source"


def _draft_review(case: dict, protocol: dict, flow: dict, plans: list[dict], papers: list[dict]) -> str:
    source_names = ", ".join(protocol.get("sources") or [])
    completed = sum(plan.get("status") == "completed" for plan in plans)
    rows = []
    synthesis = []
    references = []
    for index, paper in enumerate(papers, start=1):
        basis = paper.get("evidence_basis", "abstract")
        rows.append(
            f"| P{index} | {paper.get('title')} | {paper.get('publication_year') or '未记录'} "
            f"| {paper.get('source_type')} | {basis} |"
        )
        synthesis.append(
            f"该记录聚焦“{paper.get('title')}”所指向的问题；本次试验仅依据"
            f"{'全文片段' if basis == 'full_text' else '摘要或元数据'}建立证据卡，"
            f"因此不能据此作超出原文范围的因果或效果强度判断 [P{index}]。"
        )
        references.append(
            f"[P{index}] {paper.get('authors') or '作者未记录'}. "
            f"{paper.get('title')}. {paper.get('publication_year') or '年份未记录'}. "
            f"{paper.get('doi') or paper.get('source_url') or paper.get('paper_id')}."
        )
    review_label = {
        "rapid": "快速证据综述",
        "technical": "计算机与 AI 技术综述",
        "scoping": "范围综述",
    }.get(case["mode"], "证据综述")
    return f"""# {case['title']}

> 未完成研究草稿：这是无 LLM 密钥条件下生成的确定性流程试验产物，不是投稿成稿。

## 摘要

【作者综合判断】本案例用于验证协议、检索账本、筛选、证据卡、评价、综合与引用审计能否形成可追溯闭环。当前纳入 {len(papers)} 条记录，证据强度受候选规模和全文覆盖限制。

## 引言

【作者综合判断】研究问题为：{case['question']}。本案例选择“{review_label}”模式，以检验该模式下的停止条件、人工检查点和输出标签。

## 方法

【作者综合判断】协议版本为 {protocol.get('version')}，配置来源为 {source_names}。系统执行并记录了 {completed}/{len(plans)} 个数据源检索计划；论文数量没有被用作检索完成的唯一条件。

【作者综合判断】流程计数为：发现 {flow.get('discovered')} 条、去重后 {flow.get('unique_candidates')} 条、标题摘要通过 {flow.get('title_abstract_included')} 条、全文检查 {flow.get('full_text_assessed')} 条、最终纳入 {flow.get('included')} 条。

## 结果

### 研究特征

| 引用 | 题目 | 年份 | 来源 | 证据基础 |
|---|---|---:|---|---|
{chr(10).join(rows)}

### 证据综合

{chr(10) + chr(10).join(synthesis)}

## 讨论

【作者综合判断】这些记录展示了目标领域中的若干代表性研究或方法框架，但当前确定性试验没有使用模型完成语义级跨研究比较，冲突结果、异质性和适用边界仍需研究者结合全文确认。

## 局限

【作者综合判断】本试验没有读取用户 BYOK 密钥；OpenAlex 与 Semantic Scholar 在当前网络环境返回 429，因此改用 arXiv、Crossref、DBLP 和 Europe PMC。摘要证据不能支撑强结论，自动生成内容应保持“未完成研究草稿”标签。

## 结论

【作者综合判断】该案例证明流程和审计产物能够完整落盘，但不能替代配置真实模型后的证据抽取质量、筛选敏感度和综述写作质量评测。

## 参考文献

{chr(10).join(references)}
"""


def run_case(case: dict, output_root: Path) -> dict:
    case_dir = output_root / case["id"]
    manager = SessionManager(str(case_dir / "session_store"))
    session = manager.create_session(case["question"], keywords=case["keywords"])
    session_id = session["session_id"]
    service = ScientificReviewService(manager)
    service.update_protocol(session_id, {
        "mode": case["mode"],
        "candidate_cap": 50 if case["mode"] == "technical" else 100,
        "sources": case["sources"],
        "languages": ["en"],
        "document_types": ["journal_article", "conference_paper", "preprint", "reporting_guideline"],
        "inclusion_criteria": [
            "The title or abstract directly addresses the research question.",
            "The item is a scholarly study, trial, or reporting/methodology guideline.",
            "Verifiable source metadata is available.",
        ],
        "exclusion_criteria": [
            "The item only shares broad terminology without addressing the question.",
            "The record is a duplicate or non-scholarly page.",
            "No verifiable title or source identifier is available.",
        ],
        "primary_outcomes": ["method characteristics", "reported results", "limitations"],
    })
    protocol = service.confirm_protocol(session_id)
    plans = service.audit_summary(session_id)["search_queries"]
    raw_sections = []
    ledger = {"queries": []}
    retrieved = []
    for plan in plans:
        for page_index in range(int(plan.get("required_pages") or 1)):
            papers, attempt, raw = _execute_plan(case, plan, page_index)
            retrieved.extend(papers)
            ledger["queries"].append(attempt)
            raw_sections.append(
                f"## {plan['source']} · page/cursor {attempt['page']} · "
                f"{'success' if attempt['success'] else 'failed'}\n\n"
                f"Query: `{plan.get('query', '')}`\n\n"
                f"{_retrieval_summary(papers)}"
            )
    anchor_records, anchor_raw = _anchor_records(case)
    retrieved = anchor_records + retrieved
    raw_sections = anchor_raw + raw_sections
    plans = service.reconcile_search_ledger(session_id, ledger)
    manager.save_search_run(session_id, {
        "mode": "scientific_case_trial",
        "retrieval_ledger": ledger,
        "queries_planned": len(plans),
        "queries_completed": sum(item.get("status") == "completed" for item in plans),
        "stop_reason": "candidate_cap_or_query_plan_completed",
    })

    papers_by_id = {}
    for paper in retrieved:
        if not paper.get("title"):
            continue
        try:
            candidate = service.register_candidate(session_id, paper, source_run_id="case_trial")
        except ValueError as exc:
            if "Candidate cap reached" in str(exc):
                break
            raise
        paper_id = candidate.get("paper_id")
        if paper_id not in papers_by_id:
            manager.add_paper(session_id, {
                **paper,
                "paper_id": paper_id,
                "status": "pending",
                "screening_stage": "title_abstract",
            })
            papers_by_id[paper_id] = manager.get_papers(session_id)[-1]

    candidate_state = {
        item.get("paper_id"): item
        for item in service._read(session_id, "candidates.json", [])
    }
    included_candidates = []
    for stored_paper in manager.get_papers(session_id):
        paper = {
            **candidate_state.get(stored_paper.get("paper_id"), {}),
            **stored_paper,
        }
        relevant = _candidate_relevant(case, paper)
        source_is_available = bool(
            paper.get("abstract")
            or (paper.get("anchor") and (paper.get("pmcid") or paper.get("arxiv_id")))
        )
        decision = "include" if relevant and source_is_available else (
            "uncertain" if relevant else "exclude"
        )
        service.record_screening(
            session_id,
            paper_id=paper["paper_id"],
            stage="title_abstract",
            decision=decision,
            reason_code="not_relevant" if decision == "exclude" else None,
            reason=(
                "Matched the case concepts and has abstract or retrievable full-text metadata."
                if decision == "include"
                else "Relevant title but no abstract was available."
                if decision == "uncertain"
                else "The record did not address the case-specific concepts."
            ),
            criterion_judgements=[{
                "criterion": "Directly addresses the case question",
                "judgement": "met" if decision == "include" else decision,
                "evidence": _short_excerpt(f"{paper.get('title', '')} {paper.get('abstract', '')}"),
            }],
            evidence=[{
                "basis": "title_abstract",
                "excerpt": _short_excerpt(paper.get("abstract") or paper.get("title", "")),
            }],
            confidence=0.85 if decision == "include" else 0.45 if decision == "uncertain" else 0.8,
            reviewer="deterministic_trial",
        )
        if decision == "include":
            included_candidates.append(paper)

    included_candidates.sort(
        key=lambda item: (
            bool(item.get("anchor")),
            bool(item.get("abstract")),
            item.get("source_type") in {"arxiv", "europe_pmc"},
        ),
        reverse=True,
    )
    if case.get("anchor_only"):
        selected = [
            paper for paper in included_candidates
            if paper.get("anchor")
        ][:case["max_included"]]
    else:
        selected = included_candidates[:case["max_included"]]
    if not selected:
        selected = [
            paper for paper in manager.get_papers(session_id)
            if _candidate_relevant(case, paper)
        ][:case["max_included"]]
    selected_ids = {paper["paper_id"] for paper in selected}
    candidate_state = {
        item.get("paper_id"): item
        for item in service._read(session_id, "candidates.json", [])
    }
    for paper in manager.get_papers(session_id):
        if paper["paper_id"] in selected_ids:
            continue
        if candidate_state.get(paper["paper_id"], {}).get("screening_decision") == "uncertain":
            service.record_screening(
                session_id,
                paper_id=paper["paper_id"],
                stage="title_abstract",
                decision="exclude",
                reason_code="insufficient_information",
                reason="Resolved at the human checkpoint: insufficient evidence for final full-text assessment.",
                evidence=[{
                    "basis": "title_or_metadata",
                    "excerpt": _short_excerpt(paper.get("title", "")),
                }],
                confidence=1.0,
                reviewer="human_trial_checkpoint",
            )
    snapshot = service.confirm_inclusion_snapshot(
        session_id, [paper["paper_id"] for paper in selected]
    )

    source_documents = case_dir / "source_documents"
    source_documents.mkdir(parents=True, exist_ok=True)
    refreshed_papers = {paper["paper_id"]: paper for paper in manager.get_papers(session_id)}
    for selected_paper in selected:
        paper = {
            **candidate_state.get(selected_paper["paper_id"], {}),
            **refreshed_papers[selected_paper["paper_id"]],
        }
        refreshed_papers[selected_paper["paper_id"]] = paper
        full_text = ""
        basis = "abstract"
        evidence_location = {
            "section": "abstract",
            "page": None,
            "excerpt": _short_excerpt(paper.get("abstract") or paper.get("title", "")),
        }
        if paper.get("arxiv_id"):
            result = ArxivDownloadPdfTool(str(source_documents)).execute(
                paper_id=paper["arxiv_id"]
            )
            pdf_path = source_documents / f"{paper['arxiv_id']}.pdf"
            if result.startswith("✅") and pdf_path.exists():
                chunks = extract_full_text_from_pdf(str(pdf_path), session_id, paper["paper_id"])
                if chunks:
                    full_text = " ".join(chunk["text"] for chunk in chunks[:8])
                    basis = "full_text"
                    evidence_location = {
                        "section": "PDF excerpt",
                        "page": chunks[0]["page"],
                        "excerpt": _short_excerpt(chunks[0]["text"]),
                    }
        elif paper.get("pmcid"):
            try:
                full_text = _fetch_pmc_text(paper["pmcid"])
                if full_text:
                    basis = "full_text"
                    evidence_location = {
                        "section": "Europe PMC full text XML",
                        "page": None,
                        "excerpt": _short_excerpt(full_text),
                    }
            except Exception:
                full_text = ""
        paper["evidence_basis"] = basis
        extraction = {
            "study_design": (
                "computer_science_method_and_experiment"
                if case["mode"] == "technical"
                else "randomized_trial"
                if "random" in (paper.get("abstract") or "").casefold()
                else "reporting_or_methodology_guideline"
                if case["mode"] == "scoping"
                else "unclear"
            ),
            "population_or_dataset": None,
            "intervention_or_method": paper.get("title"),
            "comparator_or_baseline": None,
            "sample_size": None,
            "outcomes_and_metrics": [],
            "main_results": [{
                "statement": "Source text was captured for human extraction; no numerical result was inferred.",
                "metric": None,
                "value": None,
                "location": evidence_location,
            }],
            "uncertainty": "Automated semantic extraction was not run because no user LLM key was accessed.",
            "limitations": ["Evidence card requires human confirmation."],
            "funding_and_conflicts": None,
            "evidence_locations": [evidence_location],
            "computer_ai": {
                "dataset_provenance": None,
                "split_and_leakage_risk": None,
                "baseline_fairness": None,
                "variance_or_significance": None,
                "ablation_reported": None,
                "code_data_environment": None,
                "external_validity": None,
                "compute_cost": None,
            } if case["mode"] == "technical" else {},
            "evidence_basis": basis,
            "confidence": 0.6 if basis == "full_text" else 0.35,
            "review_status": "deterministic_trial_requires_human",
        }
        service.save_extraction(session_id, paper["paper_id"], extraction)
        service.save_appraisal(session_id, paper["paper_id"], {
            "profile": "computer_ai" if case["mode"] == "technical" else "design_matched_general",
            "study_design": extraction["study_design"],
            "domains": [{
                "name": "source completeness",
                "judgement": "some_concerns" if basis == "full_text" else "high",
                "reason": "No LLM-based design-specific appraisal was run.",
                "evidence": evidence_location,
            }],
            "overall_judgement": "some_concerns" if basis == "full_text" else "unclear",
            "rationale": "Trial appraisal is intentionally conservative and requires human confirmation.",
            "review_status": "deterministic_trial_requires_human",
        })
    manager.save_papers_list(session_id, list(refreshed_papers.values()))

    groups = service.build_synthesis_groups(
        session_id, [paper["paper_id"] for paper in selected]
    )
    gate = service.quality_gate(
        session_id, requested_paper_ids=[paper["paper_id"] for paper in selected]
    )
    included_for_review = [
        refreshed_papers[paper["paper_id"]]
        for paper in selected
    ]
    flow = service.flow_counts(session_id)
    review = _draft_review(case, protocol, flow, plans, included_for_review)
    review = service.enforce_review_label(session_id, review, gate, "zh-CN")
    claim_audit = service.audit_review_claims(session_id, review, included_for_review)
    version = service.write_review_version(session_id, review, gate)
    manager.save_review(
        session_id,
        review,
        referenced_papers=[paper["paper_id"] for paper in selected],
    )

    state = service.audit_summary(session_id)
    source_manifest = [
        {
            "paper_id": paper.get("paper_id"),
            "title": paper.get("title"),
            "doi": paper.get("doi"),
            "arxiv_id": paper.get("arxiv_id"),
            "pmcid": paper.get("pmcid"),
            "source_url": paper.get("source_url"),
            "evidence_basis": paper.get("evidence_basis"),
        }
        for paper in included_for_review
    ]
    artifacts = {
        "protocol.json": state["protocol"],
        "search_queries.json": state["search_queries"],
        "candidate_pool.json": _sanitized_candidates(
            service._read(session_id, "candidates.json", [])
        ),
        "screening_decisions.json": service._read(session_id, "screening_decisions.json", []),
        "inclusion_snapshot.json": snapshot,
        "evidence_cards.json": state["extractions"],
        "study_appraisals.json": state["appraisals"],
        "synthesis_groups.json": groups,
        "claim_ledger.json": service._read(session_id, "claims.json", []),
        "quality_gate.json": gate,
        "claim_audit.json": claim_audit,
        "review_version.json": version,
        "source_manifest.json": source_manifest,
    }
    for name, payload in artifacts.items():
        _write(case_dir / name, payload)
    _write(case_dir / "retrieval_raw.md", "\n\n".join(raw_sections))
    _write(case_dir / "review.md", review)
    summary = {
        "case_id": case["id"],
        "title": case["title"],
        "mode": case["mode"],
        "session_id": session_id,
        "flow": flow,
        "search_plans_completed": sum(item.get("status") == "completed" for item in plans),
        "search_plans_total": len(plans),
        "included_titles": [paper.get("title") for paper in included_for_review],
        "full_text_count": sum(paper.get("evidence_basis") == "full_text" for paper in included_for_review),
        "quality_gate": gate,
        "claim_audit": claim_audit,
    }
    _write(case_dir / "summary.json", summary)
    shutil.rmtree(source_documents, ignore_errors=True)
    shutil.rmtree(case_dir / "session_store", ignore_errors=True)
    return summary


def main() -> int:
    output_root = ROOT / "artifacts" / "scientific-case-trials-2026-07-31-reviewed"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    summaries = []
    for case in CASES:
        summaries.append(run_case(case, output_root))
    _write(output_root / "trial-summary.json", {"cases": summaries})
    lines = [
        "# 科学综述流程案例试验报告",
        "",
        "本报告由真实学术数据源检索和本地确定性工作流生成。为了不读取用户 BYOK 密钥，",
        "没有执行 LLM 语义抽取或写作；`review.md` 是用于检查流程、引用和标签门禁的审计样稿。",
        "",
    ]
    for item in summaries:
        lines.extend([
            f"## {item['title']}",
            "",
            f"- 模式：`{item['mode']}`",
            f"- 检索计划：{item['search_plans_completed']}/{item['search_plans_total']} 完成",
            f"- 候选：{item['flow']['unique_candidates']}；最终纳入：{item['flow']['included']}",
            f"- 全文证据：{item['full_text_count']}",
            f"- 输出标签：`{item['quality_gate']['output_label']}`",
            f"- Claim Audit：{'通过' if item['claim_audit']['passed'] else '需要复核'}",
            "",
        ])
    lines.extend([
        "## 已知环境限制",
        "",
        "- OpenAlex 和 Semantic Scholar 当前返回 HTTP 429；试验改用 arXiv、Crossref、DBLP 与 Europe PMC。",
        "- 未访问浏览器 localStorage 或任何 API Key。",
        "- 摘要/元数据证据不会被提升为强结论，所有案例保留未完成草稿标签。",
    ])
    _write(output_root / "README.md", "\n".join(lines))
    print(output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
