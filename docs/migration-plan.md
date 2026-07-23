# OpsVerse → LLM Inference & Operations Platform: migration plan

> Status: **approved 2026-07-23**. This document records the repositioning of OpsVerse
> from "RAG platform with a fine-tune" to "**LLM inference platform**, with RAG as its
> workload." It is a migration plan, not a rewrite plan — the audit below found that
> most of the target architecture already exists and is mis-framed rather than missing.

## 1. Why reposition at all

OpsVerse is portfolio project #3 of 3, targeting **LLM Engineer / Inference Engineer /
AI Infrastructure Engineer** roles. Its siblings already cover the adjacent ground:
FIFA2026MLOps owns classical MLOps, ProtoPro owns agents. OpsVerse must therefore own
the part neither does: **what happens to a model after it is trained** — serving,
optimization, measurement, and operation.

The repo already does most of that. What it does *not* do is **say** that, and — more
seriously — it does not yet **prove** it with measurements.

## 2. Audit: current state vs. target architecture

| Target module | Current state | Action |
|---|---|---|
| **1. Inference engine** | `libs/core/llm.py` is an OpenAI-shaped async client over litellm with streaming, fallback, and an injectable `api_base` (ADR-0004, ADR-0008). `transformers.generate()` was never used. **No vLLM has ever been run.** | **Measure.** The client is correct; the engine underneath it is unproven. |
| **2. Model registry** | Does not exist. Model identity is scattered across ADR-0009, the Hub repo, and `CONTINUE_SESSION.md`. | **Build.** Small, CPU-only, high narrative value. |
| **3. Optimization lab** | `techniques/frontier.py` computes a Pareto frontier + knee point; GGUF `Q4_K_M` published. No FP16/Q8/AWQ measurements exist to put on the frontier. | **Measure.** The analysis code is done and unit-tested; it has no inputs. |
| **4. Benchmarking** | `benchmarks/harness.py` is engine-agnostic, measures TTFT/TPOT/throughput, math unit-tested. **Zero results committed.** | **Measure.** This is the #1 priority of the whole migration. |
| **5. Evaluation** | 3 retrieval ablations, a paraphrase set that falsified the project's own v2 result, structured-output eval, 15-threshold regression gate wired into CI. | **Keep as-is.** Stronger than the RAGAS/DeepEval/Promptfoo stack originally requested. |
| **6. Observability** | Langfuse v2 self-hosted + tracing facade, live trace verified (ADR-0010). No Prometheus, no OpenTelemetry. | **Extend** with serving-side metrics once serving produces any. |
| **7. Deployment** | Docker Compose (2 profiles) + K8s manifests for API/worker/Redis/stateful/ingress. No GPU workload manifest. | **Extend** with a vLLM GPU Deployment. |
| **8. CI/CD** | `ci.yml` (ruff / ruff-format / pyright / pytest / docker build) + `eval-gate.yml`. No security scan, no registry push. | **Extend.** Small delta. |
| **9. Frontend** | `apps/web` is chat-first (`/`) plus `/evals`, `/costs`. `opslm-demo` is a public marketing/demo site. | **Reframe**, do not rebuild. |

**Conclusion of the audit: the gap is evidence, not features.**

## 3. The central problem

`benchmarks/README.md` is an honest document whose status table reads `⏳ pending` on
every row that matters to an inference role. The same is true of the Phase-5 before/after
eval. The project currently presents a well-built measuring instrument with **no readings
taken**.

No amount of new modules fixes this. A reviewer's inference is not "they haven't built
the registry yet" — it is "they have never served a model under load." Producing real
numbers is therefore sequenced ahead of every other module in this plan.

## 4. Decisions taken

### 4.1 GPU access: ephemeral Colab, not rented hardware

vLLM, AWQ/GPTQ, PagedAttention and GPU-utilization metrics all require CUDA. The
always-on serving path (`infra/oracle-opslm/`, Oracle Free Tier) is **ARM CPU** and can
never run them.

**Decision:** benchmark runs happen in ephemeral **Colab T4** sessions; raw JSON and
generated reports are committed back to the repo. The always-on public endpoint stays
CPU/Ollama.

