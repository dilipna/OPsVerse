# ADR-0005: CI eval gate = pinned thresholds + committed retrieval fixture

**Status:** accepted (2026-07-13)

## Context

Phase 4 requires a CI gate that fails PRs which regress RAG quality. The full
eval stack cannot run in GitHub Actions as-is: the corpus lives in a DVC
remote on **local MinIO** (unreachable from Actions), and the LLM-judged
metrics need Gemini free-tier quota that is shared with development —
`gemini-3.5-flash` allows 20 requests/day total, and even `flash-lite`'s
larger quota is the same pool the dataset-generation pipelines draw from.

Options considered for getting eval data into CI:

- **(a) Google Drive DVC remote** — reachable from Actions, but adds OAuth
  secret management and an external dependency for a 7 MB dataset, and every
  CI run would pull the full corpus to test a fraction of it.
- **(b) Committed trimmed fixture** — a 200-chunk subset (25 gold chunks for
  the first 25 frozen retrieval-v1 cases + 175 seeded distractors) committed
  to git (~300 KB). Embedding it with CPU fastembed takes ~50 s.
- **(c) Nightly-only gate on a self-hosted runner** — full fidelity, but
  loses the per-PR gate entirely and adds runner maintenance; the machine in
  question is a personal laptop that is often off.

## Decision

**Option (b)**, structured as two deterministic, secret-free layers in
`eval-gate.yml`:

1. **`opsverse_evals.regression`** — asserts every committed
   `docs/reports/*-summary.json` against pinned thresholds
   (`evalsets/regression-thresholds.json`). Thresholds are pinned to measured
   baselines minus explicit slack; a missing report/mode/metric is a failure,
   not a skip. This stops "the numbers quietly changed/disappeared" PRs.
2. **`opsverse_evals.ci_retrieval_smoke`** — embeds the committed fixture
   into a Qdrant service container and runs the 25 frozen cases in hybrid
   mode, asserting `live: true` thresholds. This catches real retrieval-stack
   regressions (chunking, fusion, store queries, embedder config) on every
   PR, not just report edits.

LLM-judged quality (faithfulness/relevance via `rag_suite`) stays a
**local/manual gate** for now, recorded in Postgres `eval_runs` and committed
as report artifacts that layer 1 then protects. This is a deliberate
free-tier tradeoff, not an oversight: a per-PR judge run would either starve
development of quota or silently skip on forks without secrets — a gate that
sometimes doesn't run is worse than a documented manual step.

## Consequences

- PRs touching retrieval/eval/API code get a real quality gate in ~3–4 min
  (fastembed model download is cached on `uv.lock`).
- The fixture is intentionally easy (200 chunks → MRR ≈ 0.85 vs 0.64 on the
  full corpus): its job is regression detection, not benchmarking. Absolute
  numbers live in the ablation reports.
- Fixture regeneration (`build_ci_fixture`, seeded) is only needed when the
  frozen evalset or corpus export format changes; regenerating re-pins the
  `retrieval-ci-smoke` thresholds against fresh measurements.
- When a hosted DVC remote or paid API budget arrives, layer 2 can grow into
  the full suite without changing the gate's shape (thresholds file + exit
  code stay the interface).
