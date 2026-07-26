# ADR-0017: SLO-constrained goodput, not throughput, is the capacity metric

**Status:** accepted (2026-07-26). Implemented in `benchmarks/capacity.py`,
rendered to `docs/reports/capacity-and-slo-v1.md` from the same committed
session JSON that produces `inference-benchmark-v1.md`.

## Context

The Phase-7 benchmark (ADR-0011) answers *"what did each engine do?"* — TTFT,
ITL, throughput, scaling. It does not answer the question an operator actually
has: **how many users does one GPU serve, and what does that cost?**

Left there, the benchmark invites a specific error. Ollama's peak measured
throughput is 37.22 tok/s at concurrency 1 and 33.21 tok/s at concurrency 16 —
nearly flat. Reported as throughput, concurrency 16 looks like a mild 11%
regression. It is not mild: p95 TTFT at that level is **64.6 seconds**. Those
tokens are being generated for users who have already left. Raw throughput
counts them anyway.

## Decision

**Capacity is reported as goodput under an explicit latency SLO**, defaulting
to `p95 TTFT ≤ 1s` and `p95 end-to-end ≤ 30s`.

1. **A concurrency level is serviceable only if it meets both bounds.**
   Goodput is the highest throughput among serviceable levels. An engine with
   no serviceable level reports **none**, never a fallback to its fastest
   level — the failure is the finding.

2. **Cost per million tokens is derived from goodput**, using a GPU hourly
   rate supplied on the command line. The rate is an *assumption* and is
   labelled as one everywhere it appears. It is the only non-measured input in
   the report, and it is never silently baked in as a default constant.

3. **Control runs are excluded from the headline comparison.** A control is a
   deliberately partial sweep that isolates one variable. Ranking it against a
   full sweep manufactures a flattering ratio out of a *missing measurement* —
   comparing vLLM against the no-prefix-cache control yields 10.9x purely
   because the control never measured concurrency above 1. The honest
   cross-engine number is 6.3x. Controls stay in the tables, labelled.

4. **Saturation is asserted only when measured.** If marginal efficiency at
   the top of the sweep is still above 25%, the report states that peak
   throughput is **un-measured** rather than presenting the last data point as
   a ceiling. vLLM at c=16 returned 65% marginal efficiency: the sweep ended
   before the device did.

5. **Every headline number is rendered with its `n`**, and where two sessions
   measured the same engine at the same concurrency, their spread is published
   as an empirical noise floor (currently **+/-22%** for vLLM at c=1). A
   single-run delta smaller than that floor is not evidence.

## Consequences

- The defensible engine advantage drops from **13.4x** (throughput scaling) to
  **6.3x** (goodput under SLO). The smaller number is the one that survives
  holding both engines to the same user-facing contract, and it is the one to
  quote.
- The report can contradict a favourable headline. That is the point: it did,
  and the 6.3x figure replaced a larger number that was true but not useful.
- The SLO is a *policy input*, not a fact. A batch-scoring workload with no
  interactive deadline would set different bounds and legitimately reach a
  different conclusion, which is why the thresholds are CLI flags rather than
  constants.
- Small `n` is now published rather than buried. The prefix-cache probe rests
  on n=4; that is stated next to the 47.8% figure instead of being discovered
  by a reviewer.
- **Not addressed:** goodput is computed only at the concurrency levels that
  were swept (1, 4, 16). The true maximum serviceable concurrency lies
  somewhere in the gaps and is not interpolated — interpolating between three
  points would invent precision the measurement does not have.
