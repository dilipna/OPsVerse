# Inference Engineering Lab (Phase 7)

Reproducible benchmarks of **Ollama vs vLLM vs SGLang** serving OpsLM
(Qwen3-4B, and its quantized GGUF/AWQ variants) on a free Colab/Kaggle GPU.
The comparison *is* the deliverable — this directory holds the harness,
methodology, and (once run) raw CSVs/JSON; the servers run on the GPU box, not
this machine.

## Status (honest)

| Piece | State |
|---|---|
| Benchmark harness (`harness.py`) | ✅ written; measurement math **unit-tested** |
| Inference techniques (`techniques/`) | ✅ implemented + **unit-tested** (speculative, guided decoding, quant frontier) |
| One-engine-per-notebook runners | ✅ documented below (thin wrappers) |
| **Actual benchmark run on GPU** | ⏳ pending — needs a Colab/Kaggle T4 + OpsLM (Phase 5) |
| Report (`docs/reports/inference-benchmark-v1.md`) | ⏳ blocked on the run |

Nothing here reports numbers that weren't measured. The harness is engine-
agnostic (any OpenAI-compatible `/v1/chat/completions`), so the three engines
share one measurement path — differences are the engines, not the harness.

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
