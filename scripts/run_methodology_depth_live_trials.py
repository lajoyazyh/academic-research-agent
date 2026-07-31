"""Run resumable live scholarly cases through the methodology-depth workflow.

The harness has two phases:

* ``prepare`` performs real bibliographic searches and builds confirmed
  protocols, query ledgers, and deduplicated candidate pools without an LLM.
* ``complete`` uses a request-scoped Zhipu key from ``ZHIPU_API_KEY`` for
  screening, full-text evidence extraction, appraisal, synthesis, writing,
  claim audit, and portable exports.

The key and source PDFs are never written to the artifact directory.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
OUTPUT_ROOT = ROOT / "artifacts" / "methodology-depth-live-trials-2026-07-31-v5"
RUNTIME_ROOT = OUTPUT_ROOT / ".runtime_sessions"
sys.path.insert(0, str(ROOT / "agent"))

from backend.artifact_export import _docx_bytes, _pdf_bytes, markdown_to_html  # noqa: E402
from backend.routes.agent import _extract_scientific_evidence  # noqa: E402
from backend.scientific_review import ScientificReviewService  # noqa: E402
from backend.session_manager import SessionManager  # noqa: E402
from llms.client import LLMClient  # noqa: E402
from prompts.review_skills import REVIEW_PRESETS  # noqa: E402
from tools.arxiv_tools import ArxivSearchTool, compile_arxiv_query  # noqa: E402
from tools.crossref_tools import CrossrefSearchTool  # noqa: E402
from tools.dblp_tools import DblpSearchTool  # noqa: E402
from tools.pdf_tools import ArxivDownloadPdfTool, extract_full_text_from_pdf  # noqa: E402
from utils.parser import extract_json  # noqa: E402


TODAY = dt.date.today().isoformat()
MODEL = os.getenv("ZHIPU_MODEL", "glm-4.7-flash")
BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
SOURCES = ["arXiv", "Crossref", "DBLP"]


class TrialLLMClient(LLMClient):
    """Bound individual extraction responses for the resumable live evaluation.

    The production schema remains unchanged.  This harness cap prevents a free
    model from spending most of an evaluation run emitting unused prose while
    still leaving room for the evidence card and seven-domain appraisal.
    """

    def chat(self, system_prompt: str, user_query: str, history: list) -> str:
        self._ensure_configured()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if user_query:
            messages.append({"role": "user", "content": user_query})
        retry_deadline = time.monotonic() + float(
            os.getenv("TRIAL_RETRY_WINDOW_SECONDS", "900")
        )
        delay = 8.0
        while True:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=3800,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                return str(response.choices[0].message.content or "")
            except Exception as exc:
                retryable = (
                    getattr(exc, "status_code", None) in {429, 500, 502, 503}
                    or exc.__class__.__name__ in {"APITimeoutError", "APIConnectionError"}
                )
                remaining = retry_deadline - time.monotonic()
                if not retryable or remaining <= 0:
                    raise
                time.sleep(min(delay, 60.0, remaining))
                delay = min(delay * 2, 60.0)

CASES = [
    {
        "id": "technical-rag",
        "mode": "technical",
        "title": "检索增强生成的架构、评价与可靠性技术证据综述",
        "question": (
            "检索增强生成系统在静态、迭代、按需与纠错式检索机制、"
            "可靠性评价、实验公平性和计算成本方面有哪些可验证证据与适用边界？"
        ),
        "keywords": [
            {
                "original": "检索增强生成",
                "english": "retrieval augmented generation",
                "synonyms": "RAG factuality reliability benchmark",
            },
            {
                "original": "动态与纠错检索",
                "english": "dynamic corrective retrieval augmented generation",
                "synonyms": "adaptive retrieval CRAG DRAGIN",
            },
            {
                "original": "RAG关键方法与基准",
                "english": "Self-RAG",
                "synonyms": "Corrective Retrieval Augmented Generation; DRAGIN; Benchmarking Large Language Models in Retrieval-Augmented Generation; Retrieval-Augmented Generation for Large Language Models A Survey",
            },
        ],
        "known_relevant_titles": [
            "Corrective Retrieval Augmented Generation",
            "DRAGIN: Dynamic Retrieval Augmented Generation based on the Information Needs of Large Language Models",
            "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
            "Benchmarking Large Language Models in Retrieval-Augmented Generation",
            "Retrieval-Augmented Generation for Large Language Models: A Survey",
        ],
        "date_from": "2020-01-01",
        "inclusion": [
            "直接研究RAG架构、检索控制、可靠性评价或计算成本",
            "提供原始实验、基准或具有实证验证的技术框架",
            "综述文章仅用于分类与研究版图",
            "能够获得足以核验机制和结果的全文",
        ],
    },
    {
        "id": "technical-peft",
        "mode": "technical",
        "title": "参数高效微调方法的机制、证据与工程权衡技术综述",
        "question": (
            "LoRA、量化低秩适配、Adapter和Prompt/Prefix Tuning在可训练参数、"
            "基线公平性、性能、训练与推理成本、复现性和失效条件方面有何差异？"
        ),
        "keywords": [
            {
                "original": "参数高效微调",
                "english": "parameter efficient fine tuning",
                "synonyms": "PEFT adapter prefix prompt tuning",
            },
            {
                "original": "低秩适配",
                "english": "low rank adaptation language models",
                "synonyms": "LoRA QLoRA AdaLoRA",
            },
            {
                "original": "PEFT关键方法",
                "english": "LoRA",
                "synonyms": "QLoRA; AdaLoRA; Prefix-Tuning; Parameter-Efficient Transfer Learning for NLP",
            },
        ],
        "known_relevant_titles": [
            "LoRA: Low-Rank Adaptation of Large Language Models",
            "QLoRA: Efficient Finetuning of Quantized LLMs",
            "Prefix-Tuning: Optimizing Continuous Prompts for Generation",
            "Parameter-Efficient Transfer Learning for NLP",
            "AdaLoRA: Adaptive Budget Allocation for Parameter-Efficient Fine-Tuning",
        ],
        "date_from": "2018-01-01",
        "inclusion": [
            "提出或实证评价语言模型参数高效微调方法",
            "报告至少一个任务、数据集、基线或资源指标",
            "能够区分训练参数、存储、训练成本与推理成本",
            "能够获得足以核验机制和结果的全文",
        ],
    },
    {
        "id": "scoping-agent-evaluation",
        "mode": "scoping",
        "title": "LLM Agent评测研究的范围、基准与有效性风险",
        "question": (
            "LLM Agent的规划、工具使用、记忆、协作和长程任务能力如何被评测，"
            "现有基准的任务设计、指标、复现性、污染风险与外部有效性有哪些证据缺口？"
        ),
        "keywords": [
            {
                "original": "LLM Agent评测",
                "english": "large language model agents evaluation benchmark",
                "synonyms": "autonomous agents benchmark",
            },
            {
                "original": "长程工具使用",
                "english": "LLM agent planning tool use long horizon tasks",
                "synonyms": "agent reliability reproducibility benchmark",
            },
            {
                "original": "Agent关键基准",
                "english": "AgentBench",
                "synonyms": "ToolLLM; WebArena; GAIA benchmark; SWE-bench",
            },
        ],
        "known_relevant_titles": [
            "AgentBench: Evaluating LLMs as Agents",
            "ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs",
            "WebArena: A Realistic Web Environment for Building Autonomous Agents",
            "GAIA: a benchmark for General AI Assistants",
            "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
        ],
        "date_from": "2022-01-01",
        "inclusion": [
            "定义或实证评价具有目标、状态、动作与反馈循环的LLM Agent",
            "覆盖规划、工具使用、记忆、协作或长程任务中的至少一项",
            "报告基准任务、指标、模型或可复现信息",
            "能够获得全文或足够的方法学说明",
        ],
    },
]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def parse_blocks(text: str, source: str) -> list[dict]:
    items = []
    for block in re.split(r"\n---\n", str(text or "")):
        fields = {}
        for line in block.splitlines():
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            fields[key.strip().lower()] = value.strip()
        title = fields.get("title", "")
        if not title:
            continue
        raw_id = fields.get("id") or fields.get("doi") or ""
        arxiv_id = (
            re.sub(r"v\d+$", "", fields.get("id", ""))
            if source == "arxiv"
            else ""
        )
        doi = fields.get("doi", "")
        if doi == "Not provided":
            doi = ""
        paper_id = arxiv_id or doi or raw_id or f"{source}-{abs(hash(title))}"
        source_url = fields.get("url", "")
        if arxiv_id:
            source_url = f"https://arxiv.org/abs/{arxiv_id}"
        items.append(
            {
                "paper_id": paper_id,
                "title": title,
                "authors": fields.get("authors", ""),
                "abstract": fields.get("summary") or (
                    ""
                    if fields.get("abstract", "").startswith("Not provided")
                    else fields.get("abstract", "")
                ),
                "doi": doi,
                "arxiv_id": arxiv_id,
                "publication_year": (
                    fields.get("published") or fields.get("year", "")
                )[:4],
                "venue": fields.get("journal") or fields.get("venue", ""),
                "source": source,
                "source_type": source,
                "source_url": source_url,
                "pdf_url": (
                    f"https://arxiv.org/pdf/{arxiv_id}"
                    if arxiv_id
                    else fields.get("pdf", "")
                ),
            }
        )
    return items


def execute_search(plan: dict, page_index: int, mode: str) -> tuple[list[dict], dict]:
    source = str(plan.get("source") or "")
    query = str(plan.get("compiled_query") or plan.get("query") or "")
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        if source == "arxiv":
            page_size = 10 if mode == "technical" else 8
            start = page_index * page_size
            raw = str(
                ArxivSearchTool().execute(
                    query=query,
                    max_results=page_size,
                    start=start,
                )
            )
            rows = parse_blocks(raw, source)
            page_value = start
            actual_query = compile_arxiv_query(query)
            actual_field_mapping = ["arXiv all-field Boolean query"]
        elif source == "crossref":
            page_size = 5 if mode == "technical" else 4
            offset = page_index * page_size
            raw = str(
                CrossrefSearchTool().execute(
                    query=query,
                    rows=page_size,
                    offset=offset,
                )
            )
            rows = parse_blocks(raw, source)
            page_value = offset
            actual_field_mapping = ["Crossref bibliographic query"]
        elif source == "dblp":
            page_size = 5 if mode == "technical" else 4
            offset = page_index * page_size
            raw = str(
                DblpSearchTool().execute(
                    query=query,
                    rows=page_size,
                    offset=offset,
                )
            )
            rows = parse_blocks(raw, source)
            page_value = offset
            actual_field_mapping = ["DBLP bibliographic query"]
        else:
            raise ValueError(f"Unsupported live-trial source: {source}")
        if source != "arxiv":
            actual_query = query
        return rows, {
            "search_query_id": plan.get("search_query_id"),
            "source": source,
            "query": actual_query,
            "original_query": plan.get("original_query"),
            "compiled_query": actual_query,
            "page": page_value,
            "result_count": len(rows),
            "success": True,
            "error": None,
            "started_at": started_at,
            "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "field_mapping": actual_field_mapping,
            "filters": plan.get("filters") or {},
        }
    except Exception as exc:
        return [], {
            "search_query_id": plan.get("search_query_id"),
            "source": source,
            "query": query,
            "original_query": plan.get("original_query"),
            "compiled_query": query,
            "page": page_index,
            "result_count": 0,
            "success": False,
            "error": str(exc)[:500],
            "started_at": started_at,
            "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "field_mapping": [],
            "filters": plan.get("filters") or {},
        }


def sanitized_candidates(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        abstract = re.sub(r"\s+", " ", str(row.get("abstract") or "")).strip()
        output.append(
            {
                key: row.get(key)
                for key in (
                    "candidate_id",
                    "paper_id",
                    "title",
                    "authors",
                    "publication_year",
                    "doi",
                    "arxiv_id",
                    "venue",
                    "source_url",
                    "sources",
                    "duplicate_count",
                    "discovered_at",
                )
            }
            | {
                "abstract_available": bool(abstract),
                "abstract_excerpt": " ".join(abstract.split()[:36]),
            }
        )
    return output


def title_matches(expected: str, observed: str) -> bool:
    left = set(re.findall(r"[a-z0-9]+", str(expected).casefold()))
    right = set(re.findall(r"[a-z0-9]+", str(observed).casefold()))
    if not left or not right:
        return False
    if left.issubset(right) or right.issubset(left):
        return True
    return len(left & right) / len(left | right) >= 0.6


def load_or_create_case(
    manager: SessionManager,
    case: dict,
) -> tuple[str, ScientificReviewService, Path]:
    case_dir = OUTPUT_ROOT / case["id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    state_path = case_dir / "runtime_state.json"
    if state_path.exists():
        session_id = json.loads(state_path.read_text(encoding="utf-8"))["session_id"]
        return session_id, ScientificReviewService(manager), case_dir
    session = manager.create_session(case["question"], keywords=case["keywords"])
    session_id = session["session_id"]
    service = ScientificReviewService(manager)
    service.update_protocol(
        session_id,
        {
            "mode": case["mode"],
            "language": "zh-CN",
            "candidate_cap": 100,
            "sources": SOURCES,
            "languages": ["English"],
            "document_types": [
                "journal article",
                "conference paper",
                "preprint",
            ],
            "date_from": case["date_from"],
            "date_to": TODAY,
            "search_field_scope": ["title", "abstract", "keywords"],
            "inclusion_criteria": case["inclusion"],
            "exclusion_criteria": [
                "不直接回答研究问题",
                "错误的问题、方法、结局或文献类型",
                "重复版本",
                "信息不足或全文无法获得",
            ],
        },
    )
    protocol = service.confirm_protocol(session_id)
    write_json(
        state_path,
        {
            "session_id": session_id,
            "case_id": case["id"],
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "api_key_retained": False,
        },
    )
    write_json(case_dir / "protocol.json", protocol)
    return session_id, service, case_dir


def copy_methodology_artifacts(
    service: ScientificReviewService,
    session_id: str,
    case_dir: Path,
) -> None:
    mappings = {
        "search_queries.json": "search_ledger.json",
        "candidates.json": "candidate_records.json",
        "screening_decisions.json": "screening_ledger.json",
        "extractions.json": "evidence_cards.json",
        "appraisals.json": "study_appraisals.json",
        "synthesis_groups.json": "synthesis_groups.json",
        "claims.json": "claim_ledger.json",
    }
    for internal, external in mappings.items():
        value = service._read(session_id, internal, [])
        write_json(case_dir / external, value)
    write_json(case_dir / "methodology_audit.json", service.methodology_report(session_id))


def prepare_case(
    manager: SessionManager,
    case: dict,
) -> dict:
    session_id, service, case_dir = load_or_create_case(manager, case)
    prepared_path = case_dir / "preparation_summary.json"
    if prepared_path.exists():
        session = manager.load_session(session_id) or {}
        runs = session.get("search_runs") or []
        if runs and (runs[-1].get("queries") or []):
            service.reconcile_search_ledger(
                session_id,
                {"queries": runs[-1]["queries"]},
            )
            copy_methodology_artifacts(service, session_id, case_dir)
        return json.loads(prepared_path.read_text(encoding="utf-8"))
    plans = service._read(session_id, "search_queries.json", [])
    attempts = []
    registered_before = service.flow_counts(session_id)["unique_candidates"]
    for plan_index, plan in enumerate(plans, start=1):
        required_pages = int(plan.get("required_pages") or 1)
        for page_index in range(required_pages):
            print(
                f"[{case['id']}] search {plan_index}/{len(plans)} "
                f"{plan['source']} page {page_index + 1}/{required_pages}",
                flush=True,
            )
            rows, attempt = execute_search(plan, page_index, case["mode"])
            attempts.append(attempt)
            for row in rows:
                try:
                    service.register_candidate(
                        session_id,
                        row,
                        source_run_id=plan["search_query_id"],
                    )
                except ValueError as exc:
                    if "Candidate cap reached" not in str(exc):
                        raise
            if plan["source"] == "arxiv":
                time.sleep(2.5)
            else:
                time.sleep(0.4)
    service.reconcile_search_ledger(session_id, {"queries": attempts})
    flow = service.flow_counts(session_id)
    manager.save_search_run(
        session_id,
        {
            "run_id": f"live_{case['id']}_{dt.datetime.now().strftime('%H%M%S')}",
            "protocol_id": service.ensure_protocol(session_id)["protocol_id"],
            "sources": SOURCES,
            "queries": attempts,
            "new_candidates": flow["unique_candidates"] - registered_before,
            "unique_candidates": flow["unique_candidates"],
            "duplicates_removed": flow["duplicates_removed"],
            "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )
    candidates = service._read(session_id, "candidates.json", [])
    write_json(case_dir / "candidate_pool.json", sanitized_candidates(candidates))
    copy_methodology_artifacts(service, session_id, case_dir)
    summary = {
        "case_id": case["id"],
        "mode": case["mode"],
        "title": case["title"],
        "query_count": len(plans),
        "query_attempt_count": len(attempts),
        "queries_completed": service.flow_counts(session_id)["queries_completed"],
        "unique_candidates": len(candidates),
        "duplicates_removed": service.flow_counts(session_id)["duplicates_removed"],
        "source_failures": sum(not item["success"] for item in attempts),
        "known_relevant_recall": {
            "retrieved": sum(
                any(
                    title_matches(expected, candidate.get("title", ""))
                    for candidate in candidates
                )
                for expected in case.get("known_relevant_titles") or []
            ),
            "total": len(case.get("known_relevant_titles") or []),
        },
        "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "api_key_retained": False,
    }
    write_json(prepared_path, summary)
    return summary


def make_llm() -> TrialLLMClient:
    api_key = str(os.getenv("ZHIPU_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "ZHIPU_API_KEY is not available. Set it in the current terminal "
            "or the repository's gitignored .env before running --phase complete."
        )
    return TrialLLMClient(
        {
            "provider_id": "zhipu",
            "api_key": api_key,
            "base_url": BASE_URL,
            "chat_model": MODEL,
            "embedding_model": "",
            "language": "zh-CN",
        }
    )


def call_text(
    llm: LLMClient,
    system: str,
    prompt: str,
    *,
    max_tokens: int = 8000,
    thinking: bool = False,
) -> str:
    retry_deadline = time.monotonic() + float(
        os.getenv("TRIAL_RETRY_WINDOW_SECONDS", "900")
    )
    delay = 8.0
    while True:
        try:
            response = llm.client.chat.completions.create(
                model=llm.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
                extra_body={
                    "thinking": {
                        "type": "enabled" if thinking else "disabled"
                    }
                },
            )
            return str(response.choices[0].message.content or "").strip()
        except Exception as exc:
            retryable = (
                getattr(exc, "status_code", None) in {429, 500, 502, 503}
                or exc.__class__.__name__ in {"APITimeoutError", "APIConnectionError"}
            )
            remaining = retry_deadline - time.monotonic()
            if not retryable or remaining <= 0:
                raise
            time.sleep(min(delay, 60.0, remaining))
            delay = min(delay * 2, 60.0)


def call_json(
    llm: LLMClient,
    system: str,
    prompt: str,
    *,
    max_tokens: int = 8000,
) -> dict:
    raw = call_text(
        llm,
        system + " 只返回合法JSON对象，不要使用Markdown代码围栏。",
        prompt,
        max_tokens=max_tokens,
    )
    parsed = extract_json(raw)
    if isinstance(parsed, dict) and parsed:
        return parsed
    repaired = call_text(
        llm,
        "你是JSON格式修复器。只修复格式，不新增事实，只返回JSON对象。",
        raw,
        max_tokens=max_tokens,
    )
    parsed = extract_json(repaired)
    if not isinstance(parsed, dict) or not parsed:
        raise RuntimeError("Model did not return a parseable JSON object")
    return parsed


def title_abstract_screen(
    llm: LLMClient,
    case: dict,
    service: ScientificReviewService,
    session_id: str,
) -> None:
    if service._read(session_id, "title_screen_complete.json", {}):
        return
    candidates = service._read(session_id, "candidates.json", [])
    schema = {
        "decisions": [
            {
                "paper_id": "",
                "decision": "include|exclude|uncertain",
                "reason_code": "not_relevant|wrong_population_or_problem|wrong_method_or_intervention|wrong_outcome|wrong_document_type|insufficient_information|other",
                "reason": "",
                "criterion_judgements": [
                    {
                        "criterion": "",
                        "judgement": "met|not_met|uncertain",
                        "evidence": "",
                    }
                ],
                "confidence": 0.0,
            }
        ]
    }
    decided = set()
    for start in range(0, len(candidates), 8):
        batch = candidates[start : start + 8]
        catalog = [
            {
                "paper_id": item.get("paper_id"),
                "title": item.get("title"),
                "year": item.get("publication_year"),
                "abstract": str(item.get("abstract") or "")[:1400],
                "sources": item.get("sources"),
            }
            for item in batch
        ]
        print(
            f"[{case['id']}] title/abstract screening "
            f"{start + 1}-{start + len(batch)}/{len(candidates)}",
            flush=True,
        )
        result = call_json(
            llm,
            (
                "你是独立的高召回标题摘要筛选员。逐条应用协议标准，不得看到或猜测"
                "其他筛选者决定。调查/综述可用于分类背景，但不能替代一级实验证据。"
            ),
            f"""研究问题：{case['question']}
