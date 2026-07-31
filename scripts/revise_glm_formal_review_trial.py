"""Run the production quality gate and revise the GLM formal-review trial."""

from __future__ import annotations

import getpass
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "scripts"))

from llms.client import LLMClient  # noqa: E402
from main import assess_review_quality  # noqa: E402
from run_glm_formal_review_trial import (  # noqa: E402
    BASE_URL,
    MODEL,
    OUTPUT_ROOT,
    TOPIC,
    _append_references,
    _call,
    _call_json,
    _clean_markdown,
    _deterministic_quality,
    _write,
)


def _quality_sources(source_manifest: list[dict]) -> list[dict]:
    return [
        {
            "id": source["citation_id"],
            "evidence_basis": source.get("evidence_basis", "full_text"),
        }
        for source in source_manifest
    ]


def _revise(
    llm: LLMClient,
    review: str,
    evidence_cards: list[dict],
    synthesis: dict,
    quality: dict,
    pass_index: int,
) -> str:
    problems = {
        "section_coverage": quality.get("section_coverage"),
        "claim_citation_coverage": quality.get("claim_citation_coverage"),
        "unsupported_claims": quality.get("unsupported_claims", [])[:20],
        "invalid_citations": quality.get("invalid_citations", []),
    }
    prompt = f"""请执行第 {pass_index} 轮正式综述质量修订，直接返回完整 Markdown 正文。

研究问题：
{TOPIC}

生产质量门禁发现：
{json.dumps(problems, ensure_ascii=False, indent=2)}

结构化证据卡（唯一事实来源）：
{json.dumps(evidence_cards, ensure_ascii=False, indent=2)}

跨研究综合：
{json.dumps(synthesis, ensure_ascii=False, indent=2)}

待修订综述：
{review}

必须修正：
1. 使用以下二级章节名或等价的包含关键词标题：摘要、研究范围与问题、方法、主题综合、效率与性能比较、复现性、局限性、结论。不要输出参考来源，系统会附加。
2. 摘要、引言/研究范围、机制解释、跨研究比较、讨论和结论中的每个经验性陈述都要就近引用 [P1]-[P4]。
3. 仅当一个结论确实由多个来源共同支持时才并列多个引用。
4. Prefix-Tuning 的证据来自生成任务，不得写成经过 GLUE/NLU 验证；不能写“所有四种方法在 NLU 上相当”。
5. `code_available: null` 表示证据卡无法判断，不得改写为“代码未公开”。
6. 文献年份范围是 2019–2021；不得把这四篇文献的结果称为当前主流、首选或普遍最优。
7. LoRA、Prefix-Tuning、Adapter、BitFit 使用异构模型、任务和指标；不得跨研究给出统一性能排名。
8. 把“参数比例”“训练显存”“训练吞吐”“存储开销”“序列长度开销”“推理延迟”分别表述。
9. 研究协议、筛选数量等执行事实可标记为 `【方法记录】`；作者的解释性推断标记为 `【综合判断】`。
10. 不创造新数字、数据集、代码状态、作者、页码或来源，不连续引用原文超过 15 个词。
11. 保留完整、主题化的跨论文综合，目标 5000–8000 中文字符，禁止退化为逐篇摘要。
"""
    return _clean_markdown(
        _call(
            llm,
            "你是严格的计算机科学综述编辑。以证据卡为事实来源，优先删除不可靠陈述。",
            prompt,
            thinking=True,
            max_tokens=12000,
        )
    )


def main() -> int:
    audit_only = "--audit-only" in sys.argv[1:]
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
    api_key = ""

    review_path = OUTPUT_ROOT / "formal_review.md"
    evidence_cards = json.loads(
        (OUTPUT_ROOT / "evidence_cards.json").read_text(encoding="utf-8")
    )
    synthesis = json.loads(
        (OUTPUT_ROOT / "synthesis.json").read_text(encoding="utf-8")
    )
    source_manifest = json.loads(
        (OUTPUT_ROOT / "source_manifest.json").read_text(encoding="utf-8")
    )
    quality_sources = _quality_sources(source_manifest)
    review = review_path.read_text(encoding="utf-8")
    before_quality = assess_review_quality(review, quality_sources, language="zh-CN")
    quality = before_quality
    if not audit_only:
        shutil.copyfile(review_path, OUTPUT_ROOT / "formal_review_before_product_gate.md")
        _write(OUTPUT_ROOT / "product_quality_before.json", before_quality)
        for index in range(1, 3):
            print(f"[revision {index}/2] quality={quality.get('score')}", flush=True)
            review = _revise(llm, review, evidence_cards, synthesis, quality, index)
            review = _append_references(review)
            _write(OUTPUT_ROOT / f"formal_review_revision_{index}.md", review)
            quality = assess_review_quality(review, quality_sources, language="zh-CN")
            _write(OUTPUT_ROOT / f"product_quality_revision_{index}.json", quality)
            if quality.get("status") == "passed":
                break

    _write(review_path, review)
    _write(OUTPUT_ROOT / "product_quality.json", quality)
    _write(OUTPUT_ROOT / "deterministic_quality.json", _deterministic_quality(review))

    print("[final audit] independent review", flush=True)
    audit_evidence = [
        {
            "citation_id": item.get("citation_id"),
            "title": item.get("title"),
            "main_findings": item.get("main_findings"),
            "limitations": item.get("limitations"),
            "reproducibility": item.get("reproducibility"),
        }
        for item in evidence_cards
    ]
    model_audit = _call_json(
        llm,
        "你是独立的计算机科学技术综述审稿人，只根据给定证据评价，不补充外部知识。",
        f"""请严格评价下列综述。

综述：
{review}

审计用证据摘要：
{json.dumps(audit_evidence, ensure_ascii=False, indent=2)}

返回 JSON：
- verdict: pass|needs_revision
- strengths: 字符串数组
- major_issues: 字符串数组
- factual_or_scope_errors: 字符串数组
- evidence_grounding: 0-1
- synthesis_quality: 0-1
- structure_quality: 0-1
- citation_problems: 字符串数组
- human_checks_required: 字符串数组

审稿时特别检查：Prefix-Tuning 是否被错误说成 NLU/GLUE 证据；代码状态 null 是否被错误解释；
是否把异构任务结果直接排名；摘要和结论是否有就近引用。
""",
        thinking=False,
        max_tokens=3000,
    )
    _write(OUTPUT_ROOT / "model_methodology_audit.json", model_audit)

    manifest = json.loads(
        (OUTPUT_ROOT / "run_manifest.json").read_text(encoding="utf-8")
    )
    manifest.update({
        "product_quality_score": quality.get("score"),
        "product_quality_status": quality.get("status"),
        "model_audit_verdict": model_audit.get("verdict"),
        "api_key_retained": False,
    })
    _write(OUTPUT_ROOT / "run_manifest.json", manifest)
    print(
        json.dumps(
            {
                "score": quality.get("score"),
                "status": quality.get("status"),
                "model_audit": model_audit.get("verdict"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if quality.get("status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
