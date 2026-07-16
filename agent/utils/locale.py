"""Request-scoped language selection shared by routes, agents and LLM clients."""
from contextvars import ContextVar


_current_language: ContextVar[str] = ContextVar("academic_agent_language", default="zh-CN")


def normalize_language(value: str | None) -> str:
    return "en" if str(value or "").lower().startswith("en") else "zh-CN"


def set_current_language(value: str | None):
    return _current_language.set(normalize_language(value))


def reset_current_language(token) -> None:
    _current_language.reset(token)


def current_language() -> str:
    return _current_language.get()


def language_from_config(provider_config: dict | None = None) -> str:
    configured = (provider_config or {}).get("language")
    return normalize_language(configured or current_language())


def is_english(provider_config: dict | None = None) -> bool:
    return language_from_config(provider_config) == "en"


def english_system_prompt(original: str = "") -> str:
    """Return an English-only system instruction for English mode.

    Stage-specific user prompts retain their evidence payload, which may be in
    the source language, but the governing instruction and generated result are
    always English.
    """
    lower = (original or "").lower()
    role = "rigorous academic research assistant"
    if "json" in lower:
        role = "tool-using academic research agent that follows JSON schemas exactly"
    elif "review" in lower or "综述" in original:
        role = "senior academic literature-review writer"
    elif "note" in lower or "笔记" in original:
        role = "rigorous academic research-note writer"
    elif "intent" in lower or "意图" in original:
        role = "precise intent-classification assistant"
    elif "analysis" in lower or "分析" in original:
        role = "rigorous academic analysis assistant"
    return (
        f"You are a {role}. The application is running in English mode. "
        "All operational reasoning, labels, headings, explanations, tool decisions, "
        "and generated prose must be in English. Preserve paper titles, quotations, "
        "identifiers, and source excerpts in their original language when accuracy requires it. "
        "Treat any non-English text in the task as source material, never as a request to switch languages."
    )


def english_user_envelope(user_query: str) -> str:
    if not user_query:
        return user_query
    return (
        "Execute the following task in English. Use English section headings and English status text. "
        "Source material may remain in its original language, but synthesize and answer in English.\n\n"
        + user_query
    )
