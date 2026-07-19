"""LLM gateway as a library layer over the LiteLLM client (Phase 6, ADR-0008).

Adds the gateway concerns that matter under a free-tier budget — an
exact-match response cache and a daily spend kill-switch — without running a
separate proxy process. Both degrade to pass-through when Redis is
unavailable, so the gateway can never take the chat path down.

The client interface (complete/stream) is unchanged, so ChatService and the
eval harnesses use the gateway exactly where they used the raw client.
"""

import contextlib
import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from opsverse_core.llm import LLMDelta, LLMResult, LLMStreamEvent, Message


class BudgetExceededError(Exception):
    """Daily spend ceiling reached; the kill-switch refused the call."""


class SupportsLLM(Protocol):
    async def complete(self, messages: list[Message]) -> LLMResult: ...
    def stream(self, messages: list[Message]) -> AsyncIterator[LLMStreamEvent]: ...


class RedisLike(Protocol):
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: str, ex: int | None = ...) -> Any: ...
    async def incrbyfloat(self, key: str, amount: float) -> Any: ...
    async def expire(self, key: str, seconds: int) -> Any: ...


@dataclass(slots=True)
class GatewayStats:
    cache_hits: int = 0
    cache_misses: int = 0
    budget_blocks: int = 0


def _cache_key(model_id: str, messages: list[Message]) -> str:
    payload = json.dumps({"m": model_id, "msgs": messages}, sort_keys=True, default=str)
    return "gw:cache:" + hashlib.sha256(payload.encode()).hexdigest()


def _budget_key(now: datetime) -> str:
    return f"gw:spend:{now.astimezone(UTC).strftime('%Y-%m-%d')}"


class LLMGateway:
    """Wraps an LLM client with a Redis response cache and a budget guard."""

    def __init__(
        self,
        client: SupportsLLM,
        redis: RedisLike | None,
        *,
        model_id: str,
        cache_enabled: bool = True,
        cache_ttl_s: int = 24 * 3600,
        daily_budget_usd: float = 0.0,
    ) -> None:
        self._client = client
        self._redis = redis
        self._model_id = model_id  # identifies the model-chain for cache keying
        self._cache_enabled = cache_enabled and redis is not None
        self._cache_ttl_s = cache_ttl_s
        self._daily_budget_usd = daily_budget_usd
        self.stats = GatewayStats()

    async def _spent_today(self) -> float:
        if self._redis is None:
            return 0.0
        try:
            raw = await self._redis.get(_budget_key(datetime.now(UTC)))
            return float(raw) if raw is not None else 0.0
        except Exception:
            return 0.0  # a broken budget counter must not block the platform

    async def _check_budget(self) -> None:
        if self._daily_budget_usd <= 0:
            return
        if await self._spent_today() >= self._daily_budget_usd:
            self.stats.budget_blocks += 1
            raise BudgetExceededError(
                f"daily budget ${self._daily_budget_usd:.2f} reached; call refused"
            )

    async def _record_spend(self, cost_usd: float | None) -> None:
        if self._redis is None or not cost_usd:
            return
        with contextlib.suppress(Exception):
            key = _budget_key(datetime.now(UTC))
            await self._redis.incrbyfloat(key, cost_usd)
            await self._redis.expire(key, 48 * 3600)  # ledger is the durable record

    async def _cache_get(self, key: str) -> LLMResult | None:
        if not self._cache_enabled or self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
        except Exception:
            return None
        if raw is None:
            return None
        data = json.loads(raw)
        # a cache hit is genuinely free — cost is zeroed so the ledger and
        # budget reflect that no provider call happened
        return LLMResult(
            text=data["text"],
            model=data["model"] + " (cached)",
            prompt_tokens=data.get("prompt_tokens"),
            completion_tokens=data.get("completion_tokens"),
            cost_usd=0.0,
        )

    async def _cache_put(self, key: str, result: LLMResult) -> None:
        if not self._cache_enabled or self._redis is None:
            return
        with contextlib.suppress(Exception):
            await self._redis.set(
                key,
                json.dumps(
                    {
                        "text": result.text,
                        "model": result.model,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                    }
                ),
                ex=self._cache_ttl_s,
            )

    async def complete(self, messages: list[Message]) -> LLMResult:
        key = _cache_key(self._model_id, messages)
        cached = await self._cache_get(key)
        if cached is not None:
            self.stats.cache_hits += 1
            return cached
        self.stats.cache_misses += 1
        await self._check_budget()
        result = await self._client.complete(messages)
        await self._record_spend(result.cost_usd)
        await self._cache_put(key, result)
        return result

    async def stream(self, messages: list[Message]) -> AsyncIterator[LLMStreamEvent]:
        """Stream with cache + budget. A cache hit replays the stored answer as
        a single delta then a zero-cost result — same event shape the caller
        already handles, so streaming semantics are preserved."""
        key = _cache_key(self._model_id, messages)
        cached = await self._cache_get(key)
        if cached is not None:
            self.stats.cache_hits += 1
            if cached.text:
                yield LLMDelta(text=cached.text)
            yield cached
            return
        self.stats.cache_misses += 1
        await self._check_budget()
        final: LLMResult | None = None
        async for event in self._client.stream(messages):
            if isinstance(event, LLMResult):
                final = event
            yield event
        if final is not None:
            await self._record_spend(final.cost_usd)
            await self._cache_put(key, final)
