# ADR-0012: A deterministic structured-output / tool-use eval

**Status:** accepted (2026-07-19) — baseline measured, in the regression gate

## Context

Two things pushed this in. (1) The plan's design review flagged
**structured-output / function-calling evaluation** as a differentiator —
"top AI Engineer JDs ask about tool-use reliability." (2) Phase 5 needs to
answer *"does fine-tuning break JSON/tool-calling?"* — SFT on prose Q&A can
quietly degrade a model's ability to emit clean JSON, and you only know if you
measure it before and after.

## Decision

Add `opsverse_evals.structured_eval`: a frozen set
(`evalsets/structured-output-v1.jsonl`) of DevOps tasks that each require a
**structured JSON answer with deterministically checkable fields** (extract
resource limits, parse a `docker run`, emit a `search_docs` tool call, pull
`kind`/`name` from a manifest, list exposed ports, …). Three metrics per run:

- `json_parse_rate` — is the output valid JSON at all?
- `schema_valid_rate` — are all required keys present?
- `field_accuracy` — do the checkable field values match expected?

**Scoring is fully deterministic** — JSON parse + key check + lenient exact
match (case-insensitive strings, int/float collapse, list normalization). No
LLM judge, so no judge quota and no non-determinism: the same output always
scores the same. This is deliberate — a tool-use gate that itself depends on a
judge would be measuring two things at once.

Recorded to `eval_runs` like every other report, surfaced at
`/v1/evals/reports`, and pinned in the regression gate.

## Baseline & how it's used

Gemini `3.1-flash-lite` scores **1.0 / 1.0 / 1.0** on the 12-case set — a
clean base-model baseline. The point is the **delta**: re-run
`structured_eval` against a served OpsLM (via `OPSVERSE_CHAT_MODEL` +
`OPSVERSE_CHAT_API_BASE`, ADR from the gateway/eval wiring) and compare. A
drop in `json_parse_rate` after SFT is the canonical "fine-tuning broke tool
calling" regression, and now it is a number, not a worry.

## Consequences

- Tool-use reliability is a measured, gated property of the platform, not an
  interview hand-wave.
- Thresholds are pinned with generous slack (n=12 is small; the gate is for
  regression detection, not leaderboard bragging) — `json_parse_rate ≥ 0.9`,
  `field_accuracy ≥ 0.8`.
- Native provider function-calling (`tools=[...]`) is deliberately *not* used:
  testing the model's ability to emit structured output from a plain prompt is
  the harder, more portable signal and works identically across Gemini, OpsLM,
  and any OpenAI-compatible server. Revisit if a native-tool-call path ships.
