# ADR-0022: Validating the relevance judge against a second rater

**Status:** accepted (2026-09-04)

## Context

Every retrieval conclusion this project has published since
[ADR-0019](0019-golden-set-pooled-graded-relevance.md) rests on relevance labels produced
by a single LLM judge (`gemini/gemini-3.1-flash-lite`, via `golden_set.py`). The only
check on that judge was **seed recovery**: each question was written *from* a specific
chunk, so that chunk should grade >= 2, and 100/100 did.

Seed recovery is a sanity check, not an agreement measurement. It asks the judge one
easy question per query — "is the chunk this question was literally generated from
relevant?" — and says nothing about the other ~18 candidates in the pool. A judge that
is confidently and consistently wrong about those passes it unchanged. So the honest
description of `retrieval-golden-v1` was *one rater's opinion, unvalidated*, and that
limitation was stated in every report built on it.

That gap is also the one an evaluation reviewer probes first, and closing it needs no
GPU, no API quota and no new infrastructure — only labels.

## Decision

Measure the judge against an independent rater on a blinded sample, and report the
agreement statistics that decide whether the labels are usable.

**1. Stratify on the judge's binary call.** Only 15.8% of the 1,914 judgements are
relevant (grade >= 2). A simple random sample of ~190 items would carry ~30 positives
and estimate TPR with an interval too wide to conclude anything. The sample is drawn
half from each stratum (96/96 at n=192).

**2. Weight back to the population.** Each item carries its inverse sampling probability
(303/96 = 3.16 for judge-relevant, 1611/96 = 16.78 for judge-not-relevant), so the
balanced sample yields population rates rather than the rates of a design artifact. Both
the weighted and unweighted numbers are printed — the unweighted ones are what a naive
reading of a balanced sample would report, and they differ substantially (TPR 0.876
unweighted vs 0.571 weighted).

**3. Stratified bootstrap for every interval.** Kappa, TPR and TNR are ratios computed
from a contingency table over the whole sample, not means of per-item scores, so
`stats.bootstrap_ci` does not apply. `stats.bootstrap_statistic_ci` recomputes the
statistic on each resample and resamples *within* stratum, matching the design.

**4. Chance-corrected agreement, not raw agreement.** On a pool that is ~84%
non-relevant, a judge that rejected everything scores ~0.84 raw agreement. Cohen's kappa
(binary, at the relevance cut) and quadratic-weighted kappa (graded 0-3, penalising by
squared distance so a 3-vs-2 near miss is not equated with 3-vs-0) are the headline
numbers.

**5. Enforce blinding rather than claiming it.** The annotator file carries only a task
id, the question and the chunk text — no chunk id, no case id, no judge grade (a test
asserts nothing leaks). Tasks are shuffled so strata are not blocked. The rater sees the
same rubric wording and the same 4,000-character excerpt window the judge saw; a test
pins `EXCERPT_CHARS` to `golden_set`'s, because agreement between two raters who read
different amounts of text measures the truncation.

**6. Ask the question that actually threatens the results.** Absolute judge accuracy
could be mediocre without invalidating a *comparison* between retrieval modes, provided
the judge's errors do not favour one mode. Every sampled candidate is tagged with the
modes that retrieved it (from the committed ablation raw JSON), and signed error is
reported per mode.

## What it found

Full report: [`judge-validation-v1.md`](../reports/judge-validation-v1.md).
190 labelled pairs (2 excluded, see below).

**The judge is systematically strict.** Mean signed error (rater − judge) is
**+0.327 [+0.226, +0.430]** on the 0-3 scale — the interval excludes zero, so it is a
calibration offset, not noise. The asymmetry is sharp: **precision 0.968 [0.926, 1.000]**
against **TPR 0.571 [0.464, 0.740]**. When this judge calls a chunk relevant it almost
always is; it misses a large share of what the second rater counts as relevant.

**Agreement is "substantial" but not better than that.** Quadratic-weighted kappa
**0.717 [0.641, 0.787]**, binary kappa **0.648 [0.524, 0.799]**. Agreement within one
grade is **0.972** — the disagreements are near misses on an ordinal scale, not two
raters reading different documents.

**The consequence, stated in both directions.** The graded labels are a conservative
floor, so the relevant-chunk count per query in `retrieval-golden-v1` is probably an
undercount and absolute `recall@k` / `nDCG_graded@k` read low. But the bias is close to
equal across all four modes (+0.317 to +0.412, intervals heavily overlapping), and a
bias shared equally cancels in a paired comparison. **The levels move; the deltas
stand** — ADR-0019's mode-vs-mode conclusions are not overturned.

