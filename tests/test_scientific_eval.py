import json
from pathlib import Path

from scripts.evaluate_scientific_workflow import evaluate


ROOT = Path(__file__).parents[1]


def test_scientific_eval_set_has_twenty_balanced_topics():
    topics = json.loads(
        (ROOT / "evals" / "scientific_review" / "topics.json").read_text(encoding="utf-8")
    )

    assert len(topics) == 20
    assert sum(item["domain"] == "computer_ai" for item in topics) == 10
    assert sum(item["domain"] == "general" for item in topics) == 10
    assert all(item["known_relevant_titles"] for item in topics)


def test_scientific_eval_computes_recall_sensitivity_and_flow_reconciliation():
    topics = [{
        "id": "topic",
        "domain": "general",
        "question": "Question",
        "known_relevant_titles": ["Known Relevant Study"],
    }]
    predictions = {
        "topic": {
            "candidate_titles": ["Known Relevant Study"],
            "screening": [{"title": "Known Relevant Study", "decision": "include"}],
            "flow": {
                "discovered": 2,
                "duplicates_removed": 1,
                "unique_candidates": 1,
            },
        }
    }

    report = evaluate(topics, predictions)

    assert report["candidate_recall"] == 1.0
    assert report["screening_sensitivity"] == 1.0
    assert report["flow_reconciliation"] == 1.0
    assert report["passed"] is True
