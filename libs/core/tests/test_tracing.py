from opsverse_core.tracing import NullTracer, build_tracer


def test_null_tracer_is_total_noop():
    tracer = NullTracer()
    assert tracer.enabled is False
    trace = tracer.trace("chat", input="hi")
    # spans support both context-manager and explicit end, all no-ops
    with trace.span("retrieval", input="q") as span:
        span.update(output=[1, 2, 3])
    trace.span("generation").end()
    trace.update(output="done")
    tracer.flush()  # must not raise


def test_build_tracer_returns_null_when_no_host():
    assert isinstance(build_tracer(None, "pk", "sk"), NullTracer)
    assert isinstance(build_tracer("", "pk", "sk"), NullTracer)


def test_build_tracer_never_raises_on_bad_host():
    # a malformed host must degrade to NullTracer, never crash the app
    tracer = build_tracer("http://nonexistent.invalid:1", "pk", "sk")
    # whatever it returns, using it must be safe
    tracer.trace("chat").span("x").end()
    tracer.flush()
