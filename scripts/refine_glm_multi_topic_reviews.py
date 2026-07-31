"""Refine completed multi-topic reviews against the corrected quality gate.

The API key is collected with a no-echo prompt and never written. Retrieval,
PDF parsing, and evidence extraction are reused from existing checkpoints.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "scripts"))

from main import _normalize_citation_markers, assess_review_quality  # noqa: E402
from run_glm_multi_topic_review_trials import (  # noqa: E402
    CASES,
    OUTPUT_ROOT,
    _append_references,
    _independent_audit,
    _provider,
    _quality_sources,
    _repair_quality,
    _write,
)


def main() -> int:
    llm = _provider()
    summaries = []
    for case in CASES:
        case_dir = OUTPUT_ROOT / case["id"]
        review_path = case_dir / "formal_review.md"
        if not review_path.exists():
            raise RuntimeError(f"Missing completed review: {review_path}")

        original = review_path.read_text(encoding="utf-8")
        backup = case_dir / "formal_review_before_gate_fix.md"
        if not backup.exists():
            shutil.copyfile(review_path, backup)

        review = _normalize_citation_markers(original)
        selected = json.loads(
            (case_dir / "included_sources.json").read_text(encoding="utf-8")
        )
        cards = json.loads(
            (case_dir / "evidence_cards.json").read_text(encoding="utf-8")
        )
        sources = _quality_sources(selected)
        history = []

        for revision in range(1, 4):
            quality = assess_review_quality(review, sources, language="zh-CN")
            history.append({"revision": revision - 1, **quality})
            print(
                f"[{case['id']}] gate {revision - 1}: "
                f"score={quality['score']} unsupported="
                f"{len(quality['unsupported_claims'])}",
                flush=True,
            )
            if quality["status"] == "passed":
                break
            review = _repair_quality(llm, case, review, cards, quality)
            review = _normalize_citation_markers(review)
            review = _append_references(review, selected)
            _write(
                case_dir / f"review_post_gate_fix_{revision}.md",
                review,
            )

        quality = assess_review_quality(review, sources, language="zh-CN")
        history.append({"revision": "final", **quality})
        _write(case_dir / "quality_history_postfix.json", history)
        _write(review_path, review)
        _write(case_dir / "product_quality.json", quality)

        print(f"[{case['id']}] refreshing independent audit", flush=True)
        audit = _independent_audit(llm, case, review, cards)
        _write(case_dir / "model_methodology_audit.json", audit)
        summary = {
            "case_id": case["id"],
            "mode": case["mode"],
            "title": case["title"],
            "candidate_count": len(json.loads(
                (case_dir / "candidate_pool.json").read_text(encoding="utf-8")
            )),
            "included_count": len(selected),
            "full_text_count": len(cards),
            "review_characters": len(review),
            "product_quality_score": quality.get("score"),
            "product_quality_status": quality.get("status"),
            "model_audit_verdict": audit.get("verdict"),
            "api_key_retained": False,
        }
        _write(case_dir / "summary.json", summary)
        summaries.append(summary)

    _write(OUTPUT_ROOT / "trial_summary.json", {"cases": summaries})
    print(OUTPUT_ROOT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
