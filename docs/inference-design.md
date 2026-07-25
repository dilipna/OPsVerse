# Inference System — Technical Design

How OpsVerse serves a fine-tuned model in production, and why each choice was
made. Every performance claim here is a **measured** number from
[`docs/reports/inference-benchmark-v1.md`](reports/inference-benchmark-v1.md)
(Tesla T4, raw JSON in [`benchmarks/results/`](../benchmarks/results/));
forward-looking scaling that a single free T4 cannot demonstrate is labelled
**[design]** and never dressed up as a result.

---

## 1. System architecture

The serving layer sits behind one **OpenAI-compatible surface** (`/v1/chat/completions`),
which is the single most important design decision: the gateway, the benchmark
harness, and the eval suite all speak it, so the engine underneath can change
without touching anything above it (ADR-0004, ADR-0011).

```
        FastAPI gateway  (libs/core: cache · budget · fallback · tracing)
                 │  OpenAI-shaped messages in, SSE deltas out
                 ▼
        ┌──────────────── OpenAI-compatible /v1 surface ───────────────┐
        │                                                              │
  vLLM (Colab T4, ephemeral)                        Ollama / llama.cpp (Oracle ARM, always-on)
  PagedAttention · continuous batching              GGUF Q4 · single-stream · the public demo
  prefix cache · guided decoding · FP16/AWQ         no continuous batching
        │                                                              │
        └───────────────────────► OpsLM-v1 ◄───────────────────────────┘
                          Qwen3-4B QLoRA (r=16)
```

**Two serving paths with different jobs** (ADR-0016). A single path cannot be both
"always-on and free" *and* "demonstrates GPU inference engineering": the free
always-on host (Oracle Free Tier) is ARM CPU and can never run CUDA/vLLM. So
measurement runs on an **ephemeral Colab T4** and is captured as a committed
artifact (raw JSON + report), while the **always-on demo** runs Ollama on CPU.
Every artifact states which hardware it describes — the demo's latency is the CPU
path; the report's latency is the T4 path, and conflating them would be the most
tempting dishonesty available here.

## 2. Inference flow (one request)

A generation request is two regimes with very different cost, and the platform
measures them separately because they are moved by different optimizations:

1. **Prefill** — the prompt is processed in one forward pass; its output is
   **TTFT** (time to first token). Dominated by prompt length and by whether the
   prompt's prefix is already in the KV cache. *Measured: vLLM FP16 TTFT p50
   **59 ms** at concurrency 1.*
2. **Decode** — tokens are produced one at a time, each attending to the growing
   KV cache; the per-token gap is **ITL / TPOT** (inter-token latency). This is
   what continuous batching and speculative decoding move; TTFT is not. *Measured:
   vLLM FP16 ITL p50 ≈ **50–60 ms**.*

Tokens stream back over SSE as they decode. The harness measures TTFT from the
first streamed chunk and reconstructs ITL as `(latency − TTFT) / (tokens − 1)`,
so the two regimes never get averaged into one misleading "latency" figure.

**KV cache & PagedAttention.** The dominant memory cost during decode is the KV
cache (per-token key/value tensors for every layer). vLLM's PagedAttention stores
it in fixed-size pages instead of one contiguous buffer, which is what makes the
next two features possible — pages can be shared (prefix caching) and packed
across requests (continuous batching) without contiguous-allocation waste.

**Prefix caching.** Requests that share a long prefix (a fixed system prompt, or a
retrieved document reused across turns — exactly the RAG workload) reuse the
prefix's KV pages, so the second+ request skips prefilling it. *Measured, with a
control: vLLM **47.8%** TTFT reduction with the cache on vs **0.0%** with
`--no-enable-prefix-caching` — the control run is what proves the number is the
cache and not warm-up.*

**Guided decoding.** For structured output, the engine masks the token logits to
only those the JSON schema permits, so the result parses by construction. *Measured:
vLLM JSON parse rate **0 → 1.00** (off → on); Ollama's OpenAI endpoint does not
honor `response_format`, so it cannot be constrained (0 → 0.0).*

## 3. Scaling strategy

**Continuous batching is the scaling story on a single device.** Instead of
running requests one at a time, the engine interleaves many requests' decode steps
into shared forward passes, admitting and retiring them token-by-token. The payoff
is measured directly by sweeping concurrency 1 → 16:

| Config | Throughput scaling (1→16) | p95 latency inflation | What it means |
|---|---|---|---|
| **vLLM FP16** | **13.4×** | **0.81×** | concurrent requests share decode passes — throughput scales while tail latency *holds* |
| **Ollama Q4** | 0.89× | 16.0× | no continuous batching — requests serialize, throughput flat, latency grows linearly |

