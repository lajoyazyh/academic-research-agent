"""Run four 12-paper GLM review trials across two review modes.

The API key is read from a no-echo prompt and never persisted. Source PDFs are
temporary; only metadata, structured evidence, synthesis, reviews and audits
are retained. Every stage is checkpointed so free-model congestion can be
resumed without repeating completed work.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "scripts"))

from llms.client import LLMClient  # noqa: E402
from main import _normalize_citation_markers, assess_review_quality  # noqa: E402
from prompts.review_skills import REVIEW_PRESETS  # noqa: E402
from run_glm_formal_review_trial import (  # noqa: E402
    BASE_URL,
    MODEL,
    _call,
    _call_json,
    _clean_markdown,
    _page_balanced_text,
    _write,
)
from tools.pdf_tools import ArxivDownloadPdfTool, extract_full_text_from_pdf  # noqa: E402


OUTPUT_ROOT = ROOT / "artifacts" / "glm-multi-topic-12plus-review-trials-2026-07-31"
TARGET_INCLUDED = 12

CASES = [
    {
        "id": "technical-peft",
        "mode": "technical",
        "title": "参数高效微调方法的机制、证据与工程权衡",
        "question": (
            "参数高效微调方法在可训练参数、结构改动、任务适用性、性能证据、"
            "训练与推理成本以及复现性方面形成了怎样的技术谱系？"
        ),
        "queries": [
            "parameter efficient fine tuning language models LoRA adapter prefix prompt",
            "low rank adaptation quantized LoRA adaptive rank fine tuning",
            "prompt tuning prefix tuning adapters bias tuning transformers",
        ],
    },
    {
        "id": "technical-rag",
        "mode": "technical",
        "title": "检索增强生成的架构、评价与可靠性技术综述",
        "question": (
            "检索增强生成系统在检索器、生成器耦合、训练方式、评价框架、"
            "事实可靠性与计算成本方面有哪些主要技术路线和证据边界？"
        ),
        "queries": [
            "retrieval augmented generation language models",
            "RAG evaluation factuality reliability benchmark",
            "self retrieval corrective retrieval augmented generation",
        ],
    },
    {
        "id": "scoping-hallucination",
        "mode": "scoping",
        "title": "大语言模型幻觉检测与缓解研究的范围综述",
        "question": (
            "大语言模型幻觉研究如何定义问题、构建评价、检测错误并实施缓解，"
            "现有研究覆盖了哪些场景，又留下哪些证据空白？"
        ),
        "queries": [
            "large language model hallucination survey detection mitigation",
            "factuality evaluation hallucination language models",
            "hallucination benchmark attribution faithfulness LLM",
        ],
    },
    {
        "id": "scoping-agent-evaluation",
        "mode": "scoping",
        "title": "大语言模型自主 Agent 评测研究的范围综述",
        "question": (
            "LLM Agent 的规划、工具使用、记忆、协作与长期任务能力如何被评价，"
            "现有基准的任务设计、指标、可复现性和有效性风险是什么？"
        ),
        "queries": [
            "large language model autonomous agents evaluation benchmark",
            "LLM agent planning tool use benchmark evaluation",
            "language model agents long horizon tasks benchmark",
        ],
    },
]


def _provider() -> LLMClient:
    api_key = getpass.getpass("")
    if not api_key.strip():
        raise SystemExit("API key is required")
    client = LLMClient({
        "provider_id": "zhipu",
        "api_key": api_key,
        "base_url": BASE_URL,
        "chat_model": MODEL,
        "embedding_model": "",
        "language": "zh-CN",
    })
    api_key = ""
    return client


def _fingerprint(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(title).casefold()))


def _short_excerpt(text: str, words: int = 18) -> str:
    return " ".join(re.sub(r"\s+", " ", str(text or "")).split()[:words])


def _openalex_abstract(inverted_index: dict | None) -> str:
    positioned: list[tuple[int, str]] = []
    for word, positions in (inverted_index or {}).items():
        for position in positions:
            positioned.append((int(position), str(word)))
    return " ".join(word for _, word in sorted(positioned))


def _arxiv_id_from_work(work: dict) -> str:
    values = list((work.get("ids") or {}).values())
    for location in work.get("locations") or []:
        values.extend([
            location.get("landing_page_url"),
            location.get("pdf_url"),
        ])
    pattern = re.compile(
        r"(?:arxiv(?:\.org/(?:abs|pdf)/|\.))"
        r"([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})",
        re.IGNORECASE,
    )
    for value in values:
        match = pattern.search(str(value or ""))
        if match:
            return re.sub(r"v\d+$", "", match.group(1))
    return ""


def _preferred_location(work: dict) -> dict:
    locations = [
        location
        for location in (work.get("locations") or [])
        if location.get("pdf_url")
    ]
    for location in locations:
        if "arxiv.org/pdf/" in str(location.get("pdf_url")):
            return location
    return work.get("best_oa_location") or (locations[0] if locations else {})


def _search_openalex(query: str, per_page: int = 20) -> list[dict]:
    params = {
        "search": query,
        "filter": "has_fulltext:true",
        "per-page": str(per_page),
        "select": (
            "id,doi,title,publication_year,authorships,locations,"
            "best_oa_location,abstract_inverted_index,ids,cited_by_count"
        ),
    }
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AcademicResearchAgent/1.0 (mailto:research@example.com)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    records = []
    for work in payload.get("results") or []:
        location = _preferred_location(work)
        pdf_url = str(location.get("pdf_url") or "")
        if not pdf_url:
            continue
        openalex_id = str(work.get("id") or "").rsplit("/", 1)[-1]
        arxiv_id = _arxiv_id_from_work(work)
        authors = [
            str((authorship.get("author") or {}).get("display_name") or "")
            for authorship in (work.get("authorships") or [])
        ]
        records.append({
            "paper_id": arxiv_id or openalex_id,
            "arxiv_id": arxiv_id,
            "openalex_id": openalex_id,
            "doi": work.get("doi"),
            "title": work.get("title"),
            "authors": ", ".join(author for author in authors if author),
            "publication_year": work.get("publication_year"),
            "abstract": _openalex_abstract(work.get("abstract_inverted_index")),
            "source_url": (
                location.get("landing_page_url")
                or work.get("doi")
                or work.get("id")
            ),
            "pdf_url": pdf_url,
            "cited_by_count": work.get("cited_by_count"),
            "discovery_source": "openalex",
        })
    return records


def _search(case: dict) -> tuple[list[dict], list[dict]]:
    candidates: list[dict] = []
    ledger = []
    for query in case["queries"]:
        parsed: list[dict] = []
        error = ""
        for attempt in range(3):
            try:
                parsed = _search_openalex(query)
                if parsed:
                    break
            except Exception as exc:
                error = str(exc)[:500]
            time.sleep(6 * (attempt + 1))
        ledger.append({
            "source": "openalex",
            "query": query,
            "success": bool(parsed),
            "result_count": len(parsed),
            "error": None if parsed else error,
        })
        candidates.extend(parsed)
        time.sleep(3)

    unique = {}
    for item in candidates:
        arxiv_id = re.sub(r"v\d+$", "", str(item.get("arxiv_id") or ""))
        doi = str(item.get("doi") or "").casefold().removeprefix("https://doi.org/")
        # Title is deliberately the primary key here so the journal version
        # and arXiv preprint of the same work do not survive as two studies.
        title_key = _fingerprint(item.get("title", ""))
        key = title_key or doi or arxiv_id
        if not key:
            continue
        normalized = {
            **item,
            "paper_id": arxiv_id or item.get("openalex_id") or item.get("paper_id"),
            "arxiv_id": arxiv_id,
            "source_url": (
                f"https://arxiv.org/abs/{arxiv_id}"
                if arxiv_id
                else item.get("source_url")
            ),
        }
        current = unique.get(key)
        if current is None or len(normalized.get("abstract", "")) > len(current.get("abstract", "")):
            unique[key] = normalized
    return list(unique.values()), ledger


def _select(llm: LLMClient, case: dict, candidates: list[dict]) -> dict:
    catalog = [
        {
            "paper_id": item.get("paper_id"),
            "title": item.get("title"),
            "authors": item.get("authors"),
            "year": item.get("publication_year"),
            "abstract": str(item.get("abstract") or "")[:2200],
        }
        for item in candidates
    ]
    schema = {
        "ranked": [
            {
                "paper_id": "",
                "decision": "include|reserve|exclude",
                "reason": "",
                "coverage_role": "",
                "confidence": 0.0,
            }
        ],
        "selection_rationale": "",
        "anticipated_gaps": [],
    }
    result = _call_json(
        llm,
        (
            "你是文献综述标题摘要筛选员。以高召回为先，同时确保最终集合覆盖问题的不同子主题。"
            "只能选择候选目录中真实存在的 paper_id。"
        ),
        f"""综述模式：{case['mode']}
