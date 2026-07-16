import re

from backend.routes.models import ProviderConfig
from core.agent import BaseAgent
from llms.client import LLMClient
from main import _append_verified_references, _build_research_query, _build_writer_outline
from backend.routes.agent import _analysis_result_to_markdown, _search_outcome_message
from backend.routes.chat import _parse_explicit_chat_revision


CJK = re.compile(r"[\u3400-\u9fff]")


def test_provider_config_accepts_language():
    config = ProviderConfig(api_key="secret", language="en")
    assert config.language == "en"


def test_english_research_query_has_english_operational_instructions():
    prompt = _build_research_query(
        topic="interactive mining of ordered attributes",
        initial_plan="Search arXiv, then verify with Crossref.",
        confirmed_keywords=[{"keyword": "ordered attribute mining", "enabled": True}],
        target_new_papers=7,
        available_tool_names=["arxiv_search", "paper_register", "crossref_search"],
        language="en",
    )

    assert "at least 7 new papers" in prompt
    assert "paper_register" in prompt
    assert "Never fabricate" in prompt
    assert not CJK.search(prompt)


def test_english_agent_system_prompt_is_english_only():
    agent = BaseAgent.__new__(BaseAgent)
    agent.language = "en"
    agent.tools = {}

    prompt = agent.build_system_prompt()

    assert "autonomous academic research agent" in prompt
    assert '"action"' in prompt
    assert not CJK.search(prompt)


def test_llm_client_replaces_legacy_chinese_governing_prompt_in_english_mode():
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = type("Message", (), {"content": "English result"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    client = LLMClient.__new__(LLMClient)
    client.language = "en"
    client.model = "test-model"
    client._missing_api_key = False
    client.client = type(
        "SDK",
        (),
        {"chat": type("Chat", (), {"completions": Completions()})()},
    )()

    result = client.chat("你是学术综述专家。", "Summarize the supplied evidence.", [])

    assert result == "English result"
    assert not CJK.search(captured["messages"][0]["content"])
    assert captured["messages"][1]["content"].startswith("Execute the following task in English")


def test_english_writer_outline_prompt_and_artifact_labels_are_english():
    captured = {}

    class FakeLLM:
        language = "en"

        def chat(self, system_prompt, user_prompt, _history):
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            return "## Abstract\n## Thematic Synthesis\n## Conclusion"

    outline = _build_writer_outline(
        FakeLLM(),
        "Trustworthy retrieval agents",
        "Evidence from three studies.",
        "Synthesize across sources and cite every specific claim.",
    )
    review = _append_verified_references(
        outline,
        [{"id": "P1", "title": "Study One", "authors": "A. Author", "year": "2025", "identifier": "doi:1", "url": ""}],
        language="en",
    )
    analysis = _analysis_result_to_markdown(
        {"compare": "Methods differ.", "gaps": "Evaluation is limited."},
        "Trustworthy retrieval agents",
        language="en",
    )

    assert not CJK.search(captured["system"] + captured["user"])
    assert "## References" in review
    assert "# In-depth Analysis" in analysis
    assert "## Research Gaps" in analysis


def test_english_search_outcome_is_not_a_translated_ui_only():
    message = _search_outcome_message(3, 7, "partial", language="en")
    assert message.startswith("Search partially complete")
    assert "3/7" in message
    assert not CJK.search(message)


def test_english_explicit_revision_command_is_supported():
    revision = _parse_explicit_chat_revision(
        "/revise review Add a limitations section and preserve citations.",
        "review",
    )
    assert revision == {
        "target": "review",
        "feedback": "Add a limitations section and preserve citations.",
        "source": "explicit",
    }