Same model, same T4, same harness: the delta is the engine. This is the clearest
evidence in the project of *why* a dedicated serving engine matters. (Note the
honest nuance: Ollama is **faster single-stream** — 3.6 s vs 13.0 s at concurrency
1, because Q4 is lighter than FP16 — but collapses under load. The engine choice is
a load-shape decision, not a blanket "faster/slower".)

**Beyond one T4 [design].** A single free T4 cannot demonstrate the next tiers, so
they are described, not claimed:
- **Tensor parallelism** — shard a model too large for one GPU across devices
  (`--tensor-parallel-size`); needs ≥2 GPUs.
- **Horizontal replicas** — stateless vLLM replicas behind a load balancer; the
  gateway already speaks the OpenAI surface, so this is a deployment change, not a
  code change ([`infra/k8s`](../infra/k8s/) has the manifests).
- **KV-cache pressure** — the real ceiling on concurrency is KV memory, not FLOPs;
  `--gpu-memory-utilization` and `--max-model-len` are the levers, and quantized
  KV / paged offload are the next steps.

## 4. Failure handling

The serving path is designed to fail *legibly*, consistent with the RAG stack's
degradation ladder:

- **Server not ready.** The benchmark/serve harness blocks on `/v1/models` and
  runs a single smoke request before load-testing, so "up but not generating"
  (e.g. a bad launch flag) fails in seconds with the real HTTP error rather than
  as 32 silent timeouts.
- **Generation failure.** The gateway tries models in order, but only until the
  first token reaches the client — a mid-stream provider failure surfaces as an
  error rather than silently splicing two answers together (`libs/core/llm.py`).
- **Cold start / OOM.** vLLM reserves KV memory at launch (`--gpu-memory-utilization
  0.85`); if another process holds VRAM the engine fails fast at startup rather
  than thrashing. (Observed live: a still-running vLLM starved a co-located Ollama
  to 80% CPU — the fix is to free the GPU before switching engines, now enforced.)
- **Quality floor under quantization.** Speed is never accepted without its quality
  cost: each quant is meant to re-run the Phase-4 eval, and the Pareto frontier
  excludes any config without a quality score so "faster" can't silently mean
  "worse" (`benchmarks/report.py`).

## 5. Tradeoffs

| Decision | Chosen | Cost accepted | Why |
|---|---|---|---|
| **Serving engine** | vLLM for measurement, Ollama for the always-on demo | two paths to keep honest about | free-tier ARM can't run CUDA; the split is the only way to have both always-on-free and real GPU numbers (ADR-0016) |
| **Quantization** | FP16 benchmarked; GGUF Q4 serves the demo | Q4 trades some quality for ~4× smaller + faster single-stream | Q4 fits the CPU demo host and wins single-stream; FP16 is the fidelity reference. The frontier (pending a quality axis) picks the knee, not the fastest |
| **AWQ** | dropped | one fewer quant on the frontier | AutoAWQ is unmaintained past torch 2.6 and threw cascading conflicts on Colab's torch 2.11; recorded honestly rather than forced |
| **Abstraction** | one OpenAI-compatible surface | a thin indirection layer | swapping engines/quants becomes config, not a rewrite; one harness measures them all |
| **Measurement** | committed JSON + generated report | must re-run to refresh | a latency number without committed provenance (hardware, n, date) is a rumour, not a result |

## 6. What is measured vs. designed

| Claim | Status |
|---|---|
| Continuous batching 13.4× / prefix cache 47.8% / guided 0→1.0 | **measured** (T4, committed JSON) |
| Cross-engine contrast (vLLM vs Ollama) | **measured** (same T4, same harness) |
| Before/after eval (base vs OpsLM), quant→quality frontier | **pending** — needs a served-model eval pass |
| Tensor parallelism, multi-replica scaling | **[design]** — a single T4 can't show it; stated, not faked |

---

*Decision records: [ADR-0004](adr/0004-chat-serving-thin-litellm-sse.md) (OpenAI-shaped
serving), [ADR-0008](adr/0008-gateway-as-library-not-proxy.md) (gateway),
[ADR-0011](adr/0011-inference-lab-openai-compatible-harness.md) (one harness),
[ADR-0014](adr/0014-inference-optimization-techniques.md) (optimization techniques),
[ADR-0016](adr/0016-split-serving-ephemeral-gpu-vs-always-on-cpu.md) (split serving).*