研究问题：{case['question']}
目标：排名至少 18 条候选，以便最终获得至少 {TARGET_INCLUDED} 篇可读取全文。

候选目录：
{json.dumps(catalog, ensure_ascii=False, indent=2)}

返回 JSON：
{json.dumps(schema, ensure_ascii=False, indent=2)}

筛选要求：
1. technical 模式覆盖奠基方法、重要改进、评价/复现与效率研究。
2. scoping 模式覆盖定义、分类、评价、应用场景和方法学批评，不只选性能论文。
3. 综述/调查论文可以用于分类框架，但不能替代原始研究证据。
4. 排除只共享宽泛术语、与问题无直接关系的记录。
""",
        thinking=False,
        max_tokens=6500,
    )
    valid = {item.get("paper_id"): item for item in candidates}
    ranked = []
    seen = set()
    for row in result.get("ranked") or []:
        paper_id = str(row.get("paper_id") or "")
        if paper_id not in valid or paper_id in seen:
            continue
        seen.add(paper_id)
        ranked.append({**valid[paper_id], "screening": row})
    # Preserve recall if the model returned too few rows.
    for item in candidates:
        paper_id = item.get("paper_id")
        if paper_id not in seen:
            ranked.append({
                **item,
                "screening": {
                    "paper_id": paper_id,
                    "decision": "reserve",
                    "reason": "Deterministic reserve after model ranking.",
                    "coverage_role": "reserve",
                    "confidence": 0.3,
                },
            })
    return {
        "ranked": ranked,
        "selection_rationale": result.get("selection_rationale"),
        "anticipated_gaps": result.get("anticipated_gaps") or [],
    }


def _download_selected(
    case_dir: Path,
    ranking: dict,
    case_id: str,
) -> tuple[list[dict], dict[str, str]]:
    temp_dir = case_dir / ".temporary_sources"
    shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True)
    selected = []
    full_texts = {}
    attempts = []
    try:
        for item in ranking["ranked"]:
            if len(selected) >= TARGET_INCLUDED:
                break
            if item.get("screening", {}).get("decision") == "exclude":
                continue
            paper_id = str(item.get("paper_id") or "")
            arxiv_id = str(item.get("arxiv_id") or "")
            pdf_url = str(item.get("pdf_url") or "")
            download_target = arxiv_id or pdf_url
            if not download_target:
                attempts.append({
                    "paper_id": paper_id,
                    "success": False,
                    "message": "No full-text download URL",
                })
                continue
            result = ArxivDownloadPdfTool(str(temp_dir)).execute(
                paper_id=download_target
            )
            download_name = (
                arxiv_id
                if arxiv_id
                else "paper_" + hashlib.md5(pdf_url.encode("utf-8")).hexdigest()[:8]
            )
            pdf_path = temp_dir / f"{download_name}.pdf"
            if not pdf_path.exists():
                attempts.append({"paper_id": paper_id, "success": False, "message": result[:200]})
                time.sleep(2)
                continue
            chunks = extract_full_text_from_pdf(str(pdf_path), case_id, paper_id)
            if not chunks:
                attempts.append({"paper_id": paper_id, "success": False, "message": "PDF text extraction failed"})
                continue
            citation_id = f"P{len(selected) + 1}"
            selected_item = {
                "citation_id": citation_id,
                "paper_id": paper_id,
                "arxiv_id": arxiv_id or None,
                "openalex_id": item.get("openalex_id"),
                "doi": item.get("doi"),
                "pdf_url": pdf_url,
                "title": item.get("title"),
                "authors": item.get("authors"),
                "year": str(item.get("publication_year") or "")[:4],
                "url": item.get("source_url") or pdf_url,
                "screening": item.get("screening"),
                "evidence_basis": "full_text",
                "pages_extracted": len({chunk.get("page") for chunk in chunks}),
                "retained_source_document": False,
            }
            selected.append(selected_item)
            full_texts[citation_id] = _page_balanced_text(chunks, max_chars=38000)
            attempts.append({"paper_id": paper_id, "success": True, "citation_id": citation_id})
            time.sleep(2)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    if len(selected) < TARGET_INCLUDED:
        raise RuntimeError(
            f"{case_id} only obtained {len(selected)}/{TARGET_INCLUDED} full texts"
        )
    return selected, {"texts": full_texts, "attempts": attempts}


def _extract_batch(
    llm: LLMClient,
    case: dict,
    papers: list[dict],
    full_texts: dict[str, str],
) -> list[dict]:
    payload = [
        {
            "metadata": paper,
            "full_text": full_texts[paper["citation_id"]],
        }
        for paper in papers
    ]
    schema = {
        "papers": [
            {
                "citation_id": "P1",
                "study_or_article_type": "",
                "research_objective": "",
                "method_or_framework": "",
                "evaluation_scope": {
                    "models_or_population": [],
                    "tasks_or_contexts": [],
                    "datasets": [],
                    "baselines": [],
                    "metrics": [],
                },
                "main_findings": [
                    {
                        "finding": "",
                        "support_type": "reported_result|author_claim|reviewer_inference",
                        "page": None,
                    }
                ],
                "efficiency_or_resource_evidence": [],
                "reproducibility": {
                    "code_available": None,
                    "data_available": None,
                    "variance_or_significance": None,
                    "ablation_or_sensitivity": None,
                    "implementation_detail": "adequate|partial|unclear",
                },
                "limitations": [],
                "validity_risks": [],
                "evidence_strength": "low|moderate|high",
                "uncertainties": [],
            }
        ]
    }
    result = _call_json(
        llm,
        (
            "你是保守的全文证据提取与研究评价引擎。逐篇独立提取，"
            "不得把一篇论文的信息迁移到另一篇。"
        ),
        f"""综述模式：{case['mode']}
