import pytest

from opsverse_core.gateway import BudgetExceededError, LLMGateway
from opsverse_core.llm import LLMDelta, LLMResult


class FakeRedis:
    """Minimal async Redis stand-in with the ops the gateway uses."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.floats: dict[str, float] = {}

    async def get(self, key: str):
        if key in self.floats:
            return str(self.floats[key])
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value

    async def incrbyfloat(self, key: str, amount: float):
        self.floats[key] = self.floats.get(key, 0.0) + amount
        return self.floats[key]

    async def expire(self, key: str, seconds: int):
        return True


class FakeLLM:
    def __init__(self, text="hello world", cost=0.01):
        self.text = text
        self.cost = cost
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(self, messages):
        self.complete_calls += 1
        return LLMResult(text=self.text, model="fake/model", cost_usd=self.cost)

    async def stream(self, messages):
        self.stream_calls += 1
        yield LLMDelta(text=self.text)
        yield LLMResult(text=self.text, model="fake/model", cost_usd=self.cost)


MSGS = [{"role": "user", "content": "hi"}]


async def test_complete_caches_second_call():
    llm = FakeLLM()
    gw = LLMGateway(llm, FakeRedis(), model_id="fake/model")
    first = await gw.complete(MSGS)
    second = await gw.complete(MSGS)
    assert llm.complete_calls == 1  # second served from cache
    assert gw.stats.cache_hits == 1 and gw.stats.cache_misses == 1
    assert first.cost_usd == 0.01
    assert second.cost_usd == 0.0  # a cache hit is free
    assert second.model.endswith("(cached)")


async def test_stream_cache_replays_as_single_delta():
    llm = FakeLLM(text="streamed answer")
    gw = LLMGateway(llm, FakeRedis(), model_id="fake/model")
    _ = [e async for e in gw.stream(MSGS)]
    events = [e async for e in gw.stream(MSGS)]
    assert llm.stream_calls == 1  # second call hit cache
    deltas = [e for e in events if isinstance(e, LLMDelta)]
    results = [e for e in events if isinstance(e, LLMResult)]
    assert "".join(d.text for d in deltas) == "streamed answer"
    assert results[-1].cost_usd == 0.0


async def test_budget_kill_switch_blocks_when_exceeded():
    redis = FakeRedis()
    llm = FakeLLM(cost=1.0)
    gw = LLMGateway(llm, redis, model_id="fake/model", daily_budget_usd=1.5)
    # first call spends 1.0 (under 1.5, allowed), unique messages avoid cache
    await gw.complete([{"role": "user", "content": "q1"}])
    # now 1.0 spent >= ... still under 1.5, so a second distinct call is allowed
    await gw.complete([{"role": "user", "content": "q2"}])
    # 2.0 spent now exceeds 1.5 -> third distinct call is refused
    with pytest.raises(BudgetExceededError):
        await gw.complete([{"role": "user", "content": "q3"}])
    assert gw.stats.budget_blocks == 1


async def test_pass_through_when_redis_none():
    llm = FakeLLM()
    gw = LLMGateway(llm, None, model_id="fake/model", daily_budget_usd=0.01)
    # no redis: no cache, no budget enforcement, never raises
    r1 = await gw.complete(MSGS)
    r2 = await gw.complete(MSGS)
    assert llm.complete_calls == 2
    assert r1.cost_usd == r2.cost_usd == 0.01
