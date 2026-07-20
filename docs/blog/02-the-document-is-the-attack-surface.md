# The document is the attack surface — RAG security at ingest, measured like a classifier

*OpsVerse AI is a production-grade RAG platform for DevOps knowledge. Blog #1
was about evaluating retrieval before trusting it. This one applies the same
discipline to security: every defense is either measured or deliberately
absent, with the reasoning written down.*

## The threat model most RAG demos skip

Prompt injection discourse fixates on the chat box. For a RAG system that's
the wrong place to look. The queries users type are the *least* interesting
attack surface, because you can see them coming. The interesting one is the
corpus itself:

1. **Indirect prompt injection** — instructions planted inside an ingested
   document. This is the serious one: retrieval's whole job is to take that
   text and hand it to the LLM as trusted context. The attacker doesn't need
   access to your chat; they need one poisoned README in your corpus.
2. **Credential leakage** — a doc with a live AWS key gets chunked, embedded,
   and cheerfully quoted into an answer six weeks later.
3. **Direct query injection** — the classic "ignore previous instructions"
   typed into chat.

OpsVerse defends all three, but the design weight goes where the threat is.

## Defense #1: quarantine at ingest, not filtering at prompt time

The common pattern is to scan retrieved chunks at prompt-assembly time. We
don't. Every document is scanned by a weighted-signal injection heuristic
**at ingest**; a flagged document is stored with `status=quarantined` and
contributes **zero chunks** to the vector store. A poisoned doc never gets
embedded, never ranks, never reaches a prompt — there is nothing to filter
later because it was never there.

Why ingest is the right choke point:

- **It's one place.** Chat, search, the MCP server, exports — every consumer
  of retrieval is protected at once, including the ones added later.
- **It's auditable, not silent.** The ingest job stats report `quarantined`
  counts and per-document `quarantine_reasons`. A dropped document is a
  visible event an operator can review, not a chunk that mysteriously never
  ranks.
- **It fails safe.** The worst case is a false positive on ingest — one doc
  to manually review — not attacker text sitting live in the index.

This is verified end-to-end, not just unit-tested: upload a poisoned
document to the running stack, watch it quarantine, confirm zero chunks in
Qdrant.

## Defense #2: secrets are redacted before they exist anywhere

Credential-shaped strings — AWS key ids, GitHub/Slack/Google/OpenAI tokens,
private-key blocks, JWTs, long assigned `api_key=` values — are replaced
with `[REDACTED:<kind>]` **before storage and embedding**. Not masked at
render time: never stored. Qdrant payloads, chat context windows, exports —
no downstream surface can leak what no surface ever held. Each ingest job
counts what it redacted (`secrets_redacted`), so a doc full of live keys is
a visible anomaly, not a quiet time bomb.

## Defense #3: chat queries are flagged, not blocked — on purpose

Query-time injection scanning runs on every chat message, and the tripped
signal names land in the request ledger for audit. What it deliberately does
**not** do is block the request. Two reasons:

1. **This is read-only RAG.** No tool mutates anything; the blast radius of
   a hostile query is a weird answer to the person who typed it.
2. **DevOps vocabulary is an FPR trap.** "Override the entrypoint", "ignore
   files", "system:masters", "forget cached layers" — legitimate daily
   phrasing that pattern-matches injection. Heuristic blocking here would
   break real users to stop an attacker who isn't attacking anything.

Blocking is a policy you should be able to defend with a false-positive
budget. We couldn't, so we log instead — and the ledger means turning on
blocking later is an evidence-based decision, not a guess.

## If you ship a heuristic, ship its eval

The uncomfortable truth about the injection scanner: it's a pile of weighted
regex-ish signals. The difference between that and snake oil is measurement.
So the heuristic is treated exactly like a model: a frozen red-team set
(15 attack payloads, 18 benign DevOps sentences chosen specifically to share
surface vocabulary with the attacks) and a scoring harness.

Measured on 2026-07-17: **TPR 1.0, specificity 1.0, precision 1.0** — and
those floors are pinned in the same regression gate that guards retrieval
(TPR ≥ 0.85, specificity ≥ 0.95), so a "quick tweak" to a signal weight that
starts missing attacks fails CI before it ships.

The honest caveat, stated in the ADR and repeated here: the set is small and
hand-curated. The claim is "commodity attacks are caught, and the catch rate
is measured and gated" — not "prompt injection is solved". False negatives
are possible by construction; every observed miss grows the versioned set.

## What we deliberately did not build

Saying no is half the design. Written down with revisit triggers:

- **No Presidio / PII pipeline.** The corpus is public vendor documentation;
  there is no user PII at rest. Presidio brings hundreds of MB of NLP models
  to solve a problem this system doesn't have. Trigger: ingesting private or
  user-generated content.
- **No IP/hostname/port redaction.** In DevOps docs those are load-bearing
  content. Redacting them destroys the product to protect nothing.
- **No embedding-similarity attack detector.** A fuzzier second layer with a
  tunable threshold and no labeled data to tune it on. The measured layer
  has to be beaten by real misses first.

## The shape of the whole thing

Same philosophy as the retrieval work: **a defense you haven't measured is a
vibe.** Quarantine at the single choke point, redact before anything is
stored, log where blocking would break users, score the heuristic like a
classifier, and gate the floor in CI. Every claim above traces to a committed
report or an ADR — and the one number that matters most is still zero: chunks
contributed to retrieval by a poisoned document.

*Numbers from the committed security-redteam-v1 report; design rationale in
ADR-0007. The red-team set, scoring harness, and regression thresholds are
all in the repo.*
