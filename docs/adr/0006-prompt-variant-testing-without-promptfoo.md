# ADR-0006: Prompt-variant testing via the existing eval stack, not promptfoo

**Status:** accepted (2026-07-16)

## Context

The Phase 4 plan listed "promptfoo for prompt-variant testing" alongside the
RAGAS-style judged suite and the regression gate. Those two now exist and run
(rag_suite → eval_runs + pinned thresholds; eval-gate.yml green on Actions).
The question left: adopt promptfoo for comparing chat-prompt variants, or
close the gap another way.

What prompt-variant testing must deliver here:
1. **Regression protection** — a prompt edit that hurts answer quality must
   fail a gate before it ships.
2. **Side-by-side comparison** — when someone proposes a prompt change,
   variant A vs variant B numbers on the same cases.

## Decision

**Do not adopt promptfoo.** Cover the two needs with what exists:

1. Regression protection is already live: the chat prompt cannot change
   without the judged smoke (`rag_suite`) being re-run — its report is pinned
   in `evalsets/regression-thresholds.json` (faithfulness ≥ 0.9, relevance
   ≥ 0.85, citation_used ≥ 0.9), and the regression gate fails on any
   committed report below threshold. The workflow for a prompt PR is:
   re-run the smoke, commit the regenerated report, gate must stay green.
2. Side-by-side comparison, when actually needed, is two `rag_suite` runs —
   one per prompt variant — compared as `eval_runs` rows (same dataset, same
   judge, run params recorded). The Postgres judge cache makes the unchanged
   halves of repeated runs free. No new tooling is required to read two rows.

Why promptfoo specifically lost:
- **Judge quota**: promptfoo's LLM-graded assertions bypass our Postgres
  judge cache, and free-tier quota is the platform's scarcest resource —
  a second, uncached judging path is a real cost, not a convenience.
- **Duplicate config surface**: it would re-declare providers/models outside
  `libs/core` settings (fallback chains, reasoning-effort quirks, the
  litellm <1.92 pin), which is exactly the drift the thin LiteLLM client
  (ADR-0004) exists to prevent.
- **Node dependency in the Python eval path** for a capability we exercise
  rarely (the chat prompt has changed twice in the project's life).

## Consequences

- Prompt iteration stays quota-cheap and lands in the same eval_runs/reports
  surface the UI and gate already read.
- We give up promptfoo's matrix ergonomics (many variants × many asserts in
  one YAML). If prompt work ever becomes high-frequency (e.g. Phase 5 OpsLM
  prompt tuning), the revisit trigger is: >2 variants compared per week —
  then a thin `--system-prompt` override on `rag_suite` is the first step,
  promptfoo the second.
- The plan's Phase 4 checklist item is closed by this ADR rather than by a
  dependency.
