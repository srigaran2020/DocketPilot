"""GroqProvider behaviour, using a fake client (no network, no quota)."""
import json
from types import SimpleNamespace
from typing import Any

import groq
import httpx
import pytest

from docketpilot.llm import GroqProvider, LLMError, LLMUnavailable

REQ = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _resp(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, request=REQ, headers=headers or {}, json={"error": {"message": "x"}})


class FakeCompletions:
    def __init__(self, outcome: Any):
        self.outcome = outcome
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def provider_with(outcome: Any) -> tuple[GroqProvider, FakeCompletions]:
    p = GroqProvider(api_key="test", model="openai/gpt-oss-120b")
    fake = FakeCompletions(outcome)
    p._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))  # type: ignore[assignment]
    return p, fake


def ok_response(content: str = "hello", reasoning: str = "hidden chain of thought") -> Any:
    msg = SimpleNamespace(content=content, reasoning=reasoning)
    return SimpleNamespace(
        model="openai/gpt-oss-120b",
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3),
    )


async def test_returns_content_and_usage_but_never_reasoning():
    p, _ = provider_with(ok_response())
    r = await p.complete([{"role": "user", "content": "hi"}])
    assert r.text == "hello"
    assert (r.input_tokens, r.output_tokens) == (10, 3)
    assert "hidden" not in json.dumps(r.__dict__)


async def test_sends_reasoning_effort_and_schema():
    p, fake = provider_with(ok_response("{}"))
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    await p.complete([{"role": "user", "content": "x"}], reasoning_effort="low", json_schema=schema,
                     schema_name="facts", max_tokens=99)
    assert fake.kwargs["reasoning_effort"] == "low"
    assert fake.kwargs["max_completion_tokens"] == 99
    assert fake.kwargs["response_format"] == {
        "type": "json_schema", "json_schema": {"name": "facts", "schema": schema}}


async def test_no_schema_means_no_response_format():
    p, fake = provider_with(ok_response())
    await p.complete([{"role": "user", "content": "x"}])
    assert "response_format" not in fake.kwargs


async def test_missing_key_is_not_configured():
    p = GroqProvider(api_key=None, model="m")
    with pytest.raises(LLMUnavailable) as e:
        await p.complete([{"role": "user", "content": "x"}])
    assert e.value.reason == "not_configured"


async def test_rate_limit_maps_to_unavailable_with_retry_after():
    err = groq.RateLimitError("slow down", response=_resp(429, {"retry-after": "7"}), body=None)
    p, _ = provider_with(err)
    with pytest.raises(LLMUnavailable) as e:
        await p.complete([{"role": "user", "content": "x"}])
    assert e.value.reason == "rate_limited"
    assert e.value.retry_after_s == 7.0


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (groq.APIConnectionError(request=REQ), "unreachable"),
        (groq.APITimeoutError(request=REQ), "timeout"),
        (groq.InternalServerError("boom", response=_resp(503), body=None), "server_error"),
    ],
)
async def test_outages_map_to_unavailable(error, reason):
    p, _ = provider_with(error)
    with pytest.raises(LLMUnavailable) as e:
        await p.complete([{"role": "user", "content": "x"}])
    assert e.value.reason == reason


async def test_bad_request_is_llm_error_not_outage():
    p, _ = provider_with(groq.BadRequestError("bad schema", response=_resp(400), body=None))
    with pytest.raises(LLMError):
        await p.complete([{"role": "user", "content": "x"}])


@pytest.mark.live
async def test_live_structured_output():
    """Real call to Groq with synthetic text. Run with:  pytest -m live"""
    p = GroqProvider.from_settings()
    schema = {
        "type": "object",
        "properties": {"cheque_number": {"type": "string"}, "amount_rupees": {"type": "number"}},
        "required": ["cheque_number", "amount_rupees"],
        "additionalProperties": False,
    }
    r = await p.complete(
        [{"role": "system", "content": "Extract the fields."},
         {"role": "user", "content": "Synthetic: Cheque No. 004512 for Rs. 2,50,000 was returned unpaid."}],
        reasoning_effort="low", max_tokens=400, json_schema=schema,
    )
    assert json.loads(r.text) == {"cheque_number": "004512", "amount_rupees": 250000}


async def test_rate_limit_waits_then_succeeds(monkeypatch):
    """With a wait budget, a 429 is retried after the retry-after pause instead of failing the user's request."""
    import docketpilot.llm.groq_provider as gp

    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(gp.asyncio, "sleep", fake_sleep)
    p, fake = provider_with(None)
    p.rate_wait_s = 60
    outcomes = [groq.RateLimitError("slow down", response=_resp(429, {"retry-after": "3"}), body=None), ok_response("done")]

    async def create(**kwargs: Any) -> Any:
        o = outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o

    fake.create = create  # type: ignore[method-assign]
    r = await p.complete([{"role": "user", "content": "hi"}])
    assert r.text == "done" and sleeps == [3.5]


async def test_backup_key_takes_over_when_first_is_out_of_quota(monkeypatch):
    """Daily quota on key 1 -> the same request goes to key 2 at once; key 1 rests and is skipped next time."""
    import docketpilot.llm.groq_provider as gp

    monkeypatch.setattr(gp, "_resting_until", {})
    p = GroqProvider(api_key="k1", model="openai/gpt-oss-120b", backup_api_key="k2")
    daily = groq.RateLimitError("Rate limit reached on tokens per day (TPD)", response=_resp(429, {"retry-after": "900"}), body=None)
    first, second = FakeCompletions(daily), FakeCompletions(ok_response("from backup"))
    p._client = SimpleNamespace(chat=SimpleNamespace(completions=first))  # type: ignore[assignment]
    p._backup = SimpleNamespace(chat=SimpleNamespace(completions=second))  # type: ignore[assignment]
    r = await p.complete([{"role": "user", "content": "hi"}])
    assert r.text == "from backup"
    first.kwargs = {}
    r = await p.complete([{"role": "user", "content": "again"}])
    assert r.text == "from backup" and first.kwargs == {}  # key 1 is resting, not even tried


async def test_both_keys_out_of_quota_reports_daily_limit(monkeypatch):
    import docketpilot.llm.groq_provider as gp

    monkeypatch.setattr(gp, "_resting_until", {})
    p = GroqProvider(api_key="k1", model="openai/gpt-oss-120b", backup_api_key="k2")
    daily = groq.RateLimitError("Rate limit reached on tokens per day (TPD)", response=_resp(429, {"retry-after": "900"}), body=None)
    p._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(daily)))  # type: ignore[assignment]
    p._backup = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(daily)))  # type: ignore[assignment]
    with pytest.raises(LLMUnavailable) as e:
        await p.complete([{"role": "user", "content": "hi"}])
    assert "today" in str(e.value)
