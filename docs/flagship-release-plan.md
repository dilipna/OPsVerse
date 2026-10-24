# Flagship investigation release

Owner handoff accepted October 23, 2026. Starting source:
`c385cc5f867834dc63dc93daa98d323dc98c48fe`. This checkout is isolated on
`improve/flagship-investigation`. No publication or production release is implied.

## Product and engineering acceptance

An engineer should be able to bring a sanitized Kubernetes symptom, distinguish
observations from hypotheses, inspect the supporting source, see missing evidence,
and export a reproducible investigation brief. No command executes. Model-backed
drafts and browser retrieval must have distinct operating identities.

1. Reproduce the existing Python, browser-library, raw-corpus and HTTP baseline.
2. Freeze failure cases before repairing the corresponding mechanism. Preserve the
   original 24-case evaluation and published negative outcomes; do not reuse them as
   an untouched test for a newly tuned retriever.
3. Enforce consistent output states. In particular, an abstention must not carry
   actionable claims or commands. Reject unknown output fields instead of exporting
   unverifiable model metadata. Test through the actual shared HTTP handler.
4. Develop a bounded investigation/evidence policy with explicit decisions,
   provenance, context omissions and failure reasons. Compare alternatives on the
   same frozen inputs and report regressions as well as improvements.
5. Develop the workspace as a complete product: clear evidence hierarchy,
   inspectable decisions, keyboard/mobile interaction, errors and recovery,
   useful empty states, and truthful evaluation/architecture views.
6. Run complete release checks and package source plus evidence. Publication and
   production changes need approval for the concrete tested release. Verify the
   real production site after deployment.

## Model evidence and resource constraint

The prior base/SFT study is an independently converted served-artifact comparison,
not a causal training experiment. No new model benefit is established. At initial
inspection available host memory was approximately 1.47 GiB, below the existing
protocol's 2.5 GiB minimum for a CPU model load. Do not load a model, stop unrelated
applications, substitute sample outputs, or silently change the protocol. Recheck
resources when a real inference run is otherwise ready. No paid inference/training.

## Fifteen-idea decisions

These are design decisions and acceptance targets, not implemented accomplishments.

| # | Idea | OpsVerse decision |
|---|---|---|
| 1 | Dynamic context assembler | Extend existing context assembly with explicit omissions and real-token accounting when an available runtime/tokenizer supports it. Character limits are not token budgets. |
| 2 | Durable state machine | Use versioned, reviewable investigation state only if recovery is part of the product; do not introduce Temporal without a long-running external workflow. |
| 3 | Raw MCP | Audit the existing MCP service and its actual read scopes. Preserve maintained transport instead of a redundant from-scratch server. |
| 4 | Triage router | Conditional experiment after task-quality and resource baselines; no invented 95/5 traffic distribution or cost saving. |
| 5 | Corrective RAG | Priority candidate: bounded evidence checks and retrieval retry only for demonstrated baseline failures; explicit abstention. |
| 6 | Three-tier memory | Defer until a longitudinal investigation needs selective recall; saved local state alone is not three-tier memory. |
| 7 | Trajectory CI | Priority candidate: executable invariants for retrieval, no-evidence/no-model, validation, rejection and no external effects. Accept multiple valid paths. |
| 8 | Sanitization proxy | Strengthen typed untrusted evidence/output boundaries. No inter-agent proxy claim without actual inter-agent communication. |
| 9 | Voice interruption | Exclude: does not serve this investigation product. |
| 10 | DPO flywheel | Defer pending reviewed preference pairs and a measured base/SFT benefit. No automatic training or promotion. |
| 11 | Cost kill-switch | Bound actual retries, time and context first. No paid-provider fallback or fictional dollar accounting. |
| 12 | Shadow comparator | Use paired offline replay when comparing a concrete candidate. Do not label replay as mirrored live traffic. |
| 13 | Computer-use fallback | Exclude: no demonstrated portal/API gap; no autonomous browser access to a cluster. |
| 14 | PII restoration | Preserve data minimization/redaction; no restoration vault without an authorized recipient use case. Redaction is best-effort. |
| 15 | Architecture teardown | Extend the existing case study with actual defects, alternatives, measured results, reproduction and limitations. |

The references and full original descriptions are retained in the program-level
fifteen-idea ledger. Inspect current primary documentation and licenses before any
new dependency or upstream code adoption.
