# ADR-0011: One OpenAI-compatible harness for the inference lab

**Status:** accepted (2026-07-18) — harness committed + tested; GPU run pending

## Context

Phase 7 compares Ollama, vLLM, and SGLang serving OpsLM on a free GPU. The
risk with multi-engine benchmarks is that per-engine measurement code makes
the *harness* a variable — a difference in how each client counts tokens or
times first-token would masquerade as an engine difference.

## Decision

**One engine-agnostic harness** targeting the **OpenAI-compatible
`/v1/chat/completions`** endpoint that all three engines expose. Same client,
same streaming parse, same metric math for every engine; only the server
under test changes.

- **Measurement math is pure and unit-tested** (`percentile`, `summarize`,
  `tokens_per_s`) — the part that must be correct regardless of GPU is
  verified in CI, not just "run once and eyeball".
- **Metrics chosen to expose the real serving behavior:** TTFT and per-request
  tokens/sec show single-stream latency; **system throughput** (total output
  tokens ÷ wall-clock) at a concurrency sweep is what reveals continuous
  batching — a speed-only single-request table would hide the main event.
- **Quality is measured alongside speed** by pointing the existing Phase-4
  eval harness at each served/quantized model, yielding a quality-vs-cost
  curve. Reusing the eval gate keeps "faster" honest about "and still good".

## Consequences

- Adding a fourth engine later is a new notebook, not new harness code.
- The absolute output-token count is approximated by streamed-chunk count
  (documented); it is consistent across engines, so the *comparison* holds.
- Single-T4 limits (no tensor parallelism) are disclosed and explained in the
  report rather than faked — consistent with the project's honesty bar
  (cf. the rerank-off and sparse-leakage calls).
- The harness needs OpsLM (Phase 5) served somewhere; until the training run
  happens, Phase 7 is committed-and-tested scaffolding, not measured numbers —
  stated plainly in `benchmarks/README.md`.
