# ADR-0014: Inference-optimization techniques, measured in the lab

**Status:** accepted (2026-07-20) — algorithms + harness committed and tested; served numbers pending OpsLM

## Context

Phase 7's inference lab (ADR-0011) can measure throughput/latency of a served
model but exercises no **inference-optimization techniques** — the core of an
LLM-inference-engineer skillset. The goal here is to demonstrate command of the
techniques that actually move production serving metrics, held to this project's
bar: *a technique you cannot measure is a vibe.* So each one ships as (a) a
correct, unit-tested implementation or harness capability now, and (b) a slot in
the benchmark/eval that fills with real numbers during the OpsLM serving session.

Selection criterion: techniques that are **high-signal for the role** *and* land
on the model this project actually produces — OpsLM, a **QLoRA adapter** served
as a quantized GGUF. That immediately makes multi-LoRA serving and quantization
frontiers first-class rather than generic.

## Decision

Five techniques, each with an owner artifact and a measured payoff:

| Technique | Committed artifact (tested offline) | Measured payoff (on served OpsLM) |
|---|---|---|
| **Speculative decoding** (prompt-lookup / n-gram) | `techniques/speculative.py` — lossless draft/verify driver + acceptance & speedup-proxy meter | acceptance rate + tokens/s uplift vs baseline, in the harness |
| **Guided / structured decoding** | `techniques/constrained.py` — schema-FSM token masking | `json_parse_rate`→1.0 and field-accuracy via the ADR-0012 structured evalset, guided-on vs off |
| **Quantization frontier** | `techniques/frontier.py` — Pareto + knee over (latency, quality) | FP16/Q8/Q4 latency (harness) × quality (Phase-4 eval) → which quant to serve |
| **Prefix caching** (APC / RadixAttention) | `harness.shared_prefix_prompts` + `prefix_cache_speedup` | TTFT drop on shared-prefix (RAG system-prompt) requests |
| **Continuous batching + TPOT** | `harness` TTFT / **inter-token latency** / system-throughput sweep | throughput scaling vs concurrency; ITL as the steady-state decode metric |

### Why these, and why implement rather than just flag

- **Speculative decoding** is the headline decode-latency technique. The
  prompt-lookup variant needs *no draft model*, which suits RAG/tool-use output
  (repeated paths, keys, boilerplate). Implementing it — and unit-testing that it
  is **token-identical to greedy** (losslessness) while using **fewer target
  forward passes** (amortization) — proves understanding a config flag can't. On
  vLLM it becomes `--speculative-model [ngram]`; acceptance rate is the number
  that transfers from our toy to the GPU.
- **Guided decoding** ties straight into the existing structured-output eval
  (ADR-0012): masking the vocabulary to a grammar makes `json_parse_rate` 1.0 *by
  construction*. We already have the evalset to prove it, so the technique is
  measurable the moment OpsLM serves.
- **Quantization** is unavoidable for OpsLM (it ships as GGUF Q4_K_M). The honest
  artifact is not "we quantized" but the **frontier**: latency vs quality with the
  dominated configs dropped and a recommended knee — exactly the call an inference
  engineer is paid to make.
- **Prefix caching** matters precisely for RAG, where every request carries the
  same long system/context prefix; the probe makes the TTFT win explicit.
- **Continuous batching** is what the concurrency sweep already reveals; adding
  **inter-token latency (TPOT)** separates prefill cost (TTFT) from steady-state
  decode — the two knobs these techniques trade against.

### Boundaries (kept honest)

- The **offline meters are proxies**, clearly labelled: speedup-proxy counts
  target forward passes, not GPU wall-clock; the constrained decoder is
  character-level over a toy vocab. The *transferable* quantities — acceptance
  rate, parse rate, the frontier shape, TTFT deltas — are what the served run
  reports. This mirrors ADR-0011's "math is unit-tested; numbers come from the GPU".
- **Not implemented** (deferred, documented): draft-*model* and self-speculative
  decoding (Medusa/EAGLE), integer/nested guided-decoding grammars, tensor
  parallelism, and paged-attention internals — all either need multi-GPU we don't
  have or add surface without changing the story a single-T4 demo can measure.
  Revisit triggers noted in `benchmarks/README.md`.

## Consequences

- The inference lab now demonstrates *techniques*, not just a stopwatch, and each
  is falsifiable against a committed test or evalset.
- Every measured number still waits on OpsLM being served (Phase 5). Until then
  this is committed-and-tested scaffolding — stated plainly, not overclaimed.
- Adding a technique later (e.g. a real draft model) is a new `techniques/` module
  plus a harness flag, not a redesign — same extensibility as the engine-agnostic
  harness.