研究问题：{case['question']}

论文全文批次：
{json.dumps(payload, ensure_ascii=False)}

返回：
{json.dumps(schema, ensure_ascii=False, indent=2)}

规则：
1. 只能使用所给全文；缺失信息用 null 或 []。
2. 数值、数据集、指标和结论必须记录 PDF 页码。
3. 区分作者主张、报告结果和审稿推断。
4. code_available 未在全文确认时必须为 null。
5. 不保存或返回超过 15 个连续原文词的引文。
6. technical 模式评价基线公平性、统计充分性、复现与计算成本。
7. scoping 模式提取概念定义、研究类型、评价场景和范围边界。
""",
        thinking=False,
        max_tokens=8500,
    )
    by_id = {paper["citation_id"]: paper for paper in papers}
    rows = []
    for row in result.get("papers") or []:
        citation_id = str(row.get("citation_id") or "")
        if citation_id not in by_id:
            continue
        rows.append({
            **row,
            "citation_id": citation_id,
            "paper_id": by_id[citation_id]["paper_id"],
            "title": by_id[citation_id]["title"],
            "evidence_basis": "full_text",
            "review_status": "ai_draft_requires_human",
        })
    missing = set(by_id) - {row["citation_id"] for row in rows}
    if missing:
        raise RuntimeError(f"Missing evidence cards: {sorted(missing)}")
    return rows


def _synthesize(llm: LLMClient, case: dict, cards: list[dict]) -> dict:
    schema = {
        "review_mode": case["mode"],
        "taxonomy_or_method_families": [],
        "synthesis_groups": [
            {
                "name": "",
                "question_answered": "",
                "included_sources": ["P1"],
                "consensus": [],
                "disagreements": [],
                "heterogeneity": [],
                "boundary": "",
            }
        ],
        "cross_study_comparability": [],
        "evidence_gaps": [],
        "claims": [
            {
                "claim_id": "C1",
                "claim": "",
                "support": ["P1"],
                "strength": "low|moderate|high",
                "boundary": "",
            }
        ],
        "recommended_outline": [],
    }
    return _call_json(
        llm,
        (
            "你是跨研究证据综合专家。输出必须按研究问题和主题组织，"
            "不能退化为逐篇摘要。"
        ),
        f"""综述模式：{case['mode']}
