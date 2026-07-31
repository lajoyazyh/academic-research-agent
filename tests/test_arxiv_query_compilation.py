from tools.arxiv_tools import compile_arxiv_query


def test_plain_phrase_becomes_all_field_phrase():
    assert (
        compile_arxiv_query("retrieval augmented generation")
        == 'all:"retrieval augmented generation"'
    )


def test_boolean_clauses_are_fielded_independently():
    assert (
        compile_arxiv_query("(LoRA OR QLoRA OR AdaLoRA) AND language models")
        == '(all:"LoRA" OR all:"QLoRA" OR all:"AdaLoRA") '
        'AND all:"language models"'
    )


def test_explicit_arxiv_field_query_is_preserved():
    query = 'ti:"retrieval augmented generation" AND cat:cs.CL'
    assert compile_arxiv_query(query) == query


def test_andnot_operator_is_preserved():
    assert (
        compile_arxiv_query("agents ANDNOT astronomy")
        == 'all:"agents" ANDNOT all:"astronomy"'
    )
