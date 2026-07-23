# ADR-0016: Split serving — ephemeral GPU for measurement, always-on CPU for the demo

**Status:** accepted (2026-07-23) — suite + Colab runner committed and smoke-tested; GPU run pending

## Context

Repositioning OpsVerse as an **LLM inference platform** (see
`docs/migration-plan.md`) makes vLLM-class serving evidence load-bearing: continuous
batching, PagedAttention, prefix caching, and a quantization frontier are the claims the
target roles actually screen for.

Two project constraints collide with that:

1. **Free tiers only**, training and serving off this machine.
2. The always-on public endpoint (`infra/oracle-opslm/`) is an Oracle Free Tier **ARM
   CPU** VM. It can run Ollama/llama.cpp; it can never run CUDA, and therefore never
   vLLM, AWQ, GPTQ, or produce a GPU-utilization metric.

A single serving path cannot satisfy both "always on, $0" and "demonstrates GPU
inference engineering". Previous attempts to paper over this left `benchmarks/README.md`
with `⏳ pending` on every row that mattered — the platform had a measuring instrument
and no readings.

## Decision

**Two serving paths with different jobs**, joined by the one OpenAI-compatible surface
that ADR-0011 already established.

| Path | Hardware | Job | Lifetime |
|---|---|---|---|
| **vLLM** | Colab T4 (free) | produce measurements | ephemeral, per session |
| **Ollama / llama.cpp** | Oracle ARM (free) | serve the public demo | always on |

- **Measurement is a committed artifact, not a live service.** `benchmarks/run_suite.py`
  writes one JSON per (engine, quantization) — stamped with GPU, engine version, and
  timestamp — into `benchmarks/results/`. `benchmarks/report.py` renders the comparison
  tables and the Pareto frontier from those files. The GPU disappears when the Colab
  session ends; the evidence does not.
- **Both paths are measured by the same suite.** Ollama-on-GPU is benchmarked in the same
  session as vLLM, so the cross-engine comparison isolates the engine rather than
  confounding it with hardware.
- **Probes ship with controls.** Prefix caching is measured cold-vs-warm with the cache
  on, then re-run with `--no-enable-prefix-caching`; the *difference between runs* is the
  claim. Guided decoding is measured off-then-on. A single warm measurement is
  indistinguishable from warm-up and is not evidence.
- **AWQ is calibrated on `data/sft/train.jsonl`** — the project's own in-domain data.
  AWQ chooses which weight channels to protect from observed activations, so calibrating
  on the traffic the model will serve is the reason to quantize in-house rather than
  download someone else's build.
- **Configurations without a quality score are excluded from the frontier**, not
  defaulted. A speed-only frontier recommends the smallest quantization by construction,
  which is the exact error the frontier exists to prevent.

## Consequences

- **The public demo and the benchmark numbers describe different hardware**, and every
  artifact must say so. The demo endpoint's latency is the CPU path; the report's latency
  is the T4 path. Conflating them would be the most tempting dishonesty available here.
- **No tensor-parallel or multi-GPU numbers will ever exist** under this decision. Those
  get explained as limitations, never claimed — consistent with the rerank-off and
  sparse-leakage calls.
- Re-measuring after a model change costs one Colab session (~90 min), not a standing
  GPU bill. The notebook is turnkey precisely because the session is timed.
- vLLM is deliberately **left unpinned** in the notebook for the first run; the resolved
  version is captured into each result file's metadata via `--notes`. Pinning follows the
  first successful run rather than guessing a version that may not resolve on Colab.
- Turing (T4, sm_75) has **no bfloat16** — every server launches with `--dtype float16`,
  and AWQ uses the plain GEMM kernel rather than Marlin (Ampere+). Both are noted at the
  launch site, since a future Ampere run should drop them.
- The networked path is smoke-tested against a mock OpenAI-compatible server, so a timed
  Colab session is not the first place the code runs.
