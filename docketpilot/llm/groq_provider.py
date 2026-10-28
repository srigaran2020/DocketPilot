"""Groq provider for openai/gpt-oss-120b.

Several API keys may be configured for the same model (GROQ_API_KEY, GROQ_API_KEY_BACKUP, _BACKUP_2, _BACKUP_3), each
from a different Groq account (limits are per account). When a key hits its daily or per-minute limit it rests until
Groq says it is free again, and the request goes to the next free key straight away.
Which keys are resting is shared by every provider instance in the process.
"""
import asyncio
import time
from typing import Any

import groq

from docketpilot.config import get_settings
from docketpilot.llm.base import LLMError, LLMResult, LLMUnavailable, ReasoningEffort

_resting_until: dict[int, float] = {}  # key slot -> time.monotonic() when it may be used again


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str | None, model: str, timeout_s: float = 60.0, max_retries: int = 2,
                 rate_wait_s: float = 0.0, request_token_cap: int = 0,
                 backup_api_key: str | list[str] | None = None):
        self.model = model
        self.request_token_cap = request_token_cap  # 0 = no cap
        # On the free tier the per-minute token budget runs out often; wait (up to rate_wait_s in total) for the
        # window Groq names in retry-after instead of failing the user's request.
        self.rate_wait_s = rate_wait_s
        # groq's own client retries connection errors, 429s and 5xx with backoff.
        self._client = (
            groq.AsyncGroq(api_key=api_key, timeout=timeout_s, max_retries=max_retries) if api_key else None
        )
        backups = [k for k in ([backup_api_key] if isinstance(backup_api_key, str) else backup_api_key or []) if k]
        # retries are ours when more keys exist: a 429 should switch keys, not back off
        made = [groq.AsyncGroq(api_key=k, timeout=timeout_s, max_retries=0) for k in backups]
        self._backup = made[0] if made else None
        self._extra = made[1:]
        if self._backup is not None and self._client is not None:
            self._client = groq.AsyncGroq(api_key=api_key, timeout=timeout_s, max_retries=0)

    @classmethod
    def from_settings(cls) -> "GroqProvider":
        s = get_settings()
        key = s.groq_api_key.get_secret_value() if s.groq_api_key else None
        backups = [b.get_secret_value() for b in (s.groq_api_key_backup, s.groq_api_key_backup_2, s.groq_api_key_backup_3)
                   if b and b.get_secret_value()]
        return cls(key, s.llm_primary_model, s.llm_timeout_seconds, s.llm_max_retries, s.llm_rate_wait_seconds,
                   s.llm_request_token_cap, backups)

    def _pick(self) -> tuple[int, Any]:
        """The first key that is not resting; if all are resting, the one that frees up soonest."""
        slots = [(i, c) for i, c in enumerate((self._client, self._backup, *self._extra)) if c is not None]
        now = time.monotonic()
        free = [sc for sc in slots if _resting_until.get(sc[0], 0) <= now]
        return free[0] if free else min(slots, key=lambda sc: _resting_until.get(sc[0], 0))

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        reasoning_effort: ReasoningEffort = "medium",
        max_tokens: int = 2048,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
    ) -> LLMResult:
        if self._client is None:
            raise LLMUnavailable("not_configured", "GROQ_API_KEY is not set")

        # Groq counts prompt + max_completion_tokens against the per-minute token limit, so a request whose sum is
        # above the limit can never run. Shrink the completion allowance to fit (prompt estimated at ~3.5 chars/token).
        if self.request_token_cap:
            prompt_est = sum(len(m.get("content") or "") for m in messages) // 3.5 + 50 * len(messages)
            max_tokens = int(max(1200, min(max_tokens, self.request_token_cap - prompt_est)))
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "reasoning_effort": reasoning_effort,
        }
        if json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": json_schema},
            }

        start = time.perf_counter()
        waited = 0.0
        while True:
            slot, client = self._pick()
            try:
                resp = await client.chat.completions.create(**kwargs)
                break
            except groq.RateLimitError as e:
                retry = e.response.headers.get("retry-after") if e.response is not None else None
                retry_s = float(retry) if retry else 15.0
                _resting_until[slot] = time.monotonic() + retry_s
                if self._pick()[0] != slot and _resting_until.get(self._pick()[0], 0) <= time.monotonic():
                    continue  # another key is free: use it now (it rests too if it fails, so no ping-pong)
                if "per day" in str(e.message):  # the daily quota: waiting a minute will not help
                    raise LLMUnavailable(
                        "rate_limited", f"the free AI quota for today is used up; it frees up again in about "
                                        f"{max(1, round(retry_s / 60))} minute(s)", retry_s) from e
                pause = min(retry_s, 30.0) + 0.5
                if retry_s <= 60 and waited + pause <= self.rate_wait_s:
                    waited += pause
                    await asyncio.sleep(pause)
                    continue
                raise LLMUnavailable("rate_limited", "Groq rate limit reached", retry_s if retry else None) from e
            except groq.APITimeoutError as e:
                raise LLMUnavailable("timeout", "Groq did not answer in time") from e
            except groq.APIConnectionError as e:
                raise LLMUnavailable("unreachable", "Cannot reach Groq") from e
            except groq.InternalServerError as e:
                raise LLMUnavailable("server_error", f"Groq server error ({e.status_code})") from e
            except groq.APIStatusError as e:
                raise LLMError(f"Groq rejected the request ({e.status_code}): {e.message}") from e

        latency_ms = int((time.perf_counter() - start) * 1000)
        choice = resp.choices[0]
        usage = resp.usage
        return LLMResult(
            text=choice.message.content or "",  # message.reasoning is deliberately dropped
            model=resp.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
        )
