# Inference Engineering Lab (Phase 7)

Reproducible benchmarks of **vLLM vs Ollama** serving OpsLM (Qwen3-4B FP16 and
its GGUF Q4_K_M) on a free Colab T4. The comparison *is* the deliverable — this
directory holds the harness, methodology, and (once run) raw JSON; the servers
run on the GPU box, not this machine. AWQ was attempted and dropped (see below);
SGLang remains a documented future engine, not a claim.

## Status (honest)

| Piece | State |
|---|---|
| Benchmark harness (`harness.py`) | ✅ written; measurement math **unit-tested** |
| Inference techniques (`techniques/`) | ✅ implemented + **unit-tested** (speculative, guided decoding, quant frontier) |
| Session driver (`run_suite.py`) | ✅ sweep + prefix-cache/structured probes; **unit-tested + smoke-tested against a mock OpenAI server** |
| Report generator (`report.py`) | ✅ renders comparison tables + Pareto frontier from committed JSON |
| Colab runner (`notebooks/opslm_inference_bench_colab.ipynb`) | ✅ turnkey: vLLM FP16 → Ollama Q4 → control run, each with a fail-fast smoke test |
| **vLLM FP16 on T4 + prefix-cache control** | ✅ **measured** (clean run) — `docs/reports/inference-benchmark-v1.md`. 13.4× continuous-batching scaling at 0.81× latency, prefix-cache **47.8% on vs 0.0% off** (control isolates the cache), guided decoding 0→1.0 |
| Ollama Q4 cross-engine | ⏳ pending — the one remaining benchmark; needs a GPU-clean Ollama run (stop vLLM first) |
| Quality axis (Phase-4 eval) → frontier | ⏳ pending — needs a served-model eval pass |

### What the first attempted run taught us (2026-07-24)

The first live T4 session produced **no trustworthy numbers** and is recorded here
rather than hidden — three of the four issues are now fixed in code:

- **AWQ dropped.** AutoAWQ is unmaintained past torch 2.6 and threw three
  cascading dependency conflicts (torchvision, then `torchao<0.16`) against
  Colab's torch 2.11 stack; loading it also leaked GPU memory into the kernel and
  killed the next server. The FP16-vs-Q4 comparison stands without it.
- **Ollama silently ran on CPU** — its installer failed to detect the T4 (missing
  `lshw`/`pciutils`), so the "T4" latencies were CPU latencies. The notebook now
  installs the GPU deps first and verifies `ollama ps` shows GPU offload before
  trusting a number.
- **Token count read 0 on Ollama** — the harness's streamed-chunk counter didn't
  survive Ollama's delta shape. `harness.py` now requests `include_usage` and
  prefers the server-reported `completion_tokens`, verified against a mock that
  reproduces the zero-content-delta case.
- **vLLM served `/v1/models` but 400'd every chat call** — the likely missing
  chat template in the merged repo. The notebook now runs a 3-second smoke test
  after each server and auto-retries vLLM once with Qwen3's chat template,
  surfacing the real error instead of failing 32 requests silently.

Nothing here reports numbers that weren't measured. The harness is engine-
agnostic (any OpenAI-compatible `/v1/chat/completions`), so the three engines
share one measurement path — differences are the engines, not the harness.

## How a session works

```
run_suite.py  ──▶ benchmarks/results/<engine>-<quant>.json   (one file per config, committed)
                                │
Phase-4 eval  ──▶ quality score ┤
                                ▼
report.py     ──▶ docs/reports/inference-benchmark-v1.md
```

One `run_suite.py` invocation == one (engine, quantization) pair. Every result
file is stamped with GPU, engine version, and timestamp, because a latency
number without them is not a measurement.

```bash
python benchmarks/run_suite.py --base-url http://localhost:8000/v1 \
    --model dhf1234/OpsLM-v1 --engine vllm --quant fp16 \
    --concurrency 1,4,16 --requests 32 \
    --out benchmarks/results/vllm-opslm-fp16.json

python benchmarks/report.py --results benchmarks/results \
    --quality fp16=0.94 --quality awq=0.91 --quality q4_k_m=0.88 \
    --out docs/reports/inference-benchmark-v1.md
```

### Controls, not just measurements

The sweep alone cannot attribute a result to a feature. Two probes ship with an
explicit control:

