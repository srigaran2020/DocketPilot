"""Provider-neutral LLM interface.

Only redacted text may be passed in (spec 3.3). The model's hidden reasoning is never returned:
evidence must always be a quoted source passage (spec 14).
"""
from dataclasses import dataclass
from typing import Any, Literal, Protocol

ReasoningEffort = Literal["low", "medium", "high"]
UnavailableReason = Literal["not_configured", "rate_limited", "unreachable", "timeout", "server_error"]


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class LLMError(Exception):
    """The request itself was rejected (bad parameters, invalid schema). Retrying will not help."""


class LLMUnavailable(Exception):
    """The provider cannot answer right now. AI steps should pause and tell the user why."""

    def __init__(self, reason: UnavailableReason, message: str, retry_after_s: float | None = None):
        super().__init__(message)
        self.reason = reason
        self.retry_after_s = retry_after_s


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        reasoning_effort: ReasoningEffort = "medium",
        max_tokens: int = 2048,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
    ) -> LLMResult: ...