纳入标准：{json.dumps(case['inclusion'], ensure_ascii=False)}
排除标准：不相关、错误问题/方法/结局/文献类型、信息不足。

候选记录：
{json.dumps(catalog, ensure_ascii=False)}

必须为每条记录返回一个决定。信息不足但可能相关时用uncertain，禁止为了凑数量纳入。
返回结构：{json.dumps(schema, ensure_ascii=False)}""",
            max_tokens=4000,
        )
        valid = {str(item.get("paper_id")) for item in batch}
        for row in result.get("decisions") or []:
            paper_id = str(row.get("paper_id") or "")
            if paper_id not in valid or paper_id in decided:
                continue
            decision = str(row.get("decision") or "uncertain")
            if decision not in {"include", "exclude", "uncertain"}:
                decision = "uncertain"
            reason_code = str(row.get("reason_code") or "other")
            if decision == "exclude" and reason_code not in {
                "not_relevant",
                "wrong_population_or_problem",
                "wrong_method_or_intervention",
                "wrong_outcome",
                "wrong_document_type",
                "insufficient_information",
                "other",
            }:
                reason_code = "other"
            service.record_screening(
                session_id,
                paper_id=paper_id,
                stage="title_abstract",
                decision=decision,
                reason_code=reason_code if decision == "exclude" else None,
                reason=str(row.get("reason") or ""),
                criterion_judgements=row.get("criterion_judgements") or [],
                confidence=row.get("confidence"),
                reviewer="ai",
                actor_type="ai",
                actor_id="title_abstract_model",
                model_version=llm.model,
                blinded_to_peer=True,
            )
            decided.add(paper_id)
    for candidate in candidates:
        paper_id = str(candidate.get("paper_id") or "")
        if paper_id in decided:
            continue
        service.record_screening(
            session_id,
            paper_id=paper_id,
            stage="title_abstract",
            decision="uncertain",
            reason="Model response omitted this candidate; manual review required.",
            confidence=0.0,
            reviewer="ai",
            actor_type="ai",
            actor_id="title_abstract_model",
            model_version=llm.model,
            blinded_to_peer=True,
        )
    service._write(
        session_id,
        "title_screen_complete.json",
        {"completed_at": dt.datetime.now(dt.timezone.utc).isoformat()},
    )


def page_balanced_text(chunks: list[dict], max_chars: int = 18000) -> str:
    by_page: dict[int, list[str]] = {}
    for chunk in chunks:
        page = int(chunk.get("page") or 0)
        by_page.setdefault(page, []).append(str(chunk.get("text") or ""))
    sections = []
    for page in sorted(by_page):
        page_text = re.sub(r"\s+", " ", " ".join(by_page[page])).strip()
        if page_text:
            sections.append(f"[PDF page {page}]\n{page_text[:2400]}")
    joined = "\n\n".join(sections)
    if len(joined) <= max_chars:
        return joined
    third = max_chars // 3
    middle = len(joined) // 2
    return (
        joined[:third]
        + "\n\n[...middle sample...]\n\n"
        + joined[middle - third // 2 : middle + third // 2]
        + "\n\n[...ending sample...]\n\n"
        + joined[-third:]
    )


def download_and_extract(
    llm: LLMClient,
    case: dict,
    manager: SessionManager,
    service: ScientificReviewService,
    session_id: str,
    case_dir: Path,
) -> None:
    if service._read(session_id, "evidence_extraction_complete.json", {}):
        return
    resolved = service._resolved_screening_decisions(session_id)
    candidates = service._read(session_id, "candidates.json", [])
    title_included = [
        item
        for item in candidates
        if (
            resolved.get(
                (str(item.get("candidate_id") or item.get("paper_id")), "title_abstract"),
                {},
            ).get("decision") == "include"
        )
    ]
    title_included.sort(
        key=lambda item: (
            0 if item.get("arxiv_id") else 1,
            -int(item.get("cited_by_count") or 0),
            str(item.get("title") or ""),
        )
    )
    temp_dir = case_dir / ".temporary_sources"
    temp_dir.mkdir(exist_ok=True)
    completed_extractions = {
        item.get("paper_id")
        for item in service._read(session_id, "extractions.json", [])
    }
    extraction_failures = []
    try:
        for index, candidate in enumerate(title_included, start=1):
            paper_id = str(candidate.get("paper_id") or "")
            if paper_id in completed_extractions:
                continue
            arxiv_id = str(candidate.get("arxiv_id") or "")
            if not arxiv_id:
                service.record_screening(
                    session_id,
                    paper_id=paper_id,
                    stage="full_text",
                    decision="exclude",
                    reason_code="full_text_unavailable",
                    reason="No retrievable open full-text identifier was recorded.",
                    reviewer="ai",
                    actor_type="ai",
                    actor_id="fulltext_retrieval",
                    model_version=llm.model,
                    blinded_to_peer=True,
                )
                continue
            print(
                f"[{case['id']}] full text {index}/{len(title_included)} {arxiv_id}",
                flush=True,
            )
            result = ArxivDownloadPdfTool(str(temp_dir)).execute(paper_id=arxiv_id)
            pdf_path = temp_dir / f"{arxiv_id}.pdf"
            if not pdf_path.exists():
                service.record_screening(
                    session_id,
                    paper_id=paper_id,
                    stage="full_text",
                    decision="exclude",
                    reason_code="full_text_unavailable",
                    reason=str(result)[:300],
                    reviewer="ai",
                    actor_type="ai",
                    actor_id="fulltext_retrieval",
                    model_version=llm.model,
                    blinded_to_peer=True,
                )
                continue
            chunks = extract_full_text_from_pdf(str(pdf_path), case["id"], paper_id)
            if not chunks:
                service.record_screening(
                    session_id,
                    paper_id=paper_id,
                    stage="full_text",
                    decision="exclude",
                    reason_code="insufficient_information",
                    reason="PDF was downloaded but text extraction returned no usable content.",
                    reviewer="ai",
                    actor_type="ai",
                    actor_id="fulltext_retrieval",
                    model_version=llm.model,
                    blinded_to_peer=True,
                )
                pdf_path.unlink(missing_ok=True)
                continue
            note = page_balanced_text(chunks)
            paper = {
                **candidate,
                "paper_id": paper_id,
                "status": "pending",
                "evidence_basis": "full_text",
                "pdf_status": "available",
                "notes": note,
                "pages_extracted": len({chunk.get("page") for chunk in chunks}),
            }
            manager.add_paper(session_id, paper)
            try:
                extraction, appraisal = _extract_scientific_evidence(
                    llm,
                    topic=case["question"],
                    paper=paper,
                    notes=note,
                    appraisal_profile=(
                        "computer_ai" if case["mode"] == "technical" else "general"
                    ),
                )
            except Exception as exc:
                failure = {
                    "paper_id": paper_id,
                    "arxiv_id": arxiv_id,
                    "error": str(exc)[:500],
                    "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "retryable": True,
                }
                extraction_failures.append(failure)
                service.record_screening(
                    session_id,
                    paper_id=paper_id,
                    stage="full_text",
                    decision="uncertain",
                    reason="Full text was retrieved but structured evidence extraction failed; human review or retry is required.",
                    reviewer="ai",
                    actor_type="ai",
                    actor_id="evidence_extraction",
                    model_version=llm.model,
                    blinded_to_peer=True,
                )
                pdf_path.unlink(missing_ok=True)
                continue
            service.save_extraction(session_id, paper_id, extraction)
            service.save_appraisal(session_id, paper_id, appraisal)
            completed_extractions.add(paper_id)
            pdf_path.unlink(missing_ok=True)
            time.sleep(0.8)
    finally:
        if temp_dir.exists():
            for path in temp_dir.iterdir():
                if path.is_file():
                    path.unlink(missing_ok=True)
            temp_dir.rmdir()
    write_json(case_dir / "extraction_failures.json", extraction_failures)
    if not extraction_failures:
        service._write(
            session_id,
            "evidence_extraction_complete.json",
            {"completed_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        )


def fulltext_screen(
    llm: LLMClient,
    case: dict,
    manager: SessionManager,
    service: ScientificReviewService,
    session_id: str,
) -> list[str]:
    snapshot = service.latest_inclusion_snapshot(session_id)
    if snapshot:
        return list(snapshot.get("paper_ids") or [])
    extractions = service._read(session_id, "extractions.json", [])
    decisions = []
    schema = {
        "decisions": [
            {
                "paper_id": "",
                "decision": "include|exclude|uncertain",
                "reason_code": "not_relevant|wrong_population_or_problem|wrong_method_or_intervention|wrong_outcome|wrong_document_type|insufficient_information|other",
                "reason": "",
                "confidence": 0.0,
            }
        ]
    }
    for start in range(0, len(extractions), 8):
        batch = extractions[start : start + 8]
        evidence = [
            {
                "paper_id": item.get("paper_id"),
                "study_or_article_type": item.get("study_or_article_type"),
                "study_design": item.get("study_design"),
                "intervention_or_method": item.get("intervention_or_method"),
                "main_results": item.get("main_results"),
                "limitations": item.get("limitations"),
                "evidence_basis": item.get("evidence_basis"),
            }
            for item in batch
        ]
        print(
            f"[{case['id']}] full-text screening "
            f"{start + 1}-{start + len(batch)}/{len(extractions)}",
            flush=True,
        )
        result = call_json(
            llm,
            (
                "你是独立全文筛选员。只能依据结构化全文提取逐条应用协议，"
                "不能为了达到目标篇数而纳入。二级综述可作为分类背景，但须明确证据层级。"
            ),
            f"""研究问题：{case['question']}