研究问题：{case['question']}

全文证据卡：
{json.dumps(cards, ensure_ascii=False, indent=2)}

返回：
{json.dumps(schema, ensure_ascii=False, indent=2)}

规则：
1. 先判断可比性，再综合。
2. 异构模型、任务、数据集和指标不得直接排名。
3. 每条综合论断给出支持来源、强度和适用边界。
4. technical 模式突出机制、基线公平性、性能、成本与复现。
5. scoping 模式突出概念范围、研究类型、评价场景与证据空白，不强求统一效果结论。
""",
        thinking=True,
        max_tokens=9000,
    )


def _append_references(review: str, papers: list[dict]) -> str:
    body = re.sub(
        r"(?ms)\n##\s+(?:参考来源|参考文献|References)\s*.*$",
        "",
        _clean_markdown(review),
    ).rstrip()
    lines = ["## 参考来源", ""]
    for paper in papers:
        lines.append(
            f"- [{paper['citation_id']}] {paper.get('authors') or '作者未记录'}. "
            f"{paper['title']}. {paper.get('year') or '年份未记录'}. {paper['url']}"
        )
    return body + "\n\n" + "\n".join(lines) + "\n"


def _write_review(
    llm: LLMClient,
    case: dict,
    papers: list[dict],
    cards: list[dict],
    synthesis: dict,
) -> str:
    skill = REVIEW_PRESETS[case["mode"]]["content"]
    return _clean_markdown(
        _call(
            llm,
            "你是严谨的学术综述作者。以结构化证据卡为事实来源，以综合单元组织正文。",
            f"""请撰写完整中文综述。