## What this is not

**This is a second-*model* cross-check, not human validation.** The reference rater is
`claude-opus-5`, not a person. Two LLMs share training data and failure modes, so
model-model agreement is biased *upward*: it is an optimistic ceiling on what human
agreement would be. It can detect a badly miscalibrated judge — and it did — but it
cannot certify a well-calibrated one.

The report says this in its title, an admonition block at the top, and its limits
section, and `--rater-kind model` is what switches that language on. The project's
stated limitation is **narrowed by this, not closed**. Human labels remain the open item
and are the reason `--rater-kind human` is the default.

**Two tasks were excluded for broken blinding.** While verifying the sample, the first
two rows of the key file were printed to the terminal, so the rater had seen the judge's
grade for `t0001` and `t0002` before labelling. They are dropped and named in the report
rather than silently retained.

## Alternatives considered

**Report raw agreement.** Rejected: ~84% of the pool is non-relevant, so raw agreement
is high for a judge that does nothing. It is printed as a secondary row only.

**Sample uniformly at random.** Rejected: ~30 positives in 190 items cannot estimate TPR
usefully. Stratifying and weighting costs one extra concept and buys a usable interval.

**Skip the weighting and report the balanced sample's rates.** Rejected as the more
dangerous option, because the numbers look fine and are wrong: TPR reads 0.876
unweighted against 0.571 weighted. Both are printed so the gap is visible.

**Grade only the pools of a few complete queries** (so retrieval metrics could be fully
recomputed on human labels). Rejected: ~19 candidates/query means 10 queries consume the
entire labelling budget and n=10 moves no conclusion. The per-mode signed-error analysis
answers the question that actually matters — whether judge error threatens the
comparisons — from a stratified sample instead.

## Consequences

- `retrieval-golden-v1`'s absolute figures now carry a measured, directional caveat
  rather than an unquantified one.
- The comparative conclusions in ADR-0019/0020/0021 survive, and now survive *for a
  stated reason* rather than by assumption.
- A future revision of the judge prompt has an untouched `test` half to be evaluated on;
  no prompt has been tuned against these labels, so both halves are held out today.
- `stats.bootstrap_statistic_ci` is available for any future statistic that is not a
  mean of per-item scores.

---

## Update 2026-09-06 — the human labels arrived, and revised this

The open item above ("human labels remain the open item") is now partly closed. A human
rater labelled **40** of the same tasks, drawn as a stratified subset of the v1 sample so
the labels join directly to both the judge key and the model rater's labels. Full
analysis: [`judge-validation-v2.md`](../reports/judge-validation-v2.md).

**What replicated.** The direction and the capability number, cleanly. Both raters grade
*above* the judge, and the judge finds **56%** of what the human calls relevant against
**47%** of what the model does. It misses roughly half the relevant material under either
reference. That is the finding that survives, and it is the one that matters for reading
absolute recall off the golden set.

**What did not.** The magnitude. On the same 40 tasks the model rater puts the offset at
**+0.505 [+0.303, +0.739]** and the human at **+0.226 [−0.076, +0.571]** — which spans
zero. Head to head, the human grades **0.279 [−0.539, −0.018]** of a grade *lower* than
the model, an interval excluding zero. The model rater is systematically **more lenient**,
and leniency in the reference inflates the apparent gap between rater and judge.

So the honest position is now weaker than v1's, in a specific way: *the judge grades below
both raters, but how far below is not established.* n=40 buys a direction, not a magnitude.
Note also that the two offset intervals overlap, so v1's +0.327 is not *refuted* — it is
un-confirmed, with a measured mechanism (rater leniency) for why it may be too high.

**What this says about model-as-rater.** v1 asserted that model-model agreement would be
biased upward and should be read as an optimistic ceiling. That is now measured rather than
asserted, and it held: the model agreed with the judge on the graded scale slightly more
than the human did (quadratic kappa 0.687 vs 0.659) while being more lenient in absolute
grading. The cross-check was **directionally sound and quantitatively soft** — which is a
fair summary of what a second model should be trusted for, and worth carrying into any
future use of LLM-as-judge here.

**Consequences for the decision.** None of the retrieval conclusions change: the per-mode
bias analysis in v1 is unaffected, so the ADR-0019/0020/0021 comparisons still stand. What
changes is how the offset should be quoted — as a direction with an open magnitude, never
as `+0.327` unqualified. The remaining next step is unchanged in kind and smaller in size:
more human labels, and ideally a second *independent* human so this becomes inter-annotator
agreement rather than one author's judgement.
