"""Deterministically finalize the completed multi-topic trial artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "scripts"))

from main import _normalize_citation_markers, assess_review_quality  # noqa: E402
from run_glm_multi_topic_review_trials import (  # noqa: E402
    CASES,
    OUTPUT_ROOT,
    _quality_sources,
    _write,
)


DEDUP_OVERRIDES = {
    "scoping-agent-evaluation": {
        "unique_candidate_count": 42,
        "unique_study_count": 11,
        "version_linked_record_count": 1,
    }
}


def main() -> int:
    summaries = []
    for case in CASES:
        case_dir = OUTPUT_ROOT / case["id"]
        review_path = case_dir / "formal_review.md"
        review = _normalize_citation_markers(
            review_path.read_text(encoding="utf-8")
        )
        _write(review_path, review)
        selected = json.loads(
            (case_dir / "included_sources.json").read_text(encoding="utf-8")
        )
        cards = json.loads(
            (case_dir / "evidence_cards.json").read_text(encoding="utf-8")
        )
        quality = assess_review_quality(
            review,
            _quality_sources(selected),
            language="zh-CN",
        )
        _write(case_dir / "product_quality.json", quality)
        audit = json.loads(
            (case_dir / "model_methodology_audit.json").read_text(
                encoding="utf-8"
            )
        )
        candidate_count = len(json.loads(
            (case_dir / "candidate_pool.json").read_text(encoding="utf-8")
        ))
        dedup = DEDUP_OVERRIDES.get(case["id"], {})
        summary = {
            "case_id": case["id"],
            "mode": case["mode"],
            "title": case["title"],
            "candidate_record_count": candidate_count,
            "unique_candidate_count": dedup.get(
                "unique_candidate_count",
                candidate_count,
            ),
            "included_record_count": len(selected),
            "unique_study_count": dedup.get(
                "unique_study_count",
                len(selected),
            ),
            "version_linked_record_count": dedup.get(
                "version_linked_record_count",
                0,
            ),
            "full_text_record_count": len(cards),
            "review_characters": len(review),
            "product_quality_score": quality.get("score"),
            "product_quality_status": quality.get("status"),
            "model_audit_verdict": audit.get("verdict"),
            "model_audit_major_issue_count": len(
                audit.get("major_issues") or []
            ),
            "human_checks_required_count": len(
                audit.get("human_checks_required") or []
            ),
            "api_key_retained": False,
        }
        _write(case_dir / "summary.json", summary)
        summaries.append(summary)

    _write(OUTPUT_ROOT / "trial_summary.json", {"cases": summaries})
    print(OUTPUT_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
