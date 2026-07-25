# "Which engine is faster?" is the wrong question — measuring continuous batching on a free T4

*OpsVerse AI serves a fine-tuned DevOps model, OpsLM (Qwen3-4B). This is the story
of benchmarking two serving engines on one free GPU, the result that reversed
itself under load, and the two ways the measurement almost lied to me.*

## The setup

I had one model, two ways to serve it, and a single OpenAI-compatible harness that
doesn't care which engine is underneath: **vLLM** (FP16) and **Ollama** (the GGUF
Q4 build that runs the public demo). Same model, same Tesla T4, same prompts, same
concurrency sweep. The question I *thought* I was answering was "which is faster?"

That question has no answer. The real one does: **which is faster at what load?**

## The result that reverses itself

At concurrency 1 — one request at a time — Ollama wins, and it isn't close:

| concurrency 1 | vLLM FP16 | Ollama Q4 |
|---|---|---|
| latency p50 | 13.0 s | **3.6 s** |
| throughput | 17 tok/s | **37 tok/s** |

If I'd stopped there — and a lot of "benchmarks" do — I'd have written that Ollama
is 3.6× faster and moved on. Q4 is a lighter quantization than FP16, so single-stream
it genuinely is quicker per token.

Then I swept concurrency to 16, and the ranking inverted:

| concurrency 16 | vLLM FP16 | Ollama Q4 |
|---|---|---|
| latency p50 | **11.2 s** | 69.8 s |
| throughput | **233 tok/s** | 33 tok/s |

vLLM's throughput scaled **13.4×** from concurrency 1→16 while its p95 latency
actually *dropped* (0.81×). Ollama's throughput stayed flat — **0.89×**, slightly
*worse* — and its latency inflated **16×**. Same model, same GPU. The only variable
was the engine.

## Why: continuous batching

The mechanism is the whole point. vLLM does **continuous batching** on top of
PagedAttention: instead of running requests one at a time, it interleaves many
requests' decode steps into shared forward passes, admitting and retiring them
token-by-token. Sixteen concurrent requests mostly ride the *same* GPU passes, so
throughput scales and per-request latency barely moves.

Ollama, on this workload, has no equivalent — concurrent requests serialize. So
throughput hits a ceiling (one request's worth of GPU) and everyone else queues,
which is exactly what 16× latency inflation looks like. Ollama's TTFT told the same
story bluntly: 0.38 s at concurrency 1, **64.6 s** at concurrency 16 — that's not
compute, that's a queue.

So "which is faster" dissolves into a real engineering decision: **single-stream
tools and chat demos** are fine on Ollama; **anything that has to hold latency
under concurrent load** wants continuous batching. That's the sentence I actually
care about a hiring panel reading.

## The control that makes a number evidence

vLLM's prefix cache measured a **47.8%** TTFT reduction on requests sharing a long
prefix. Good number — and almost meaningless on its own, because a warm server is
faster for lots of reasons. So I ran the same probe with `--no-enable-prefix-caching`
and nothing else changed: **0.0%** reduction. The gap between the two runs *is* the
cache. A measurement without its control is an anecdote wearing a lab coat.

(Guided decoding got the same treatment: vLLM's JSON parse rate went 0 → 1.00 with
the schema constraint on; Ollama's endpoint doesn't honor `response_format`, so it
can't be constrained — 0 → 0.0. A real capability difference, not a tuning gap.)

## The two ways the measurement almost lied

Free-tier serving is a minefield, and two traps nearly shipped wrong numbers:

**Ollama silently ran on CPU.** The first Ollama pass looked plausible — until I
checked `ollama ps` and saw `80%/20% CPU/GPU`. The still-running vLLM server was
holding 85% of the T4, so Ollama spilled to CPU. Those "T4" latencies were CPU
latencies. The fix (free the GPU first; assert 100% offload before benchmarking) is
trivial; *checking* was the part that mattered. A number labelled "T4" that was
secretly CPU is worse than no number.

**Colab recycled the whole runtime** mid-session and wiped the result files before
I'd downloaded them. The vLLM numbers survived only because the harness prints each
result to stdout as it's produced — so I recovered them from the session transcript,
committed the file flagged `recovered_from_stdout`, and made the notebook dump every
result immediately from then on. Honest provenance beats a clean-looking file with a
story I can't defend.

## Why this matters for a production system

1. **A benchmark's job is to find the crossover, not crown a winner.** The single-
   stream ranking and the under-load ranking are opposite, and both are true. The
   deliverable is the *curve*, not a headline number.
2. **Controls turn numbers into claims.** Prefix-cache-on vs -off, guided-on vs
   -off, engine-vs-engine on identical hardware — every real finding here is a
   difference between two runs that differ in exactly one thing.
3. **Distrust results that flatter the easy path**, and *check the hardware you
   think you measured*. Both near-misses came from a number that looked fine.

*OpsVerse is built on free tiers and local compute, with an ADR for every non-trivial
decision and a measured number behind every claim. Every figure above was emitted by
`benchmarks/run_suite.py` against OpsLM-v1 on a Tesla T4; the raw JSON is committed in
`benchmarks/results/`, the report in `docs/reports/inference-benchmark-v1.md`, and the
serving design in `docs/inference-design.md`.*