纳入标准：{json.dumps(case['inclusion'], ensure_ascii=False)}
全文证据摘要：{json.dumps(evidence, ensure_ascii=False)}
必须逐条返回决定。返回结构：{json.dumps(schema, ensure_ascii=False)}""",
            max_tokens=7000,
        )
        valid = {str(item.get("paper_id")) for item in batch}
        for row in result.get("decisions") or []:
            paper_id = str(row.get("paper_id") or "")
            if paper_id not in valid:
                continue
            decision = str(row.get("decision") or "uncertain")
            if decision not in {"include", "exclude", "uncertain"}:
                decision = "uncertain"
            reason_code = str(row.get("reason_code") or "other")
            service.record_screening(
                session_id,
                paper_id=paper_id,
                stage="full_text",
                decision=decision,
                reason_code=reason_code if decision == "exclude" else None,
                reason=str(row.get("reason") or ""),
                confidence=row.get("confidence"),
                reviewer="ai",
                actor_type="ai",
                actor_id="fulltext_screen_model",
                model_version=llm.model,
                blinded_to_peer=True,
            )
            decisions.append((paper_id, decision))
    decided_ids = {paper_id for paper_id, _ in decisions}
    for extraction in extractions:
        paper_id = str(extraction.get("paper_id") or "")
        if paper_id in decided_ids:
            continue
        service.record_screening(
            session_id,
            paper_id=paper_id,
            stage="full_text",
            decision="uncertain",
            reason="Model response omitted this full-text record.",
            confidence=0.0,
            reviewer="ai",
            actor_type="ai",
            actor_id="fulltext_screen_model",
            model_version=llm.model,
            blinded_to_peer=True,
        )
    resolved = service._resolved_screening_decisions(session_id)
    included_ids = []
    for candidate in service._read(session_id, "candidates.json", []):
        paper_id = str(candidate.get("paper_id") or "")
        outcome = resolved.get(
            (str(candidate.get("candidate_id") or paper_id), "full_text"),
            {},
        ).get("decision")
        if outcome == "include":
            included_ids.append(paper_id)
            manager.update_paper_status(session_id, paper_id, "accepted")
        elif outcome == "exclude" and any(
            paper.get("paper_id") == paper_id
            for paper in manager.get_papers(session_id)
        ):
            manager.update_paper_status(session_id, paper_id, "rejected")
    service.confirm_inclusion_snapshot(
        session_id,
        included_ids,
        confirmed_by="ai_orchestrator",
        record_decisions=False,
    )
    return included_ids


def review_prompt(
    case: dict,
    methodology: dict,
    extractions: list[dict],
    appraisals: list[dict],
    synthesis: list[dict],
) -> str:
    preset = REVIEW_PRESETS[case["mode"]]["content"]
    return f"""请撰写中文学术证据综述正文。

