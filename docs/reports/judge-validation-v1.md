# Judge validation v1 - does the LLM relevance judge agree with a second model?

Generated 2026-09-04 by `opsverse_evals.judge_validation` from the committed
golden set, corpus dump and label file. No Qdrant, no API, no network.

Judge under test: **`gemini/gemini-3.1-flash-lite`** (the judge that labelled
`retrieval-golden-v1`, ADR-0019). Reference rater: **claude-opus-5** (model), one rater,
**190** blinded (question, candidate) pairs.

> [!WARNING]
> **This is a second-model cross-check, not human validation.** The reference
> rater here is `claude-opus-5`, not a person. Two LLMs share training data and
> failure modes, so model-model agreement is biased **upward** and sets an
> optimistic ceiling rather than a ground truth. It can detect a judge that is
> badly miscalibrated; it cannot certify one that is well calibrated. The
> project's stated limitation - *the golden set is one rater's opinion* - is
> **narrowed by this report, not closed**. Human labels remain the open item.

## What this found

**The judge is systematically stricter than the reference rater.** Mean
signed error +0.327 [+0.226, +0.430] on a 0-3 scale - the interval excludes zero, so this
is a calibration offset, not noise. It shows up as an asymmetry, not as random
disagreement: precision 0.968 [0.926, 1.000] against TPR 0.571 [0.464, 0.740].
When this judge calls a chunk relevant it almost always is; it misses a large
share of what the other rater counts as relevant.

**What that costs.** The graded labels are a conservative floor, so the count of
relevant chunks per query in `retrieval-golden-v1` is likely an *under*count, and
absolute `recall@k` / `nDCG_graded@k` on that set read low. Any absolute number
quoted from the golden set should be read with that direction of bias attached.

**What it does not cost.** The bias is close to equal across all four retrieval
modes (see the per-mode table), and a bias shared equally cancels in a paired
comparison. The mode-vs-mode conclusions in ADR-0019 - dense significantly worse
than hybrid, sparse-vs-hybrid a tie, rerank no measurable help - are not
overturned by this. The *levels* move; the *deltas* stand.

Chance-corrected agreement is 0.717 [0.641, 0.787] (quadratic-weighted,
graded) and 0.648 [0.524, 0.799] (binary, at the relevance cut) -
'substantial' on the conventional reading, and agreement within one grade is
0.972 [0.938, 0.998]. The disagreements are near misses on an
ordinal scale, not two raters reading different documents.

## Why this exists

Every retrieval conclusion in this project rests on one LLM judge's labels. The
only check on it so far was **seed recovery** - the chunk each question was written
from graded >= 2, 100/100. That detects a badly broken judge and nothing else: a
judge that is confidently wrong about the other ~19 candidates per query passes it
unchanged. Until now the honest description of the golden set was *one rater's
opinion, unvalidated*, and that limitation is stated in every report that uses it.

## Design

- **Stratified on the judge's binary call.** Only 15.8% of the 1,914 judgements are
  relevant (grade >= 2), so a simple random sample would carry too few positives to
  estimate TPR usefully. Half the sample is drawn from each stratum.
- **Inverse sampling weights** (stratum population / stratum sample) recover the
  population rates from the balanced sample. Both weighted and unweighted numbers
  are printed below; the weighted ones are the population estimates.
- **Stratified bootstrap** (2,000 resamples within stratum) for every interval,
  because kappa and TPR are table ratios, not means of per-item scores.
- **Blinded.** The labeling file carries no chunk id, no case id and no judge grade;
  tasks are shuffled so strata are not blocked. Same rubric wording and same
  4,000-character excerpt window the judge saw.

## Agreement

| statistic | weighted (population) | unweighted (in-sample) |
|---|---|---|
| TPR - judge finds what the rater calls relevant | 0.571 [0.464, 0.740] | 0.876 |
| TNR - judge rejects what the rater calls irrelevant | 0.993 [0.984, 1.000] | 0.965 |
| Precision - judge's 'relevant' the rater confirms | 0.968 [0.926, 1.000] | 0.968 |
| NPV - judge's 'not relevant' the rater confirms | 0.863 [0.789, 0.937] | 0.863 |
| Cohen's kappa (binary, relevance cut) | 0.648 [0.524, 0.799] | 0.832 |
| Quadratic-weighted kappa (graded 0-3) | 0.717 [0.641, 0.787] | 0.829 |
| Exact grade agreement | 0.626 [0.537, 0.707] | 0.658 |
| Agreement within one grade | 0.972 [0.938, 0.998] | - |
| Mean signed error (rater - judge) | +0.327 [+0.226, +0.430] | - |