- **Prefix caching** — the suite measures cold-vs-warm TTFT with the cache on;
  the notebook re-runs it with `--no-enable-prefix-caching`. The *difference
  between the two runs* isolates the cache. A single warm-request measurement
  is indistinguishable from ordinary warm-up and is not evidence.
- **Guided decoding** — parse rate is measured with the constraint off, then on.
  Guided-on is 1.0 by construction, so the unguided baseline is the informative
  half.

Configurations with no quality score are **excluded from the frontier** rather
than defaulted, because a speed-only frontier recommends the smallest
quantization by construction — the exact error the frontier exists to prevent.

## What it measures

Per request: **TTFT** (time to first streamed token), total latency, output
tokens, tokens/sec. Per **concurrency level** (sweep 1 / 4 / 16): p50 & p95 of
each, plus **system throughput** (total output tokens ÷ wall-clock) — the
number that reveals continuous batching. Errors are excluded from latency
stats but counted.

```bash
python benchmarks/harness.py --base-url http://localhost:11434/v1 \
    --model opslm --concurrency 1,4,16 --requests 32 \
    --out benchmarks/results/ollama-opslm-q4.json
```

## Engines (one Colab notebook each, pinned)

| Engine | Serve command (sketch) | Endpoint |
|---|---|---|
| **Ollama** | `ollama serve` + `ollama create opslm -f Modelfile` (GGUF Q4_K_M) | `:11434/v1` |
| **vLLM** | `vllm serve <you>/OpsLM-v1 --quantization awq --max-model-len 2048` | `:8000/v1` |
| **SGLang** | `python -m sglang.launch_server --model-path <you>/OpsLM-v1` | `:30000/v1` |

Each notebook: install (pinned), pull/serve OpsLM, run `harness.py` at the
concurrency sweep, save JSON to `results/`. Same prompts, same sweep, same
harness → comparable numbers.

## Inference-optimization techniques (ADR-0014)

Each technique ships as tested code now; the measured payoff lands when OpsLM is
served. `techniques/` holds the algorithm/meter; the harness or the Phase-4 eval
produces the number.

| Technique | How it's measured on the served model | Serve flag (sketch) |
|---|---|---|
| **Speculative decoding** (prompt-lookup n-gram) | acceptance rate + tokens/s vs baseline; `speculative.py` proves it's *lossless* vs greedy and amortizes target passes | vLLM `--speculative-config '{"method":"ngram",...}'` |
| **Guided / structured decoding** | `json_parse_rate`→1.0 + field-accuracy via the structured-output evalset (ADR-0012), guided-on vs off; `constrained.py` is the token-masking FSM | vLLM `--guided-decoding-backend xgrammar` |
| **Quantization frontier** | FP16/Q8/Q4 latency (harness) × quality (Phase-4 eval) → Pareto + knee via `frontier.py` | GGUF `Q8_0`/`Q4_K_M`, AWQ |
| **Prefix caching** (APC / RadixAttention) | TTFT drop on shared-prefix requests: `shared_prefix_prompts` + `prefix_cache_speedup` | vLLM `--enable-prefix-caching` |
| **Multi-LoRA serving** (S-LoRA) | per-adapter latency + swap overhead; OpsLM *is* a LoRA — serve base + adapter and hit both `model` names | vLLM `--enable-lora --lora-modules opslm=<path>` |
| **Continuous batching / TPOT** | throughput vs concurrency sweep + **inter-token latency** (steady-state decode metric, distinct from TTFT) | native to vLLM/SGLang |

```bash
# unit tests for the technique implementations (no GPU needed)
uv run pytest benchmarks/tests -q
```

## Quantization vs quality

Speed is half the story. For each quant (FP16 / Q8 / Q4), re-run the
**Phase-4 eval** (`opsverse_evals.rag_suite`) pointed at that served model to
get the **quality delta**, producing a quality-vs-cost curve rather than a
speed-only table. This reuses the harness that already gates the platform.

## Honesty notes (planned in the report)

- Single **T4** can't demonstrate tensor parallelism — that will be *explained*
  (KV cache, continuous batching, prefix caching, speculative decoding) with
  measurements where the hardware allows and clearly labeled where it doesn't.
- "Output tokens" is approximated by streamed-chunk count (documented in
  `harness.py`); it's consistent across engines, so comparisons hold even if
  the absolute token count is approximate.
- Raw JSON is committed alongside the report so the charts are reproducible.
