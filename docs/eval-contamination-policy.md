# Eval-Set Contamination Policy

**Status:** active (v1, 2026-07-13) · **Enforced by:** `opsverse_evals.contamination`

## The rule

No content from a frozen eval set may appear in any training dataset
(SFT instruction pairs, DPO preference pairs, or any future fine-tuning data).
If OpsLM has seen an eval question during training, every "before vs after"
number built on that set is worthless — this policy exists so the Phase 5
model claims stay defensible.

## What counts as frozen

Every `evalsets/*.jsonl` file, excluding `*.partial.jsonl` working files.
Frozen means: **never edited in place**. Fixing or extending an eval set means
writing a new versioned file (`retrieval-v2.jsonl`), keeping the old one for
comparability. Current frozen sets:

| File | Cases | SHA-256 |
|---|---|---|
| `evalsets/retrieval-v1.jsonl` | 100 | `a87f652e0c88cd728ddb5d0f74baeb4b09300444080bd01bc1a94203fcd4fbd6` |
| `evalsets/retrieval-v2.jsonl` | 100 | `b8958fd3894ae7ae6793ffb8584e091560f60820822712755b390fface495c1c` |
| `evalsets/retrieval-v3.jsonl` | 100 | `4369a0476c4b5864dbb75e41aa3e07fe0c95b121f98c8fa57776ad8924a31463` |
| `evalsets/ci/retrieval-ci.jsonl` | 25 | subset of retrieval-v1 (first 25 cases); protected via v1 |

(The file hash is recorded at freeze time; git history is the audit trail.
New frozen sets get a row here in the same PR that adds them.)

## Enforcement mechanism

Two layers, both implemented in `libs/evals/src/opsverse_evals/contamination.py`
and unit-tested:

1. **Exact match:** SHA-256 over a *normalized* question (casefold, strip
   punctuation, collapse whitespace). The normalization function is part of
   this policy — changing it invalidates stored hashes and requires a policy
   revision.
2. **Near-duplicate:** 5-gram token shingles, Jaccard similarity ≥ 0.6 against
   any eval question. This catches paraphrases, which are the realistic leak
   path: the Phase 5 instruction generator and the eval-set generator are the
   same model family looking at the same corpus, so independently generated
   near-identical questions are expected, not hypothetical.

Every training-data pipeline MUST route candidate examples through
`ContaminationGuard.from_evalsets_dir(Path("evalsets"))` before writing
output, and MUST report the dropped count in its dataset manifest. A dataset
whose manifest lacks a `decontamination` entry does not get trained on.

## Direction of protection

The guard protects eval **questions** from entering training **inputs**.
Corpus text itself is *not* contamination: eval questions were generated from
corpus chunks, and training pairs are generated from the same corpus — shared
source material is by design. What must never transfer is the question
(or a paraphrase of it), because that is what the eval measures generalization
against.

## Known limitations (accepted)

- Semantic duplicates below 0.6 shingle Jaccard (aggressive rewording) can
  slip through. Embedding-similarity dedup was considered and deferred: the
  shingle check already catches same-generator paraphrases, and an embedding
  threshold adds a tunable free parameter with no labeled data to tune it on.
- The policy governs data this repo generates. It cannot say anything about
  the base model's (Qwen3-4B) pretraining corpus — base-model contamination
  is disclosed as a caveat in eval reports, not "solved".
