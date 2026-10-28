"""LLM access. One provider today (Groq); the interface lets another be added by configuration."""
from docketpilot.llm.base import LLMError, LLMProvider, LLMResult, LLMUnavailable
from docketpilot.llm.groq_provider import GroqProvider

# Groq's free tier refuses a request above 8,000 tokens a minute. Long papers are sent as their opening and their
# end (where cause titles, case numbers, orders and next dates usually are), about 5,000 tokens in all.
PAPER_CHARS = 18_000


def head_tail(text: str, limit: int = PAPER_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.65)
    return f"{text[:head]}\n\n[... middle of the document not sent ...]\n\n{text[-(limit - head):]}"

__all__ = ["GroqProvider", "LLMError", "LLMProvider", "LLMResult", "LLMUnavailable", "get_llm"]


def get_llm() -> LLMProvider:
    return GroqProvider.from_settings()