*Consequence to state honestly in the README:* single-T4 means no tensor parallelism and
no multi-GPU scaling numbers. Those get **explained**, never claimed. Everything a single
T4 *can* demonstrate — continuous batching, KV cache, prefix caching, speculative
decoding, quantization frontier, multi-LoRA — gets **measured**.

### 4.2 RAG is demoted to a workload, not deleted

The brief said "not another RAG application." The fix is framing, not deletion:

- The README and architecture doc lead with **inference**; retrieval appears as *the
  workload the platform serves*.
- The eval platform is retained precisely because **the quantization frontier needs a
  quality axis.** Deleting the eval sets would make "quality degradation" unmeasurable
  and reduce Module 3 to a speed table — which is exactly the shallow artifact the
  repositioning is meant to avoid.

No ingestion, RAG, or security code is removed.

### 4.3 Rejected from the original brief

| Rejected | Reason |
|---|---|
| RAGAS / DeepEval / Promptfoo | ADR-0006 already documents rejecting promptfoo with reasoning. The bespoke eval platform is more defensible than three imported frameworks; adding them would read as keyword-stuffing. |
| Terraform | Belongs to the MLOps sibling project. Adds no LLM-inference signal. |
| Ground-up frontend rewrite | `apps/web` needs new pages and a new information hierarchy, not a new codebase. |
| Retraining the model | OpsLM-v1 is the production artifact by definition. DPO→v2 stays optional depth. |

## 5. Redesigned architecture

Serving is promoted to a first-class layer with a real engine under it. The dashed path
is the honest split between what runs always-on for free and what runs during a
measurement session.

```
                       Next.js dashboard  (apps/web)
                    overview · registry · playground
                    benchmarks · evals · monitoring
                                  │
                       FastAPI gateway  (apps/api)
             routing · Redis cache · budget kill-switch · tracing
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
        Model registry      Eval platform       Observability
      versions · quant ·   ablations · gates   Langfuse · Prom · OTel
      eval score · status
                                  │
                       OpenAI-compatible surface
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
      vLLM (Colab T4, ephemeral)          Ollama / llama.cpp (Oracle ARM)
      PagedAttention · cont. batching     always-on public demo endpoint
      prefix cache · spec decode · LoRA
              │                                       │
              └──────────────► OpsLM-v1 ◄─────────────┘
                        (Qwen3-4B QLoRA, FP16 / AWQ / GGUF)
```

The single OpenAI-compatible surface is what makes this tractable: one harness, one
client, one eval path measures every engine and every quantization without per-engine
code.

## 6. Migration sequence

Ordered by evidence produced per unit of effort.

| # | Work | Produces | Blocked on |
|---|---|---|---|
| **1** | **Measurement suite + Colab runner** | vLLM vs Ollama, FP16/AWQ/Q8/Q4, concurrency sweep, TTFT/TPOT/throughput, prefix-cache and guided-decoding probes → committed JSON + report | user runs one Colab session |
| **2** | Quantization frontier report | Module 3 table with a real quality axis, using existing eval sets | #1 |
| **3** | Before/after eval (base Qwen3-4B vs OpsLM-v1) | the fine-tune's justification | #1 |
| **4** | Model registry | versions, quant, eval score, deploy status; fed by #1–#3 | #1 |
| **5** | Frontend reframe | overview / registry / benchmarks / playground pages | #4 |
| **6** | Prometheus + OTel serving metrics | GPU + request metrics alongside Langfuse | #1 |
| **7** | CI/CD + K8s extensions | security scan, registry push, GPU workload manifest | — |
| **8** | README + technical design doc rewrite | the framing this document specifies | #1–#5 |

Steps 4–8 are deliberately *downstream of measurement*: each one is a surface that
displays numbers, and building surfaces before there are numbers to display is how the
project got into its current state.

## 7. Standing honesty rules

Carried forward from the project's existing bar, and binding on every artifact produced
under this plan:

1. A claim without a committed measurement is a liability. Reports state `n`, hardware,
   and date.
2. Raw JSON is committed next to every generated report so charts are reproducible.
3. Approximations are labelled at the point of use (e.g. `harness.py` counts streamed
   chunks as a proxy for output tokens — consistent across engines, so comparisons hold
   even where the absolute count does not).
4. What a single T4 cannot show is stated as a limitation, not omitted.
