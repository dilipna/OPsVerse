# ADR-0020: Chunking ablation (document-level) and a first multi-turn eval

**Status:** accepted (2026-09-01)

## Context

Two gaps remained after the golden-set work in ADR-0018/0019:

1. **Chunking was never ablated.** `opsverse_ingestion.chunking` has hard-coded
   `TARGET_TOKENS=350`, `MAX_TOKENS=512`, `OVERLAP_TOKENS=50` — three numbers picked once
   and never varied. "How did you choose your chunk size?" had no measured answer.
2. **Every eval set is single-turn.** `retrieval-v1/v2/v3` and `retrieval-golden-v1` are
   all one self-contained question per case. Production chat is not: `stream_chat`
   (`libs/rag/chat.py`) sends only the current turn's raw text to the retriever
   (`retrieval_query = query`) — conversation history reaches the generator's prompt but
   never the retriever. No eval set could see that.

## Decision — chunking ablation

Re-parse the **original source documents** (not the already-chunked corpus dump) under
three configs — `small` (150/256/30), `baseline` (350/512/50, the shipped default), and
`large` (700/900/100) — and score each against the golden set.

**Scoring is at document granularity, not chunk granularity.** Re-chunking changes chunk
ids, so `retrieval-golden-v1`'s per-chunk grades cannot be reused directly under a new
chunking. What survives re-chunking is the document: each golden query's chunk-level
grades are aggregated up to their parent document (`doc_grade = max` over that document's
judged chunks), and `hit@k` / `mrr@k` / `ndcg_at_k_graded` are computed on the retrieved
chunks' parent document ids — the same convention `run_ablation.py` already uses for its
`doc:` metrics (no dedup: duplicates in the id list are scored as-is).

**Scope:** the documents backing every judged chunk in the golden set — every document
any of the four pooled retrieval modes ever surfaced (594 total; see subsampling note in
the report for the exact run size). Source bytes are resolved from the original GitHub
tarballs committed in MinIO, each file matched to its document record **by SHA-256, not
path alone** — the corpus contains two overlapping `kubernetes-website` tarball
snapshots from its ingestion history, and hashing is what disambiguates them correctly
(verified on an 8-document smoke sample spanning that exact ambiguity: 8/8 resolved).

Same embedder throughout (`BAAI/bge-base-en-v1.5`, the incumbent) — the isolation
principle already used in `embedding_ablation.py`: one variable changes at a time.

**Result:** see [chunking-ablation-v1.md](../reports/chunking-ablation-v1.md). Time-boxed to
100/594 candidate documents for same-day turnaround (stated as a limit in the report; the
comparison between configs stays valid since all three index the identical 100 documents).

- **`small` (150 tokens) beats the shipped `baseline` (350 tokens) on `nDCG_graded@10`:**
  +0.044, paired permutation p=0.0002 — significant.
- **`large` (700 tokens) is significantly worse than `baseline`:** -0.017, p=0.017.
- **`hit@10` is identical (0.350) across all three configs** — not evidence chunking is
  irrelevant, but the ceiling imposed by indexing only 100/594 documents: many queries'
  true answer document isn't in this smaller index regardless of chunk size.
  `nDCG_graded@10` is the metric with room to move, and it moves monotonically with chunk
  size (small > baseline > large).
- Indexing cost: `small` produced 15.11 chunks/doc, `baseline` 9.22, `large` 7.92 — smaller
  chunks cost proportionally more to embed and store. `small`'s wall-clock index time
  (2271.8s) was measured under CPU contention with a concurrent job and is not a clean
  throughput comparison; chunk count is the reliable relative-cost signal.
- **The shipped default is not the best-measured option** on this corpus, on this metric,
  at this scope. That is the entire point of running the ablation instead of trusting the
  original choice.

## Decision — multi-turn eval

Built `multiturn-v1`: 2-turn conversations where turn 2 is deliberately elliptical (a
pronoun or "what about X instead" that only resolves given turn 1), LLM-written per
chunk, single gold label per case (same convention as `retrieval-v1/v2/v3` — the
ADR-0018 degeneracy applies here too: this set reports `hit@k`/`mrr@k`, not
recall/precision).

Two conditions scored against the **live production collection** (`opsverse_kb`, hybrid
mode — the actual deployed retriever, not a throwaway index):

- **`turn2_only`** — what `stream_chat` does today.
- **`concat_history`** — retrieve on `f"{turn1} {turn2}"`. The cheapest plausible
  mitigation: no architecture change, no query-rewriting model, just folding history
  into the retrieval string.

A paired permutation test on `concat_history` vs `turn2_only` answers the only question
that matters: does the naive fix actually help, or does it just add noise to the query?

**Result:** see [multiturn-v1.md](../reports/multiturn-v1.md). 50 cases, 0 skipped.

- `turn2_only`: hit@10 **0.680**, mrr@10 **0.483**
- `concat_history`: hit@10 **0.600**, mrr@10 **0.413**
- Paired permutation test (10k permutations): **not significant** on any metric
  (hit@10 p=0.448, mrr@10 p=0.301, ndcg@10 p=0.247) — the naive fix trends *worse*, not
  better, though the gap does not clear the noise floor at n=50.

**The naive fix does not help, and the direction is a plausible-but-unproven story worth
stating rather than hiding:** turn 1 is deliberately about a *different* topic than
turn 2 (that is what makes turn 2 elliptical), so concatenating it adds off-topic query
terms rather than resolving the reference — string concatenation is not query rewriting.
Turn2-only remains the better default of the two conditions tested; the honest next step
is an actual reference-resolution step (an LLM call, or a dedicated conversational
encoder), not string concatenation.

## Consequences

- Two more places where "we never measured X" is replaced with a written number and a
  significance test, continuing the pattern from ADR-0018/0019.
- **Chunking result is document-level only.** Whether a config also retrieves the
  *right passage* within a correctly-found document is a finer question this ablation
  cannot answer without re-judging every chunk under every config — out of scope here,
  named as a limitation in the report.
- **Multi-turn cases are constructed, not observed.** No real conversations are logged,
  so this measures whether the failure mode exists and is measurable, not its frequency
  in production traffic.
- `concat_history` did not help (trended worse, not significant) — the honest next step
  is query rewriting or a dedicated conversational encoder, not shipping string
  concatenation. This eval's job was to floor-test the cheapest fix and report honestly
  that it doesn't clear the bar, not to select a final design.
- **The shipped chunking default (350/512/50) is not the best-measured option** on the
  one metric with room to move (`nDCG_graded@10`) at the scope tested. This does not
  trigger a production change on its own — the result is document-level and scoped to
  100/594 documents — but it is a concrete, measured reason to re-run this ablation at
  full scope before treating 350/512/50 as settled.
- Both scripts gained on-disk checkpointing (`embedding_ablation.py` too) after multiple
  session-restart crashes killed long single-shot sweeps mid-run with no partial-result
  recovery — each model/config result is now cached to disk as soon as it is computed.
  One crash was self-inflicted (deleting a collection while its writer was still active,
  mistaking a slow-but-alive process for a dead one from buffered-empty log output) —
  the fix going forward is checking process activity before touching shared state, not
  just absence of recent log lines.