标题：{case['title']}
研究问题：{case['question']}
模式：{case['mode']}

方法学账本：
{json.dumps(methodology, ensure_ascii=False, indent=2)}

结构化证据卡：
{json.dumps(extractions, ensure_ascii=False, indent=2)}

质量评价：
{json.dumps(appraisals, ensure_ascii=False, indent=2)}

综合分组：
{json.dumps(synthesis, ensure_ascii=False, indent=2)}

写作Skill：
{preset}

强制要求：
1. 只写引言、结果/证据综合、讨论与结论；方法、表格、概念图和参考文献由系统确定性插入。
2. 使用[P#]引用，P编号对应给定证据卡顺序，不得创造来源。
3. 按主题跨研究综合，固定回答为何有效、何时失效、证据来自何种任务、工程或实践代价。
4. 二级证据只用于背景、分类和研究版图；数字、性能、成本和实践建议必须由一级证据支持。
5. 数字缺少数据集、模型、基线、指标、变化类型或证据位置时，只能写“原文报告但上下文不完整”。
6. “应采用、优先采用、普遍有效”等强措辞必须有多个可比一级研究，否则改成条件性表述。
7. 不把自适应系统自动称为Agent；只有目标、状态、动作与反馈循环均满足时才使用该词。
8. 不引用超过15个连续原文词，不补造缺失信息。
9. 目标正文6000至9000中文字符，直接输出Markdown。"""


def generate_review(
    llm: LLMClient,
    case: dict,
    manager: SessionManager,
    service: ScientificReviewService,
    session_id: str,
    case_dir: Path,
    included_ids: list[str],
) -> dict:
    review_path = case_dir / "formal_review.md"
    if review_path.exists():
        return json.loads((case_dir / "final_summary.json").read_text(encoding="utf-8"))
    papers_by_id = {
        str(item.get("paper_id")): item
        for item in manager.get_papers(session_id)
    }
    papers = [papers_by_id[paper_id] for paper_id in included_ids if paper_id in papers_by_id]
    for index, paper in enumerate(papers, start=1):
        paper["citation_id"] = f"P{index}"
    all_extractions = service._read(session_id, "extractions.json", [])
    all_appraisals = service._read(session_id, "appraisals.json", [])
    extractions = [
        item for paper_id in included_ids
        for item in all_extractions if item.get("paper_id") == paper_id
    ]
    appraisals = [
        item for paper_id in included_ids
        for item in all_appraisals if item.get("paper_id") == paper_id
    ]
    synthesis = service.build_synthesis_groups(session_id, included_ids)
    gate = service.quality_gate(session_id, requested_paper_ids=included_ids)
    methodology = service.methodology_report(session_id)
    print(f"[{case['id']}] writing review from {len(papers)} included records", flush=True)
    draft_path = case_dir / "draft_before_deterministic_sections.md"
    draft = (
        draft_path.read_text(encoding="utf-8")
        if draft_path.exists()
        else call_text(
        llm,
        (
            "你是严谨的高级学术综述作者。结构化证据是唯一事实来源；"
            "禁止先写结论再补引用。"
        ),
        review_prompt(case, methodology, extractions, appraisals, synthesis),
        max_tokens=9000,
            thinking=False,
        )
    )
    if not draft_path.exists():
        write_text(draft_path, draft)
    review = service.inject_deterministic_review_sections(
        session_id,
        draft,
        papers,
        "zh-CN",
    )
    review = service.enforce_review_label(session_id, review, gate, "zh-CN")
    claim_audit = service.audit_review_claims(session_id, review, papers)
    if not claim_audit.get("passed") and os.getenv("TRIAL_SKIP_CLAIM_REPAIR") != "1":
        print(f"[{case['id']}] repairing claim audit", flush=True)
        repaired = call_text(
            llm,
            (
                "你是学术证据与引用审计修订器。只修复列出的问题，"
                "不得添加证据卡中不存在的事实。"
            ),
            f"""研究问题：{case['question']}
证据卡：{json.dumps(extractions, ensure_ascii=False)}
审计问题：{json.dumps(claim_audit, ensure_ascii=False)}
当前草稿：{review}

返回完整Markdown。保留主题综合，删除或降级上下文不完整数字、二级证据滥用、
无条件建议、内部矛盾和不满足定义的Agent术语。方法、结构化表格和参考文献无需保留，
系统将重新确定性插入。""",
            max_tokens=9000,
        )
        review = service.inject_deterministic_review_sections(
            session_id,
            repaired,
            papers,
            "zh-CN",
        )
        review = service.enforce_review_label(session_id, review, gate, "zh-CN")
        claim_audit = service.audit_review_claims(session_id, review, papers)
    write_text(review_path, review)
    write_text(
        case_dir / "formal_review.html",
        markdown_to_html(review, case["title"]),
    )
    (case_dir / "formal_review.docx").write_bytes(_docx_bytes(review))
    (case_dir / "formal_review.pdf").write_bytes(_pdf_bytes(review))
    manager.save_review(
        session_id,
        review,
        referenced_papers=included_ids,
    )
    service.write_review_version(session_id, review, gate)
    copy_methodology_artifacts(service, session_id, case_dir)
    write_json(case_dir / "quality_gate.json", gate)
    write_json(case_dir / "claim_audit.json", claim_audit)
    summary = {
        "case_id": case["id"],
        "mode": case["mode"],
        "title": case["title"],
        "model": llm.model,
        "candidate_count": service.flow_counts(session_id)["unique_candidates"],
        "duplicate_count": service.flow_counts(session_id)["duplicates_removed"],
        "title_abstract_screened": service.flow_counts(session_id)["title_abstract_screened"],
        "full_text_assessed": service.flow_counts(session_id)["full_text_assessed"],
        "included_count": len(included_ids),
        "primary_evidence_count": sum(
            item.get("evidence_level") == "primary" for item in extractions
        ),
        "secondary_evidence_count": sum(
            item.get("evidence_level") == "secondary" for item in extractions
        ),
        "quality_gate_ok": gate.get("ok"),
        "quality_gate_label": gate.get("output_label"),
        "quality_gate_blockers": gate.get("blockers"),
        "quality_gate_warnings": gate.get("warnings"),
        "claim_audit_passed": claim_audit.get("passed"),
        "review_characters": len(review),
        "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "api_key_retained": False,
        "source_pdfs_retained": False,
    }
    write_json(case_dir / "final_summary.json", summary)
    return summary


def complete_case(
    llm: LLMClient,
    manager: SessionManager,
    case: dict,
) -> dict:
    session_id, service, case_dir = load_or_create_case(manager, case)
    if not (case_dir / "preparation_summary.json").exists():
        prepare_case(manager, case)
    title_abstract_screen(llm, case, service, session_id)
    copy_methodology_artifacts(service, session_id, case_dir)
    download_and_extract(llm, case, manager, service, session_id, case_dir)
    included_ids = fulltext_screen(llm, case, manager, service, session_id)
    copy_methodology_artifacts(service, session_id, case_dir)
    if len(included_ids) < 10:
        write_json(
            case_dir / "insufficient_inclusion_warning.json",
            {
                "included_count": len(included_ids),
                "target": 10,
                "message": (
                    "The protocol produced fewer than ten eligible full texts. "
                    "The workflow did not override screening decisions to meet a quota."
                ),
            },
        )
    return generate_review(
        llm,
        case,
        manager,
        service,
        session_id,
        case_dir,
        included_ids,
    )


def comparative_report(summaries: list[dict]) -> str:
    rows = [
        "| 案例 | 模式 | 候选 | 标题摘要筛选 | 全文评估 | 最终纳入 | 一级/二级证据 | 基础门禁 | Claim审计 |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in summaries:
        rows.append(
            f"| {item['title']} | {item['mode']} | {item['candidate_count']} | "
            f"{item['title_abstract_screened']} | {item['full_text_assessed']} | "
            f"{item['included_count']} | {item['primary_evidence_count']}/"
            f"{item['secondary_evidence_count']} | "
            f"{'通过' if item['quality_gate_ok'] else '未通过'} | "
            f"{'通过' if item['claim_audit_passed'] else '未通过'} |"
        )
    return """# 方法学深度升级真实案例横向报告

本轮使用真实学术检索接口、真实开放全文与智谱模型，测试协议、检索账本、去重、
AI标题摘要筛选、全文证据提取、质量评价、综合写作、Claim Ledger和八项门禁。
API Key与源PDF均未保留。

## 结果概览

""" + "\n".join(rows) + """

## 判读原则

- 纳入数量不是成功条件；若协议只产生少量合格全文，不会为了达到配额改写筛选决定。
- 技术综述必须完成七项计算机研究质量评价领域，否则基础门禁失败。
- 二级综述只能用于背景和分类；性能、成本与实践建议必须由一级研究支持。
- Claim审计未通过时仍保留草稿和问题清单，输出不得冒充完成版或系统综述。
- 三个案例均属于投稿前研究底稿，需要研究者复核。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("prepare", "complete", "all"),
        default="all",
    )
    parser.add_argument(
        "--case",
        choices=[item["id"] for item in CASES],
        action="append",
    )
    args = parser.parse_args()
    selected_cases = [
        item for item in CASES if not args.case or item["id"] in args.case
    ]
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    manager = SessionManager(str(RUNTIME_ROOT))
    preparation = []
    if args.phase in {"prepare", "all"}:
        for case in selected_cases:
            preparation.append(prepare_case(manager, case))
        write_json(OUTPUT_ROOT / "preparation_summary.json", {"cases": preparation})
    if args.phase == "prepare":
        return 0
    llm = make_llm()
    summaries = []
    for case in selected_cases:
        summaries.append(complete_case(llm, manager, case))
    write_json(OUTPUT_ROOT / "trial_summary.json", {"cases": summaries})
    write_text(OUTPUT_ROOT / "COMPARATIVE_REPORT.md", comparative_report(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