题目：{case['title']}
研究问题：{case['question']}
综述模式：{case['mode']}
真实方法记录：仅使用 arXiv；候选池经标题摘要筛选后，最终纳入 {len(papers)} 篇可读取全文；
这是一项高负载产品验证，不是穷尽性系统综述。

结构化证据卡：
{json.dumps(cards, ensure_ascii=False, indent=2)}

跨研究综合：
{json.dumps(synthesis, ensure_ascii=False, indent=2)}

模式 Skill：
{skill}

强制要求：
1. 使用“摘要、研究范围与问题、方法、主题综合、局限性、结论、参考来源”结构；
technical 增加性能与效率比较、复现性；scoping 增加证据版图与研究空白。
2. 按综合主题写作，禁止使用“一篇论文一个小节”的摘要合集结构。
3. 每个具体方法、数字、数据集、指标、归因和效果判断紧邻 [P#]。
4. 异构实验不得拼成统一排名；证据缺失写“本次纳入语料不足以判断”。
5. 方法执行事实标记 `【方法记录】`；无直接来源的解释标记 `【综合判断】`。
6. 不创造来源、数字、代码状态、页码或实验；不连续引用原文超过 15 个词。
7. 不自行输出参考来源，系统确定性附加。
8. 目标长度 6500–10000 中文字符，直接输出 Markdown。
""",
            thinking=True,
            max_tokens=15000,
        )
    )


def _audit_review(
    llm: LLMClient,
    case: dict,
    draft: str,
    cards: list[dict],
    synthesis: dict,
) -> str:
    return _clean_markdown(
        _call(
            llm,
            "你是严格的引用与方法学审计员。直接修订全文，只保留证据支持的陈述。",
            f"""综述模式：{case['mode']}
研究问题：{case['question']}

证据卡：
{json.dumps(cards, ensure_ascii=False, indent=2)}

综合：
{json.dumps(synthesis, ensure_ascii=False, indent=2)}

待审计综述：
{draft}

审计并直接修订：
1. 引用只能使用现有 [P#]，具体事实必须就近引用。
2. 删除无支持数字、来源、代码状态、性能排名和范围泛化。
3. 保留主题化跨研究综合；不得退化为逐篇摘要。
4. 方法事实使用 `【方法记录】`，解释性推断使用 `【综合判断】`。
5. 保留完整结构，不输出参考来源或解释。
""",
            thinking=True,
            max_tokens=15000,
        )
    )


def _quality_sources(papers: list[dict]) -> list[dict]:
    return [
        {"id": paper["citation_id"], "evidence_basis": "full_text"}
        for paper in papers
    ]


def _repair_quality(
    llm: LLMClient,
    case: dict,
    review: str,
    cards: list[dict],
    quality: dict,
) -> str:
    return _clean_markdown(
        _call(
            llm,
            "你是综述质量门禁修订器。只修复列出的引用、结构和证据问题，不得补造事实。",
            f"""研究问题：{case['question']}

质量问题：
{json.dumps({
    'section_coverage': quality.get('section_coverage'),
    'claim_citation_coverage': quality.get('claim_citation_coverage'),
    'unsupported_claims': quality.get('unsupported_claims', [])[:20],
    'invalid_citations': quality.get('invalid_citations'),
}, ensure_ascii=False, indent=2)}

证据卡：
{json.dumps(cards, ensure_ascii=False, indent=2)}

综述：
{review}

返回完整修订版，不输出参考来源，并严格满足：
1. 使用一个 `#` 主标题，以及 `## 摘要`、`## 引言`、`## 方法`、
   `## 结果与证据综合`、`## 讨论与局限`、`## 结论` 六个一级章节；
   可在这些章节下保留 `###` 子主题。
2. 经验性事实、方法/模型/数据集/样本/指标/数值及归因判断必须在同一句末尾
   使用半角方括号引用，如 `[P1]` 或 `[P1] [P2]`。不得只写裸 `P1`，
   不得使用 `【P1】` 或 `[P1, P2]`。
3. 本次检索和筛选过程写成 `【方法记录】...`；无法由单篇来源直接支持的
   跨论文解释写成 `【作者综合判断】...`，并保持措辞克制。
4. 在正文中实质性使用全部纳入来源，但只能在证据卡确实支持时引用；
   不能为提高覆盖率而随意贴引用。
5. 修复质量问题中列出的每一条无支持论断：补上正确证据、改为带标签的
   综合判断，或删除。不要降低综述的跨论文综合质量。
""",
            thinking=False,
            max_tokens=15000,
        )
    )


def _independent_audit(
    llm: LLMClient,
    case: dict,
    review: str,
    cards: list[dict],
) -> dict:
    evidence_summary = [
        {
            "citation_id": row.get("citation_id"),
            "title": row.get("title"),
            "main_findings": row.get("main_findings"),
            "limitations": row.get("limitations"),
            "reproducibility": row.get("reproducibility"),
        }
        for row in cards
    ]
    result = _call_json(
        llm,
        "你是独立综述审稿人，只根据给定证据评价。",
        f"""当前日期：{date.today().isoformat()}。不要把已经发生的年份误判为未来年份。
模式：{case['mode']}
研究问题：{case['question']}

综述：
{review}

证据摘要：
{json.dumps(evidence_summary, ensure_ascii=False, indent=2)}

返回 JSON：
- verdict: pass|needs_revision
- strengths: 字符串数组
- major_issues: 字符串数组
- evidence_grounding: 0-1
- synthesis_quality: 0-1
- structure_quality: 0-1
- citation_problems: 字符串数组
- human_checks_required: 字符串数组
""",
        thinking=False,
        max_tokens=4000,
    )
    major_issues = result.get("major_issues") or []
    citation_problems = result.get("citation_problems") or []
    reported_verdict = result.get("verdict")
    result["reported_verdict"] = reported_verdict
    if major_issues or citation_problems:
        result["verdict"] = "needs_revision"
    elif reported_verdict not in {"pass", "needs_revision"}:
        result["verdict"] = "needs_revision"
    return result


def _sanitized_candidates(candidates: list[dict]) -> list[dict]:
    return [
        {
            "paper_id": item.get("paper_id"),
            "title": item.get("title"),
            "authors": item.get("authors"),
            "year": item.get("publication_year"),
            "source_url": item.get("source_url"),
            "abstract_available": bool(item.get("abstract")),
            "abstract_excerpt": _short_excerpt(item.get("abstract")),
        }
        for item in candidates
    ]


def run_case(llm: LLMClient, case: dict) -> dict:
    case_dir = OUTPUT_ROOT / case["id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    summary_path = case_dir / "summary.json"
    if summary_path.exists() and (case_dir / "formal_review.md").exists():
        print(f"[{case['id']}] complete; reusing", flush=True)
        return json.loads(summary_path.read_text(encoding="utf-8"))

    selection_path = case_dir / "selection.json"
    selected_path = case_dir / "included_sources.json"
    screening_checkpoint_path = case_dir / ".screening_checkpoint.json"
    if selection_path.exists() and selected_path.exists():
        ranking = json.loads(selection_path.read_text(encoding="utf-8"))
        selected = json.loads(selected_path.read_text(encoding="utf-8"))
        candidates = []
        ledger = json.loads((case_dir / "search_ledger.json").read_text(encoding="utf-8"))
    else:
        if screening_checkpoint_path.exists():
            print(f"[{case['id']}] reusing screening checkpoint", flush=True)
            checkpoint = json.loads(
                screening_checkpoint_path.read_text(encoding="utf-8")
            )
            candidates = checkpoint["candidates"]
            ledger = checkpoint["ledger"]
            ranking = checkpoint["ranking"]
        else:
            print(f"[{case['id']}] searching", flush=True)
            candidates, ledger = _search(case)
            if len(candidates) < TARGET_INCLUDED:
                raise RuntimeError(
                    f"{case['id']} returned only {len(candidates)} unique candidates"
                )
            print(f"[{case['id']}] screening {len(candidates)} candidates", flush=True)
            ranking = _select(llm, case, candidates)
            _write(screening_checkpoint_path, {
                "candidates": candidates,
                "ledger": ledger,
                "ranking": ranking,
            })
        selected, retrieval = _download_selected(
            case_dir,
            ranking,
            case["id"],
        )
        _write(case_dir / "candidate_pool.json", _sanitized_candidates(candidates))
        _write(case_dir / "search_ledger.json", ledger)
        _write(selection_path, {
            "selection_rationale": ranking.get("selection_rationale"),
            "anticipated_gaps": ranking.get("anticipated_gaps"),
            "ranked": [
                {
                    "paper_id": item.get("paper_id"),
                    "arxiv_id": item.get("arxiv_id"),
                    "openalex_id": item.get("openalex_id"),
                    "doi": item.get("doi"),
                    "pdf_url": item.get("pdf_url"),
                    "title": item.get("title"),
                    "authors": item.get("authors"),
                    "publication_year": item.get("publication_year"),
                    "source_url": item.get("source_url"),
                    "screening": item.get("screening"),
                }
                for item in ranking["ranked"]
            ],
            "retrieval_attempts": retrieval["attempts"],
        })
        _write(selected_path, selected)
        screening_checkpoint_path.unlink(missing_ok=True)
        # Full texts remain in memory only for this run.
        _write(case_dir / "protocol.json", {
            "mode": case["mode"],
            "question": case["question"],
            "sources": ["OpenAlex candidate discovery", "original open-access full text"],
            "candidate_count": len(candidates),
            "target_included": TARGET_INCLUDED,
            "included_count": len(selected),
            "status": "focused_high_load_validation",
            "systematic_review_claim_allowed": False,
        })
        # Checkpoint transient full text only in memory. Evidence extraction
        # happens immediately before this function returns.
        ranking["_full_texts"] = retrieval["texts"]

    evidence_path = case_dir / "evidence_cards.json"
    if evidence_path.exists():
        cards = json.loads(evidence_path.read_text(encoding="utf-8"))
    else:
        full_texts = ranking.get("_full_texts")
        if not full_texts:
            # Resume after a crash: re-download only the confirmed inclusion set.
            resume_ranking = {
                "ranked": [
                    {
                        **paper,
                        "source_url": paper["url"],
                        "publication_year": paper.get("year"),
                        "screening": {"decision": "include"},
                    }
                    for paper in selected
                ]
            }
            redownloaded, retrieval = _download_selected(
                case_dir,
                resume_ranking,
                case["id"],
            )
            # Preserve original citation ordering.
            by_pid = {row["paper_id"]: row for row in redownloaded}
            selected = [
                {**paper, "pages_extracted": by_pid[paper["paper_id"]]["pages_extracted"]}
                for paper in selected
            ]
            full_texts = {
                paper["citation_id"]: retrieval["texts"][by_pid[paper["paper_id"]]["citation_id"]]
                for paper in selected
            }
        checkpoint = case_dir / "evidence_cards.checkpoint.json"
        cards = (
            json.loads(checkpoint.read_text(encoding="utf-8"))
            if checkpoint.exists()
            else []
        )
        completed = {row.get("citation_id") for row in cards}
        for start in range(0, len(selected), 2):
            batch = [
                paper for paper in selected[start:start + 2]
                if paper["citation_id"] not in completed
            ]
            if not batch:
                continue
            print(
                f"[{case['id']}] extracting {batch[0]['citation_id']}"
                f"-{batch[-1]['citation_id']}",
                flush=True,
            )
            rows = _extract_batch(llm, case, batch, full_texts)
            cards.extend(rows)
            completed.update(row["citation_id"] for row in rows)
            cards.sort(key=lambda row: int(row["citation_id"][1:]))
            _write(checkpoint, cards)
        _write(evidence_path, cards)
        checkpoint.unlink(missing_ok=True)

    synthesis_path = case_dir / "synthesis.json"
    if synthesis_path.exists():
        synthesis = json.loads(synthesis_path.read_text(encoding="utf-8"))
    else:
        print(f"[{case['id']}] synthesizing {len(cards)} papers", flush=True)
        synthesis = _synthesize(llm, case, cards)
        _write(synthesis_path, synthesis)

    draft_path = case_dir / "draft_before_audit.md"
    if draft_path.exists():
        draft = draft_path.read_text(encoding="utf-8")
    else:
        print(f"[{case['id']}] writing", flush=True)
        draft = _write_review(llm, case, selected, cards, synthesis)
        _write(draft_path, draft)

    audited_path = case_dir / "review_after_model_audit.md"
    if audited_path.exists():
        review = audited_path.read_text(encoding="utf-8")
    else:
        print(f"[{case['id']}] citation audit", flush=True)
        review = _audit_review(llm, case, draft, cards, synthesis)
        review = _normalize_citation_markers(review)
        review = _append_references(review, selected)
        _write(audited_path, review)

    quality_sources = _quality_sources(selected)
    quality = assess_review_quality(review, quality_sources, language="zh-CN")
    _write(case_dir / "quality_before_repairs.json", quality)
    for revision in range(1, 3):
        if quality.get("status") == "passed":
            break
        print(
            f"[{case['id']}] quality repair {revision} score={quality.get('score')}",
            flush=True,
        )
        review = _repair_quality(llm, case, review, cards, quality)
        review = _normalize_citation_markers(review)
        review = _append_references(review, selected)
        _write(case_dir / f"review_quality_revision_{revision}.md", review)
        quality = assess_review_quality(review, quality_sources, language="zh-CN")
        _write(case_dir / f"quality_revision_{revision}.json", quality)

    _write(case_dir / "formal_review.md", review)
    _write(case_dir / "product_quality.json", quality)
    print(f"[{case['id']}] independent audit", flush=True)
    audit = _independent_audit(llm, case, review, cards)
    _write(case_dir / "model_methodology_audit.json", audit)
    summary = {
        "case_id": case["id"],
        "mode": case["mode"],
        "title": case["title"],
        "candidate_count": (
            len(json.loads((case_dir / "candidate_pool.json").read_text(encoding="utf-8")))
            if (case_dir / "candidate_pool.json").exists()
            else None
        ),
        "included_count": len(selected),
        "full_text_count": len(cards),
        "review_characters": len(review),
        "product_quality_score": quality.get("score"),
        "product_quality_status": quality.get("status"),
        "model_audit_verdict": audit.get("verdict"),
        "api_key_retained": False,
    }
    _write(summary_path, summary)
    return summary


def main() -> int:
    llm = _provider()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    summaries = []
    for index, case in enumerate(CASES, start=1):
        print(f"=== case {index}/{len(CASES)}: {case['id']} ===", flush=True)
        summaries.append(run_case(llm, case))
    _write(OUTPUT_ROOT / "trial_summary.json", {"cases": summaries})
    _write(OUTPUT_ROOT / "README.md", """# 双模式、多主题、12+篇全文综述试验

本目录包含两种综述模式：

- `technical-*`：计算机/AI 技术综述。
- `scoping-*`：范围综述/系统映射。

每个主题目标纳入至少 12 篇可读取全文。请先查看 `trial_summary.json`，再进入各案例查看
`formal_review.md`、`included_sources.json`、`evidence_cards.json`、`synthesis.json`、
`product_quality.json` 和 `model_methodology_audit.json`。

API Key 未保存，源 PDF 在提取后删除。所有输出仍是投稿前研究底稿，需要研究者复核。
""")
    print(OUTPUT_ROOT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
