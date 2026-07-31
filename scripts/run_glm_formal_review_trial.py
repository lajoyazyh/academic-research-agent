"""Generate one formal PEFT review with GLM-4.7-Flash and auditable intermediates.

The API key is requested through a no-echo terminal prompt. It is never written
to disk, included in an artifact, or copied into a process environment variable.
Downloaded source PDFs are temporary and removed after evidence extraction.
"""

from __future__ import annotations

import getpass
import json
import re
import shutil
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from llms.client import LLMClient  # noqa: E402
from prompts.review_skills import REVIEW_PRESETS  # noqa: E402
from tools.pdf_tools import ArxivDownloadPdfTool, extract_full_text_from_pdf  # noqa: E402
from utils.parser import extract_json  # noqa: E402


MODEL = "glm-4.7-flash"
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
OUTPUT_ROOT = ROOT / "artifacts" / "scientific-llm-trial-glm-4.7-flash-2026-07-31"

TOPIC = (
    "LoRA、Prefix Tuning、Adapter 与 BitFit 等参数高效微调方法在机制、"
    "实验评价、效率、复现性和适用边界方面有何差异？"
)

SOURCES = [
    {
        "citation_id": "P1",
        "paper_id": "2106.09685",
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "authors": "Edward J. Hu et al.",
        "year": "2021",
        "url": "https://arxiv.org/abs/2106.09685",
    },
    {
        "citation_id": "P2",
        "paper_id": "2101.00190",
        "title": "Prefix-Tuning: Optimizing Continuous Prompts for Generation",
        "authors": "Xiang Lisa Li and Percy Liang",
        "year": "2021",
        "url": "https://arxiv.org/abs/2101.00190",
    },
    {
        "citation_id": "P3",
        "paper_id": "1902.00751",
        "title": "Parameter-Efficient Transfer Learning for NLP",
        "authors": "Neil Houlsby et al.",
        "year": "2019",
        "url": "https://arxiv.org/abs/1902.00751",
    },
    {
        "citation_id": "P4",
        "paper_id": "2106.10199",
        "title": "BitFit: Simple Parameter-efficient Fine-tuning for Transformer-based Masked Language-models",
        "authors": "Elad Ben Zaken, Yoav Goldberg, and Shauli Ravfogel",
        "year": "2021",
        "url": "https://arxiv.org/abs/2106.10199",
    },
]


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value.rstrip() + "\n", encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _clean_markdown(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _call(
    llm: LLMClient,
    system: str,
    prompt: str,
    *,
    thinking: bool,
    max_tokens: int,
) -> str:
    delays = [8, 16, 24, 32, 48]
    for attempt in range(len(delays) + 1):
        try:
            response = llm.client.chat.completions.create(
                model=llm.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
                extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}},
            )
            return str(response.choices[0].message.content or "").strip()
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code != 429 or attempt >= len(delays):
                raise
            delay = delays[attempt]
            print(f"[provider busy] retrying in {delay}s", flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def _call_json(
    llm: LLMClient,
    system: str,
    prompt: str,
    *,
    thinking: bool = False,
    max_tokens: int = 5000,
) -> dict:
    raw = _call(
        llm,
        system + " 只返回一个合法 JSON 对象，不要使用 Markdown 代码围栏。",
        prompt,
        thinking=thinking,
        max_tokens=max_tokens,
    )
    if not raw.strip():
        raise RuntimeError("模型返回了空的 JSON 响应")
    try:
        parsed = extract_json(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {}
    if not isinstance(parsed, dict) or not parsed:
        repaired = _call(
            llm,
            "你是 JSON 格式修复器。只返回修复后的合法 JSON 对象，不增加新事实。",
            raw,
            thinking=False,
            max_tokens=max_tokens,
        )
        try:
            parsed = extract_json(repaired)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
    if not isinstance(parsed, dict) or not parsed:
        raise RuntimeError("模型没有返回可解析的 JSON")
    return parsed


def _page_balanced_text(chunks: list[dict], max_chars: int = 60000) -> str:
    by_page: dict[int, list[str]] = {}
    for chunk in chunks:
        page = int(chunk.get("page") or 0)
        by_page.setdefault(page, []).append(str(chunk.get("text") or ""))
    sections = []
    for page in sorted(by_page):
        page_text = re.sub(r"\s+", " ", " ".join(by_page[page])).strip()
        if page_text:
            sections.append(f"[PDF page {page}]\n{page_text[:3500]}")
    result = "\n\n".join(sections)
    if len(result) <= max_chars:
        return result
    # Preserve the beginning, middle and conclusion instead of truncating only
    # the end, where limitations and conclusions are often located.
    third = max_chars // 3
    middle = len(result) // 2
    return (
        result[:third]
        + "\n\n[...middle selection...]\n\n"
        + result[middle - third // 2:middle + third // 2]
        + "\n\n[...ending selection...]\n\n"
        + result[-third:]
    )


def _extract_one(llm: LLMClient, source: dict, full_text: str) -> dict:
    schema = {
        "citation_id": source["citation_id"],
        "paper_id": source["paper_id"],
        "study_type": None,
        "research_question": None,
        "method_mechanism": None,
        "trainable_components": [],
        "backbones_and_tasks": [],
        "datasets": [],
        "baselines": [],
        "metrics": [],
        "main_findings": [
            {
                "finding": "",
                "support_type": "reported_result|author_claim|reviewer_inference",
                "page": None,
            }
        ],
        "parameter_and_compute_efficiency": [],
        "limitations": [],
        "reproducibility": {
            "code_available": None,
            "implementation_detail_sufficiency": "adequate|partial|unclear",
            "variance_or_significance_reported": None,
            "ablation_reported": None,
        },
        "validity_risks": [],
        "appraisal": {
            "benchmark_fairness": "low_concern|some_concerns|high_concern|unclear",
            "statistical_sufficiency": "low_concern|some_concerns|high_concern|unclear",
            "external_validity": "low_concern|some_concerns|high_concern|unclear",
            "overall": "low_concern|some_concerns|high_concern|unclear",
            "rationale": "",
        },
        "uncertainties": [],
        "confidence": 0.0,
    }
    prompt = f"""研究问题：{TOPIC}

论文元数据：
{json.dumps(source, ensure_ascii=False, indent=2)}

论文全文（带 PDF 页码标记）：
{full_text}

请形成结构化证据卡和设计匹配的技术论文质量评价，返回符合以下结构的 JSON：
{json.dumps(schema, ensure_ascii=False, indent=2)}

约束：
1. 只能使用上面的论文文本；缺失信息用 null 或 []。
2. 数值、数据集、基线和结论必须能定位到所给 PDF 页码。
3. 区分论文作者报告、实验结果和你的评价性推断。
4. 不得生成超过 15 个连续词的原文摘录；证据位置只记录页码并使用概括。
5. 不因为论文知名就自动给出低风险评价。
"""
    card = _call_json(
        llm,
        "你是保守的计算机科学证据提取与研究质量评价引擎。",
        prompt,
        thinking=False,
        max_tokens=6000,
    )
    card["citation_id"] = source["citation_id"]
    card["paper_id"] = source["paper_id"]
    card["title"] = source["title"]
    card["evidence_basis"] = "full_text"
    card["review_status"] = "ai_draft_requires_human"
    return card


def _synthesize(llm: LLMClient, evidence_cards: list[dict]) -> dict:
    schema = {
        "comparison_dimensions": [],
        "method_families": [],
        "consensus": [{"statement": "", "support": ["P1"], "strength": "low|moderate|high"}],
        "disagreements": [
            {
                "issue": "",
                "positions": [],
                "possible_explanations": [],
                "support": [],
            }
        ],
        "cross_study_comparability": [
            {
                "dimension": "",
                "judgement": "comparable|partly_comparable|not_comparable",
                "reason": "",
            }
        ],
        "evidence_gaps": [],
        "synthesis_claims": [
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
        "你是计算机与 AI 技术综述的证据综合专家。重点做跨研究比较，不写逐篇摘要合集。",
        f"""研究问题：{TOPIC}

结构化证据卡：
{json.dumps(evidence_cards, ensure_ascii=False, indent=2)}

请先判断研究间可比性，再形成综合单元。返回以下 JSON：
{json.dumps(schema, ensure_ascii=False, indent=2)}

约束：
1. 论文使用固定标识 P1-P4。
2. 不跨数据集、任务、骨干模型或指标做虚假排名。
3. 结论必须给出支持来源、强度与适用边界。
4. 对没有统一实验条件的比较明确降级证据强度。
""",
        thinking=True,
        max_tokens=7000,
    )


def _draft_review(
    llm: LLMClient,
    evidence_cards: list[dict],
    synthesis: dict,
) -> str:
    skill = REVIEW_PRESETS["technical"]["content"]
    protocol = {
        "mode": "technical",
        "status": "focused_validation_trial",
        "sources": ["arXiv full text"],
        "search_scope": "Four protocol-defined foundational PEFT studies",
        "screening": "Anchor validation with full-text assessment",
        "synthesis_method": "Structured qualitative technical synthesis",
        "limitations": [
            "This is a focused validation run rather than an exhaustive systematic search.",
            "No meta-analysis was attempted because tasks, models and metrics are heterogeneous.",
        ],
    }
    prompt = f"""请撰写一篇完整、连贯、可供研究者审阅的中文技术文献综述。

研究问题：
{TOPIC}

真实执行协议：
{json.dumps(protocol, ensure_ascii=False, indent=2)}

结构化证据卡：
{json.dumps(evidence_cards, ensure_ascii=False, indent=2)}

跨研究综合：
{json.dumps(synthesis, ensure_ascii=False, indent=2)}

写作 Skill：
{skill}

额外要求：
1. 标题使用“参数高效微调的机制、证据与边界：LoRA、Prefix-Tuning、Adapter 与 BitFit 技术综述”。
2. 至少包含摘要、引言、方法、机制分类、跨研究比较、效率与复现性、局限、研究议程、结论。
3. 正文以问题和综合主题组织，禁止按 P1、P2、P3、P4 逐篇介绍。
4. 每个具体方法、实验、数字、数据集和归因判断都紧邻引用 [P1]-[P4]。
5. 证据异质时明确说明不能直接排名；不把参数更少自动等同于训练或推理成本更低。
6. 只可使用证据卡中的事实；不创造 DOI、页码、实验、数字或来源。
7. 使用学术中文转述，不得连续引用论文原文超过 15 个词。
8. 方法部分必须如实声明这是四篇核心论文的聚焦验证性技术综述，不得称为系统综述。
9. 不输出参考文献列表，系统会确定性附加。
10. 直接输出完整 Markdown，目标长度 5000–8000 个中文字符。
"""
    return _clean_markdown(
        _call(
            llm,
            "你是严谨的计算机科学文献综述作者。先综合证据，再写作；绝不补造事实。",
            prompt,
            thinking=True,
            max_tokens=12000,
        )
    )


def _audit_and_revise(
    llm: LLMClient,
    draft: str,
    evidence_cards: list[dict],
    synthesis: dict,
) -> str:
    prompt = f"""请对综述执行引用与方法学审计，并直接返回修订后的完整 Markdown。

唯一允许使用的证据卡：
{json.dumps(evidence_cards, ensure_ascii=False, indent=2)}

证据综合：
{json.dumps(synthesis, ensure_ascii=False, indent=2)}

待审计综述：
{draft}

审计规则：
1. 删除或降级所有不能由证据卡支持的具体事实、数字、比较和归因。
2. 引用只能是 [P1]、[P2]、[P3]、[P4]，并紧邻被支持的句子。
3. 不得把异构任务和指标写成统一性能排名。
4. 明确“方法参数效率”“训练资源”“存储成本”“推理延迟”不是同一概念。
5. 方法部分与真实的四篇核心论文聚焦验证流程一致。
6. 保留跨论文综合，不能退化为逐篇摘要。
7. 不新增参考文献列表；不连续引用原文超过 15 个词。
8. 直接输出修订后的完整 Markdown，不解释审计过程。
"""
    return _clean_markdown(
        _call(
            llm,
            "你是严格的学术证据与方法学审计员。只保留可验证陈述。",
            prompt,
            thinking=True,
            max_tokens=12000,
        )
    )


def _append_references(review: str) -> str:
    body = re.sub(
        r"(?ms)\n##\s+(?:参考文献|参考来源|References)\s*.*$",
        "",
        review,
    ).rstrip()
    lines = ["## 参考来源", ""]
    for source in SOURCES:
        lines.append(
            f"- [{source['citation_id']}] {source['authors']}. "
            f"{source['title']}. {source['year']}. {source['url']}"
        )
    return body + "\n\n" + "\n".join(lines) + "\n"


def _deterministic_quality(review: str) -> dict:
    valid = {"P1", "P2", "P3", "P4"}
    cited = set(re.findall(r"\[(P\d+)\]", review))
    headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", review)
    required = {
        "摘要": ["摘要"],
        "引言或研究范围": ["引言", "研究范围"],
        "方法": ["方法"],
        "比较": ["比较"],
        "复现": ["复现"],
        "局限": ["局限"],
        "结论": ["结论"],
        "参考来源": ["参考文献", "参考来源"],
    }
    section_hits = {
        label: any(
            keyword in heading
            for heading in headings
            for keyword in keywords
        )
        for label, keywords in required.items()
    }
    return {
        "valid_citations": sorted(cited & valid),
        "invalid_citations": sorted(cited - valid),
        "uncited_included_sources": sorted(valid - cited),
        "required_sections": section_hits,
        "all_required_sections_present": all(section_hits.values()),
        "character_count": len(review),
        "output_label": "focused_technical_review_requires_human_validation",
        "passed": not (cited - valid) and not (valid - cited) and all(section_hits.values()),
    }


def main() -> int:
    api_key = getpass.getpass("")
    if not api_key.strip():
        raise SystemExit("API key is required")
    llm = LLMClient({
        "provider_id": "zhipu",
        "api_key": api_key,
        "base_url": BASE_URL,
        "chat_model": MODEL,
        "embedding_model": "",
        "language": "zh-CN",
    })
    # Drop the only extra local reference immediately after the client has copied
    # it into its request-scoped instance.
    api_key = ""

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = OUTPUT_ROOT / ".temporary_sources"
    shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir()

    checkpoint_path = OUTPUT_ROOT / "evidence_cards.checkpoint.json"
    source_checkpoint_path = OUTPUT_ROOT / "source_manifest.checkpoint.json"
    evidence_cards = (
        json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint_path.exists()
        else []
    )
    source_manifest = (
        json.loads(source_checkpoint_path.read_text(encoding="utf-8"))
        if source_checkpoint_path.exists()
        else []
    )
    completed_ids = {item.get("citation_id") for item in evidence_cards}
    try:
        for index, source in enumerate(SOURCES, start=1):
            if source["citation_id"] in completed_ids:
                print(f"[{index}/{len(SOURCES)}] reusing {source['citation_id']}", flush=True)
                continue
            print(f"[{index}/{len(SOURCES)}] extracting {source['citation_id']}", flush=True)
            ArxivDownloadPdfTool(str(temp_dir)).execute(paper_id=source["paper_id"])
            pdf_path = temp_dir / f"{source['paper_id']}.pdf"
            if not pdf_path.exists():
                raise RuntimeError(f"Unable to retrieve full text for {source['citation_id']}")
            chunks = extract_full_text_from_pdf(
                str(pdf_path),
                "glm_formal_trial",
                source["paper_id"],
            )
            if not chunks:
                raise RuntimeError(f"Unable to extract full text for {source['citation_id']}")
            full_text = _page_balanced_text(chunks)
            card = _extract_one(llm, source, full_text)
            evidence_cards.append(card)
            source_manifest.append({
                **source,
                "evidence_basis": "full_text",
                "pages_extracted": len({chunk.get("page") for chunk in chunks}),
                "retained_source_document": False,
            })
            _write(checkpoint_path, evidence_cards)
            _write(source_checkpoint_path, source_manifest)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("[5/8] synthesizing", flush=True)
    synthesis = _synthesize(llm, evidence_cards)
    print("[6/8] drafting review", flush=True)
    draft = _draft_review(llm, evidence_cards, synthesis)
    print("[7/8] auditing review", flush=True)
    reviewed = _audit_and_revise(llm, draft, evidence_cards, synthesis)
    final_review = _append_references(reviewed)
    deterministic_quality = _deterministic_quality(final_review)
    print("[8/8] methodology audit", flush=True)
    model_audit = _call_json(
        llm,
        "你是独立的技术综述质量审稿人。只评价给定文本，不补充领域知识。",
        f"""请评价这篇综述是否真正进行了跨研究综合，而非论文摘要拼接。

综述：
{final_review}

结构化证据：
{json.dumps(evidence_cards, ensure_ascii=False, indent=2)}

返回 JSON，必须包含：
- verdict: pass|needs_revision
- strengths: 字符串数组
- major_issues: 字符串数组
- evidence_grounding: 0-1
- synthesis_quality: 0-1
- structure_quality: 0-1
- citation_problems: 字符串数组
- human_checks_required: 字符串数组
""",
        thinking=True,
        max_tokens=5000,
    )

    _write(OUTPUT_ROOT / "source_manifest.json", source_manifest)
    _write(OUTPUT_ROOT / "evidence_cards.json", evidence_cards)
    _write(OUTPUT_ROOT / "synthesis.json", synthesis)
    _write(OUTPUT_ROOT / "draft_before_audit.md", draft)
    _write(OUTPUT_ROOT / "formal_review.md", final_review)
    _write(OUTPUT_ROOT / "deterministic_quality.json", deterministic_quality)
    _write(OUTPUT_ROOT / "model_methodology_audit.json", model_audit)
    _write(OUTPUT_ROOT / "run_manifest.json", {
        "model": MODEL,
        "provider": "zhipu",
        "api_key_retained": False,
        "topic": TOPIC,
        "case_type": "focused_technical_review_validation",
        "source_count": len(SOURCES),
        "full_text_source_count": len(evidence_cards),
        "pipeline": [
            "full_text_retrieval",
            "structured_evidence_extraction",
            "design_matched_appraisal",
            "cross_study_synthesis",
            "review_write",
            "citation_and_methodology_revision",
            "independent_methodology_audit",
        ],
        "deterministic_quality_passed": deterministic_quality["passed"],
        "model_audit_verdict": model_audit.get("verdict"),
    })
    _write(OUTPUT_ROOT / "README.md", f"""# GLM-4.7-Flash 正式综述试验

本目录使用智谱 `{MODEL}` 和四篇 PEFT 核心论文全文生成。API Key 仅通过无回显终端输入进入当前进程，没有写入任何文件。

建议依次检查：

1. `formal_review.md`
2. `evidence_cards.json`
3. `synthesis.json`
4. `deterministic_quality.json`
5. `model_methodology_audit.json`
6. `draft_before_audit.md`

本产物是四篇协议指定核心论文的聚焦验证性技术综述，不是穷尽性系统综述，仍需研究者复核后使用。
""")
    checkpoint_path.unlink(missing_ok=True)
    source_checkpoint_path.unlink(missing_ok=True)
    print(OUTPUT_ROOT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
