# We built the eval harness before the model — and the numbers changed our retrieval design twice

*OpsVerse AI is a production-grade RAG platform for DevOps knowledge. This is
the story of why "evaluation-first" isn't a slogan here — it's the thing that
stopped me shipping two wrong decisions.*

## The setup

Most RAG projects build retrieval, eyeball a few answers, call it good, and
move on. OpsVerse does the opposite: the evaluation harness existed **before**
any quality claim. Concretely, that means a frozen set of labeled questions, an
ablation runner that scores dense / sparse / hybrid / hybrid+rerank on
hit-rate, MRR, and nDCG, and a regression gate wired into CI. Boring
infrastructure — until it starts contradicting you.

It contradicted me twice.

## Wrong decision #1: "add a reranker, obviously"

The textbook RAG stack is hybrid retrieval + a cross-encoder reranker. I built
it, turned it on, and let the harness score it against the frozen eval set.

On the original corpus, rerank was **quality-negative** — MRR@10 dropped from
0.643 (hybrid) to 0.612 (hybrid+rerank), while costing ~9 seconds per query on
CPU. The "obviously correct" component made retrieval *worse* and 30× slower.

Without the harness I'd have shipped it, because it *feels* right. With the
harness, I turned it **off by default** and wrote down exactly why. That's an
ADR reviewers can read, not a vibe.

## Wrong decision #2: "sparse wins, switch the default"

Later I expanded the corpus 15× (1,241 docs / 7,383 chunks) and regenerated a
fresh eval set. New numbers: **sparse BM25 now won** — MRR@10 0.759 vs hybrid's
0.705. Lexical retrieval beating hybrid is a real, publishable-looking result.
The tempting move: switch the chat default to sparse and write a smug blog post
about how everyone over-engineers with embeddings.

I didn't — because of *how* the eval questions are generated. Each question is
written by an LLM looking at one gold chunk. That process quietly reuses the
chunk's vocabulary, which flatters exact-term (sparse) matching. The "sparse
wins" result might be measuring my data-generation process, not retrieval
quality.

So I built a third eval set to test exactly that: **paraphrase every question**
(same meaning, different words — mean vocabulary overlap with the original just
0.31), keep the gold labels, re-run the ablation.

The result settled it:

| chunk MRR@10 | verbatim questions | paraphrased questions | change |
|---|---|---|---|
| sparse | **0.759** | 0.611 | **−0.149** |
| hybrid | 0.705 | **0.656** | −0.049 |
| dense | 0.553 | 0.570 | +0.017 |

Under paraphrase, sparse lost 20% of its MRR — its win *was* vocabulary
leakage. Hybrid degraded 3× less, because the dense leg carries it when
wording shifts. Dense was flat (semantic vectors don't care about phrasing).

**Decision: chat stays hybrid**, now with evidence across three regimes. Real
users live somewhere between pasting verbatim error strings (sparse's home
turf) and describing problems in their own words (paraphrase). Hybrid is the
only mode near-optimal at both ends. That's the rationale — not a single table
I liked.

## Why this matters for a production system

Two things a panel actually cares about fell out of this:

1. **The harness caught what intuition missed, twice.** Eval-first isn't
   ceremony; it's the mechanism that made "obvious" decisions falsifiable.
2. **Honesty about your own measurement.** The second save came from
   distrusting a result that flattered a simpler design. Knowing *why* a metric
   moved — and building the eval that isolates it — is the job.

The gate is now in CI: a PR that regresses retrieval below pinned thresholds
fails before merge, and the RAG-quality, security-detection, and paraphrase
sets sit alongside it. Deterministic tests for code; statistical gates for
model behavior.

*OpsVerse is built on free tiers and local compute, with an ADR for every
non-trivial decision and a measured number behind every claim. Every number
above comes from the committed retrieval-ablation v1/v2/v3 reports; the
rerank-off default and the hybrid-over-sparse call are written up there in
full.*
