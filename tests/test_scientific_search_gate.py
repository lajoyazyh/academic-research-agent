from main import _build_research_query, _scientific_search_coverage


def _plan():
    return [{
        "source": "openalex",
        "query": '"graph neural network" OR reproducibility',
        "required_pages": 3,
        "status": "pending",
        "executed_queries": [],
    }]


def test_paper_count_cannot_bypass_protocol_query_coverage():
    traces = [{
        "action": "openalex_search",
        "input": {
            "query": "graph neural network reproducibility",
            "page": 1,
        },
        "error_type": "",
    }]

    allowed, message = _scientific_search_coverage(traces, _plan())

    assert allowed is False
    assert "openalex 1/3" in message


def test_distinct_pages_complete_protocol_query_coverage():
    traces = [
        {
            "action": "openalex_search",
            "input": {
                "query": "graph neural network reproducibility",
                "page": page,
            },
            "error_type": "",
        }
        for page in (1, 2, 3)
    ]

    allowed, message = _scientific_search_coverage(traces, _plan())

    assert allowed is True
    assert message == ""


def test_scientific_prompt_does_not_treat_batch_size_as_stopping_condition():
    prompt = _build_research_query(
        "Graph neural network reproducibility",
        "Search major scholarly databases.",
        [{"english": "graph neural network", "synonyms": "GNN"}],
        target_new_papers=6,
        language="en",
        review_protocol={
            "mode": "systematic",
            "candidate_cap": 500,
            "inclusion_criteria": ["Directly addresses reproducibility."],
            "exclusion_criteria": ["Not a research paper."],
        },
        search_query_plan=_plan(),
    )

    assert "not the scientific stopping condition" in prompt
    assert "Do not finish merely because the batch paper target is met" in prompt
    assert "openalex: pending (0/3 pages or cursor positions)" in prompt
