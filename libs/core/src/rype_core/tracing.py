"""Request tracing over Langfuse (Phase 8, ADR-0010).

A thin, dependency-light facade so the chat pipeline can emit a trace with
nested spans (retrieval, rerank, gateway/cache, generation) carrying the
attributes that make an LLM request debuggable — chunk ids + scores, token
counts, cost, cache hit, degradation — without coupling libs/rag to the
Langfuse SDK or requiring Langfuse to be up.

`NullTracer` is the default: every method is a no-op, so tests and the core
(non-`full`) stack never touch Langfuse. `LangfuseTracer` is used only when a
host is configured. Tracing must never break a request: all SDK calls are
guarded.
"""

from __future__ import annotations

import contextlib
from types import TracebackType
from typing import Any, Protocol


class Span(Protocol):
    def update(self, **kwargs: Any) -> None: ...
    def end(self, **kwargs: Any) -> None: ...


class _NullSpan:
    def update(self, **kwargs: Any) -> None:
        return None

    def end(self, **kwargs: Any) -> None:
        return None

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class Trace(Protocol):
    def span(self, name: str, **kwargs: Any) -> Any: ...
    def update(self, **kwargs: Any) -> None: ...


class _NullTrace:
    def span(self, name: str, **kwargs: Any) -> _NullSpan:
        return _NullSpan()

    def update(self, **kwargs: Any) -> None:
        return None


class Tracer(Protocol):
    def trace(self, name: str, **kwargs: Any) -> Any: ...
    def flush(self) -> None: ...


class NullTracer:
    """Default tracer: everything is a no-op."""

    enabled = False

    def trace(self, name: str, **kwargs: Any) -> _NullTrace:
        return _NullTrace()

    def flush(self) -> None:
        return None


class _LangfuseSpan:
    """Wraps a Langfuse span; guards every call and supports `with`."""

    def __init__(self, span: Any) -> None:
        self._span = span

    def update(self, **kwargs: Any) -> None:
        with contextlib.suppress(Exception):
            self._span.update(**kwargs)

    def end(self, **kwargs: Any) -> None:
        with contextlib.suppress(Exception):
            self._span.end(**kwargs)

    def __enter__(self) -> _LangfuseSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # record failures on the span, then close it
        if exc is not None:
            name = exc_type.__name__ if exc_type else ""
            self.update(level="ERROR", status_message=f"{name}: {exc}")
        self.end()


class _LangfuseTrace:
    def __init__(self, trace: Any) -> None:
        self._trace = trace

    def span(self, name: str, **kwargs: Any) -> _LangfuseSpan:
        try:
            return _LangfuseSpan(self._trace.span(name=name, **kwargs))
        except Exception:
            return _LangfuseSpan(None)

    def update(self, **kwargs: Any) -> None:
        with contextlib.suppress(Exception):
            self._trace.update(**kwargs)


class LangfuseTracer:
    """Real tracer. Constructed only when a Langfuse host is configured."""

    enabled = True

    def __init__(self, host: str, public_key: str, secret_key: str) -> None:
        from langfuse import Langfuse  # deferred: only imported when enabled

        self._client = Langfuse(host=host, public_key=public_key, secret_key=secret_key)

    def trace(self, name: str, **kwargs: Any) -> _LangfuseTrace:
        try:
            return _LangfuseTrace(self._client.trace(name=name, **kwargs))
        except Exception:
            return _LangfuseTrace(None)

    def flush(self) -> None:
        with contextlib.suppress(Exception):
            self._client.flush()


def build_tracer(host: str | None, public_key: str, secret_key: str) -> NullTracer | LangfuseTracer:
    """Return a real tracer when a host is set, else the no-op tracer."""
    if not host:
        return NullTracer()
    try:
        return LangfuseTracer(host, public_key, secret_key)
    except Exception:
        # a broken Langfuse config must never disable the platform
        return NullTracer()
