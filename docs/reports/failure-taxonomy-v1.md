# Failure taxonomy v1 - what retrieval failure actually looks like here

Generated 2026-09-07 by `opsverse_evals.failure_taxonomy` from the committed golden
set, ablation raw JSON, corpus dump and hand-assigned codes. Offline.

Scope: the **hybrid** retriever over the 100 golden queries. **28** were flagged by a deliberately over-inclusive failure
signal; all 28 were read and coded by hand.

## Why this exists

This project measured retrieval to four decimal places and could not show you a
single failure. Every report was an aggregate, and an aggregate cannot say whether
a low `recall@10` is one systematic defect or twenty unrelated ones. This is the
error analysis that answers that, and the answer was not what the metric implied.

## The finding

**23 of the 28 flagged failures (82%) are not
retrieval defects.** Only **5** are - which is **5% of the
100 queries**, not the ~28% the flag rate suggests.

The two largest categories are the metric describing the corpus rather than the
retriever: queries where a grade-3 answer sits at rank 1-3 but several other
labelled-relevant chunks were not recovered, and queries whose relevant set is
mostly near-duplicates of each other. **This is the concrete mechanism behind the
low absolute `recall@k` on the golden set** - and it is independent of, and
additional to, the judge's strictness measured in [ADR-0022](../adr/0022-judge-validation-against-a-second-rater.md).

| category | n | share | real defect? |
|---|---|---|---|
| The metric flagged a query the user would call answered | 18 | 64% | no |
| Near-duplicate chunks inflate the relevant set | 4 | 14% | no |
| A common query term pulls in generic prose | 2 | 7% | **yes** |
| Right topic, wrong specificity | 1 | 4% | **yes** |
| The judge graded a chunk that does not answer the question | 1 | 4% | no |
| Nothing relevant retrieved at all | 1 | 4% | **yes** |
| Repeated boilerplate crowds out the explanatory chunk | 1 | 4% | **yes** |

## The categories

### The metric flagged a query the user would call answered — 18 case(s)

*Not a retrieval defect.* A relevant chunk -- usually grade 3 -- is at rank 1-3, but the query has several labelled-relevant chunks and not all were recovered, so recall@10 scores it below 1.0.

> **Example** (`1ee07e4d`) — How can I configure the Docker agent to route all provider traffic through a specific models gateway URL?  
> Relevant in pool: 6, retrieved: 5, first relevant at rank 2. Top-6 grades: `[1, 2, 3, 3, 1, 1]`.  
> found 5/6, first relevant at rank 2; the grade-3 flag tables above it are reference stubs, but the question is answered on screen

**What to do:** Nothing to fix in retrieval. This is what a recall metric does on a corpus with many acceptable answers per question, and it is the largest single reason absolute recall reads low here.

### Near-duplicate chunks inflate the relevant set — 4 case(s)

*Not a retrieval defect.* The same answer appears in many chunks -- the awesome-compose samples repeat one `docker compose down` instruction across a dozen READMEs, and command docs appear again under an `alpha` namespace. Recovering 5 of 13 identical chunks answers the question completely and scores 38% recall.

> **Example** (`f5e72bd4`) — How do I configure a remote MCP server in docker-agent to use a static authorization token?  
> Relevant in pool: 4, retrieved: 3, first relevant at rank 1. Top-6 grades: `[2, 3, 1, 3, 1, 0]`.  
> the 'missed' chunk is a near-identical remote-MCP YAML block to the one retrieved at rank 4

**What to do:** A deduplication pass at ingest, or credit at document rather than chunk granularity (the ablation harness already reports both). Do not tune the retriever against this number.

### A common query term pulls in generic prose — 2 case(s)

*Real defect.* The question contains a word the corpus uses everywhere -- 'foreground', 'docker' -- and chunks that merely discuss the word outrank the one chunk that configures it.

> **Example** (`13ba0624`) — How do I add the vscode user to the docker group within a SparkJava Dockerfile?  
> Relevant in pool: 12, retrieved: 5, first relevant at rank 4. Top-6 grades: `[0, 0, 0, 2, 2, 1]`.  
> ranks 1-3 are grade 0 (a compose file, an MLflow changelog, a Node.js blurb) pulled by 'docker'/'SparkJava'; the Dockerfile answer is at rank 4

**What to do:** This is the failure a reranker is supposed to absorb, and ADR-0019 measured rerank as not significantly helpful overall. These cases are where to look for whether a better reranker would earn its cost -- a targeted question, not a general one.

### Repeated boilerplate crowds out the explanatory chunk — 1 case(s)

*Real defect.* Status dumps and reference tables that share the question's vocabulary occupy the whole top-k, pushing the prose that answers it past rank 6.

