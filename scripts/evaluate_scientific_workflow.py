"""Score exported scientific-workflow predictions against the fixed topic set.

Prediction JSON shape:
{
  "ai_gnn": {
    "candidate_titles": ["..."],
    "screening": [{"title": "...", "decision": "include"}],
    "flow": {"discovered": 2, "duplicates_removed": 0, "unique_candidates": 2}
  }
}
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOPICS = ROOT / "evals" / "scientific_review" / "topics.json"


def _fingerprint(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(title).casefold()))


def _matches(expected: str, observed: str) -> bool:
    left = set(_fingerprint(expected).split())
    right = set(_fingerprint(observed).split())
    if not left or not right:
        return False
    return len(left & right) / len(left | right) >= 0.8


def evaluate(topics: list[dict], predictions: dict) -> dict:
    relevant_total = 0
    retrieved_relevant = 0
    screened_relevant = 0
    flow_checks = 0
    flow_reconciled = 0
    topic_results = []

    for topic in topics:
        prediction = predictions.get(topic["id"], {})
        candidates = prediction.get("candidate_titles") or []
        included = [
            row.get("title", "")
            for row in prediction.get("screening") or []
            if row.get("decision") == "include"
        ]
        expected_titles = topic.get("known_relevant_titles") or []
        relevant_total += len(expected_titles)
        topic_retrieved = sum(
            any(_matches(expected, candidate) for candidate in candidates)
            for expected in expected_titles
        )
        topic_screened = sum(
            any(_matches(expected, title) for title in included)
            for expected in expected_titles
        )
        retrieved_relevant += topic_retrieved
        screened_relevant += topic_screened

        flow = prediction.get("flow")
        reconciled = None
        if isinstance(flow, dict):
            flow_checks += 1
            reconciled = (
                int(flow.get("discovered", 0)) - int(flow.get("duplicates_removed", 0))
                == int(flow.get("unique_candidates", 0))
            )
            flow_reconciled += int(reconciled)
        topic_results.append({
            "id": topic["id"],
            "retrieved_relevant": topic_retrieved,
            "screened_relevant": topic_screened,
            "known_relevant": len(expected_titles),
            "flow_reconciled": reconciled,
        })

    candidate_recall = retrieved_relevant / relevant_total if relevant_total else 0.0
    screening_sensitivity = screened_relevant / relevant_total if relevant_total else 0.0
    flow_reconciliation = flow_reconciled / flow_checks if flow_checks else 0.0
    return {
        "topic_count": len(topics),
        "candidate_recall": round(candidate_recall, 4),
        "screening_sensitivity": round(screening_sensitivity, 4),
        "flow_reconciliation": round(flow_reconciliation, 4),
        "targets": {
            "candidate_recall": 0.90,
            "screening_sensitivity": 0.95,
            "flow_reconciliation": 1.0,
        },
        "passed": (
            candidate_recall >= 0.90
            and screening_sensitivity >= 0.95
            and flow_checks == len(topics)
            and flow_reconciliation == 1.0
        ),
        "topics": topic_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    topics = json.loads(args.topics.read_text(encoding="utf-8"))
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    report = evaluate(topics, predictions)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
