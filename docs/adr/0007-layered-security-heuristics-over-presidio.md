# ADR-0007: Layered RAG security — measured heuristics, quarantine at ingest

**Status:** accepted (2026-07-17)

## Context

Phase 9 requires defenses against the attacks a RAG platform actually faces:
1. **Indirect prompt injection** — instructions planted in ingested documents
   (the serious one: retrieval hands attacker text straight to the LLM).
2. **Credential leakage** — secrets in ingested docs get embedded, retrieved,
   and quoted into answers.
3. **Direct query injection** — override/exfiltration attempts typed into chat.

The plan named Presidio (PII) and Rebuff-style detection as candidates.

## Decision

Three layers in `libs/security`, all deterministic, all measured or unit-tested:

1. **Ingest quarantine (primary defense).** Every document is scanned by a
   weighted-signal injection heuristic (`scan_injection`); a flagged document
   is stored with `status=quarantined` and contributes **zero chunks** to
   retrieval. Poisoned docs are stopped before they can ever reach a prompt.
2. **Ingest-time secret redaction.** Credential-shaped strings (AWS key ids,
   GitHub/Slack/Google/OpenAI tokens, private-key blocks, JWTs, long assigned
   `api_key=`/`secret_key=` values) are replaced with `[REDACTED:<kind>]`
   before storage/embedding, so nothing downstream — Qdrant payloads, chat
   context, exports — ever holds them. Counted per ingest job
   (`secrets_redacted` in stats).
3. **Query-time flagging, not blocking.** Chat queries are scanned and the
   tripped signal names land in `request_ledger.meta.injection_flags` for
   audit/alerting. We deliberately do NOT block: this is read-only RAG (no
   tools mutate anything), and DevOps vocabulary ("override the entrypoint",
   "ignore files", "system:masters", "forget cached layers") makes heuristic
   blocking an FPR trap that would break legitimate use.

**The heuristic is treated as a classifier with an eval.** A frozen red-team
set (`evalsets/security-redteam-v1.jsonl`: 15 attacks, 18 benign DevOps
sentences chosen to share surface vocabulary with attacks) is scored by
`python -m opsverse_security.evaluate`; measured 2026-07-17: TPR 1.0,
specificity 1.0, precision 1.0. Thresholds pinned in the regression gate
(TPR ≥ 0.85, specificity ≥ 0.95). The set is small and hand-curated — the
claim is "commodity attacks are caught and measured", not "injection solved".

## What we deliberately do NOT do

- **No Presidio / no PII pipeline.** The corpus is public vendor
  documentation; there is no user PII at rest. Presidio brings spaCy models
  (hundreds of MB) to solve a problem this system doesn't have yet.
  Revisit trigger: ingesting private/user-generated content.
- **No IP/hostname/port redaction.** They are load-bearing content in DevOps
  docs; redacting them destroys the product to protect nothing.
- **No embedding-similarity attack detection.** A second, fuzzier layer with
  a tunable threshold and no labeled data to tune on; the measured heuristic
  layer has to be beaten by real misses first.

## Consequences

- A poisoned document is invisible to retrieval, and the ingest job stats
  say so (`quarantined`, `quarantine_reasons`) — auditable, not silent.
- Redaction runs on every chunk of every ingest (a few regexes; negligible
  vs. embedding cost).
- False negatives are possible by construction (novel phrasings); the
  red-team set is versioned and grows with every observed miss, and the
  gate keeps the measured floor from regressing.