> **Example** (`be7dad51`) — What command should I run to start the Flask application containers in the background using Docker Compose?  
> Relevant in pool: 4, retrieved: 2, first relevant at rank 7. Top-6 grades: `[1, 1, 1, 1, 1, 1]`.  
> six near-identical 'Listing containers must show...' status dumps occupy ranks 1-6; `docker compose up -d` is at rank 7

**What to do:** A quality gate at ingest for low-information chunks (terminal transcripts, generated flag tables), which `libs/ingestion/quality.py` already has the shape for.

### Right topic, wrong specificity — 1 case(s)

*Real defect.* Retrieval lands on the correct subject area but returns the policy or overview chunk rather than the concrete artifact -- the sign-off rules instead of the commit-message template.

> **Example** (`b86e4994`) — What is the required format and content for a commit message when contributing to the Docker documentation?  
> Relevant in pool: 6, retrieved: 2, first relevant at rank 4. Top-6 grades: `[1, 1, 1, 2, 1, 2]`.  
> retrieves DCO sign-off policy (right topic) but misses the `docs: <description>` commit-message template that actually answers

**What to do:** The clearest candidate for query-side work: these questions ask for a template or command and get prose about it.

### The judge graded a chunk that does not answer the question — 1 case(s)

*Not a retrieval defect.* A chunk graded 3 that does not answer, while the chunk that does was graded lower or left out of the pool. Consistent with ADR-0022's finding that the judge is imperfectly calibrated.

> **Example** (`d46d4ee2`) — How do I launch the MLflow UI to compare my XGBoost training runs?  
> Relevant in pool: 8, retrieved: 3, first relevant at rank 3. Top-6 grades: `[1, 1, 3, 0, 3, 1]`.  
> two `python train.py --learning-rate` chunks graded 3 for a question about launching the MLflow UI; the real answer ('Run mlflow server') was graded lower and not retrieved

**What to do:** Not a retrieval problem. Bounded by the judge-validation work; more human labels shrink it.

### Nothing relevant retrieved at all — 1 case(s)

*Real defect.* No chunk at or above the relevance threshold appears in the top 10, though relevant chunks exist in the judged pool.

> **Example** (`ac6d1ba1`) — Why are two separate GitHub app tokens used in the MLflow UI review workflow instead of the default GITHUB_TOKEN?  
> Relevant in pool: 2, retrieved: 0, first relevant at rank none. Top-6 grades: `[0, 0, 0, 0, 0, 0]`.  
> nothing relevant in the top 10; retrieved the right workflow FILES but never the chunk explaining why two app tokens are used

**What to do:** The only category where the user is left with nothing. Rare here.

## What to fix next, in order

Ranked by count among the categories that are actually defects:

1. **A common query term pulls in generic prose** (2) — This is the failure a reranker is supposed to absorb, and ADR-0019 measured rerank as not significantly helpful overall. These cases are where to look for whether a better reranker would earn its cost -- a targeted question, not a general one.
2. **Right topic, wrong specificity** (1) — The clearest candidate for query-side work: these questions ask for a template or command and get prose about it.
3. **Nothing relevant retrieved at all** (1) — The only category where the user is left with nothing. Rare here.
4. **Repeated boilerplate crowds out the explanatory chunk** (1) — A quality gate at ingest for low-information chunks (terminal transcripts, generated flag tables), which `libs/ingestion/quality.py` already has the shape for.

Note what is *not* on this list: any change motivated purely by raising
`recall@10`. 23 of the 28 flagged cases would be 'fixed' by chasing
that number, and none of those fixes would help a user.

## Limits

- **One coder: `claude-opus-5` — a language model, not a person.** The open coding was
  done by a language model reading each of the 28 cases against the question,
  in the same session that built this module. That is a real limitation and the
  same one [ADR-0022](../adr/0022-judge-validation-against-a-second-rater.md)
  measured directly: on relevance grading this model ran **more lenient** than the
  human rater. A category mix produced by it should be read as a hypothesis to
  check, not a settled description. Every code is committed in
  `evalsets/failure-taxonomy-v1-codes.jsonl` with a free-text note, so the reading
  can be disagreed with case by case rather than in general.
- **No second coder**, so there is no inter-coder agreement to report. Re-coding
  even 10 of these by hand would test the biggest claim here — that most flagged
  failures are not defects — far more cheaply than re-running any retrieval.
- **One retrieval mode** (hybrid, the shipped default) and one corpus. The
  category *mix* is a property of this corpus - a less redundant one would shift
  it substantially.
- **The signal is over-inclusive by design**, so the flag rate is not a failure
  rate and is not quoted as one anywhere above.
- Coding stopped at 28 cases because the categories stopped changing, not
  because the queries ran out. Saturation is a judgement call, and it was the
  coder's.
