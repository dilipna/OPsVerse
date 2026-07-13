"""Thin async LLM client over the litellm SDK.

Phase 6 replaces this with the LiteLLM proxy; the interface here is
deliberately OpenAI-shaped (messages in, deltas/result out) so that swap is
a configuration change, not a rewrite.

Fallback semantics: models are tried in order, but only while the stream has
not produced any text yet. Once the first delta reaches the caller we cannot
transparently switch providers (the client would see a spliced answer), so a
mid-stream failure surfaces as an error instead.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

Message = dict[str, str]


class LLMError(Exception):
    """All configured models failed (or one failed mid-stream)."""


@dataclass(slots=True)
class LLMResult:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(slots=True)
class LLMDelta:
    text: str


LLMStreamEvent = LLMDelta | LLMResult


class LiteLLMClient:
    def __init__(
        self,
        models: list[str],
        api_keys: dict[str, str | None],
        *,
        timeout_s: float = 45.0,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        reasoning_effort: str | None = None,
    ):
        if not models:
            raise ValueError("at least one model is required")
        self._models = models
        self._api_keys = api_keys
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort

    def _api_key_for(self, model: str) -> str | None:
        provider = model.split("/", 1)[0]
        return self._api_keys.get(provider)

    def _call_kwargs(self, model: str, messages: list[Message]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "api_key": self._api_key_for(model),
            "timeout": self._timeout_s,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if self._reasoning_effort is not None:
            kwargs["reasoning_effort"] = self._reasoning_effort
        return kwargs

    async def complete(self, messages: list[Message]) -> LLMResult:
        import litellm  # deferred: importing litellm costs ~1s at process start

        last_exc: Exception | None = None
        for model in self._models:
            try:
                resp = await litellm.acompletion(**self._call_kwargs(model, messages))
                return _result_from_response(resp, model)
            except Exception as exc:  # provider errors span many exception types
                last_exc = exc
        raise LLMError(f"all models failed: {self._models}") from last_exc

    async def stream(self, messages: list[Message]) -> AsyncIterator[LLMStreamEvent]:
        """Yield LLMDelta events, then exactly one final LLMResult."""
        import litellm

        last_exc: Exception | None = None
        for model in self._models:
            started = False
            text_parts: list[str] = []
            usage = None
            try:
                # cast: litellm types the stream=True return as ModelResponse,
                # but it is an async iterator of chunks (CustomStreamWrapper).
                resp = cast(
                    AsyncIterator[Any],
                    await litellm.acompletion(
                        **self._call_kwargs(model, messages),
                        stream=True,
                        stream_options={"include_usage": True},
                    ),
                )
                async for chunk in resp:
                    delta = _delta_text(chunk)
                    if delta:
                        started = True
                        text_parts.append(delta)
                        yield LLMDelta(text=delta)
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage is not None:
                        usage = chunk_usage
            except Exception as exc:
                if started:
                    # Tokens already reached the caller; a silent provider
                    # switch would splice two answers together.
                    raise LLMError(
                        f"{model} failed mid-stream: {type(exc).__name__}: {exc}"
                    ) from exc
                last_exc = exc
                continue
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            yield LLMResult(
                text="".join(text_parts),
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=_cost_usd(model, prompt_tokens, completion_tokens),
            )
            return
        raise LLMError(
            f"all models failed: {self._models}; last: {type(last_exc).__name__}: {last_exc}"
        ) from last_exc


def _delta_text(chunk: Any) -> str:
    choices = getattr(chunk, "choices", None)
    if not choices:
        return ""
    return getattr(choices[0].delta, "content", None) or ""


def _result_from_response(resp: Any, model: str) -> LLMResult:
    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    return LLMResult(
        text=resp.choices[0].message.content or "",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=_cost_usd(model, prompt_tokens, completion_tokens),
    )


def _cost_usd(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    """Best-effort cost from litellm's price table; None when unknown."""
    import litellm

    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
        )
        return prompt_cost + completion_cost
    except Exception:
        return None
