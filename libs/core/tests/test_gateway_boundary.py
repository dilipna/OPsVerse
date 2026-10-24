import math

import pytest

from opsverse_core.gateway import BudgetExceededError, LLMGateway
from opsverse_core.llm import LLMResult


class CounterClient:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages):
        self.calls += 1
        return LLMResult(text="synthetic", model="test", cost_usd=0.01)

    async def stream(self, messages):
        self.calls += 1
        yield LLMResult(text="synthetic", model="test", cost_usd=0.01)


class BadCounter:
    def __init__(self, value):
        self.value = value

    async def get(self, key):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value

    async def set(self, key, value, ex=None):
        raise AssertionError("an invalid counter must not reach cache writes")

    async def incrbyfloat(self, key, amount):
        raise AssertionError("an invalid counter must not reach spend writes")

    async def expire(self, key, seconds):
        raise AssertionError("an invalid counter must not reach expiry writes")


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "not-a-number", OSError("offline")])
@pytest.mark.parametrize("stream", [False, True])
async def test_unknown_budget_cannot_authorize_a_provider_call(value, stream):
    client = CounterClient()
    gateway = LLMGateway(
        client, BadCounter(value), model_id="test", cache_enabled=False, daily_budget_usd=1
    )
    with pytest.raises(BudgetExceededError):
        if stream:
            _ = [e async for e in gateway.stream([{"role": "user", "content": "synthetic"}])]
        else:
            await gateway.complete([{"role": "user", "content": "synthetic"}])
    assert client.calls == 0


async def test_absent_counter_cannot_authorize_budgeted_provider_call():
    client = CounterClient()
    gateway = LLMGateway(client, None, model_id="test", daily_budget_usd=1)
    with pytest.raises(BudgetExceededError):
        await gateway.complete([])
    assert client.calls == 0


@pytest.mark.parametrize("budget", [math.nan, math.inf, -1])
def test_invalid_configuration_cannot_disable_a_budget(budget):
    with pytest.raises(ValueError):
        LLMGateway(CounterClient(), None, model_id="test", daily_budget_usd=budget)