Kappa reference points (Landis & Koch, the conventional reading): 0.21-0.40 fair,
0.41-0.60 moderate, 0.61-0.80 substantial, 0.81+ almost perfect. Raw agreement is
not reported as a headline because a pool that is ~84% non-relevant makes it easy:
a judge that rejected everything would score ~0.84 raw and 0.00 kappa.

### Confusion matrix (unweighted counts, rows = rater, cols = judge)

| rater \ judge | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| **0** | 14 | 2 | 0 | 0 |
| **1** | 22 | 44 | 2 | 1 |
| **2** | 2 | 10 | 15 | 8 |
| **3** | 0 | 1 | 17 | 52 |

At the relevance cut (grade >= 2), unweighted: tp=92, fp=3,
fn=13, tn=82.

## Does judge error favour any retrieval mode?

This is the question that decides whether the published *comparisons* survive.
Absolute judge accuracy could be mediocre without invalidating a mode-vs-mode
delta, provided the judge's errors do not systematically favour one mode. Each row
is the weighted mean of (rater - judge) over the sampled candidates that mode
retrieved; positive means the judge under-graded what that mode found.

| retrieval mode | n | mean signed error [95% CI] | judged relevant |
|---|---|---|---|
| dense | 105 | +0.362 [+0.210, +0.499] | 0.22 |
| hybrid | 125 | +0.356 [+0.233, +0.482] | 0.23 |
| hybrid+rerank | 124 | +0.412 [+0.285, +0.546] | 0.20 |
| sparse | 117 | +0.317 [+0.186, +0.449] | 0.21 |

Intervals that overlap each other give no evidence of mode-dependent bias. That is
the condition the golden-set comparisons need; it is weaker than the judge being
accurate, and it is the right one, because a bias shared equally by all four modes
cancels in a paired comparison between them.

Two honest caveats on this table. The rows are **not independent samples** - the
pool is shared, so most sampled chunks were retrieved by several modes at once and
the same item appears in several rows. And 'no significant difference' at this n is
not proof of no difference; it bounds the effect rather than excluding it. The
claim this table supports is the narrow one: **no mode-dependent judge bias is
detectable at n~120 per mode**, which is what the paired comparisons need.

## Seed recovery, re-checked

The judge recovered **100%** of originating chunks at grade >= 2 (ADR-0019).
On the 29 seed chunks that fell in this sample, the reference rater graded
**100%** of them >= 2. A gap here would mean the seed-recovery check
was easier than the judging task it was standing in for.

## dev / test split

The sample is split in half within each stratum. No judge prompt was tuned
against these labels, so both halves are held out today; the split exists so
that a future revision of the judge prompt has an untouched test set rather
than being evaluated on data it was fitted to.

| split | n | binary kappa | quadratic kappa | TPR | TNR |
|---|---|---|---|---|---|
| dev | 95 | 0.676 | 0.741 | 0.596 | 0.995 |
| test | 95 | 0.622 | 0.693 | 0.547 | 0.991 |

## Limits

- **One rater.** This measures judge-vs-rater agreement, not inter-annotator
  agreement, so it cannot separate 'the judge is wrong' from 'this rater is
  unusual'. A second independent rater is the next step, and until there is one
  the reference column is a reference, not ground truth.
- **The reference rater is a language model, not a person.** Model-model
  agreement shares training data and failure modes with the judge, so it is
  biased upward: it is an optimistic ceiling on what human agreement would be,
  never a substitute for it. Read every number here as 'the judge is at most
  this consistent', not 'the judge is this correct'.
- **n = 190** pairs across 190 sampled tasks. The
  intervals above are what that buys; they are printed on every number for that
  reason.
- Agreement is measured on this corpus and this rubric only.
- **2 task(s) excluded for broken blinding**: `t0001`, `t0002`.
  The rater had seen the judge's grade for these before labelling, so they
  are not independent observations and are dropped rather than counted.
