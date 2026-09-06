# Judge validation v2 - the human labels, and what they revise

Generated 2026-09-06 by `opsverse_evals.judge_validation three-way`. Offline.

[v1](judge-validation-v1.md) audited the judge against a **second model** (n=190) and said plainly that this was an optimistic
ceiling, not human validation, and that human labels remained the open item.
A human rater has now labelled **40** of those same tasks. This report is what
that changed.

## What the human labels confirm

**The direction replicates.** Both raters grade *above* the judge, so the judge is
the strict one under either reference. And the headline capability number is
strikingly stable: the judge finds **56%** of what the human calls relevant and **47%** of what the model
does. It misses roughly half of the relevant material under either rater. That is
the finding that survives.

## What they revise

**The size of the offset is less certain than v1 made it look.** On the *same*
tasks, the two raters disagree about how big it is:

| Mean signed error (rater - judge) | estimate |
|---|---|
| Model rater, full v1 sample (n=190) | +0.327 [+0.226, +0.430] |
| Model rater, on these 40 tasks | +0.505 [+0.303, +0.739] |
| **Human rater, on these 40 tasks** | **+0.226 [-0.076, +0.571]** |

What is *established* here is the gap between the raters, not that v1's number
is wrong: the two offset intervals overlap, so they are not significantly
different from each other. But head to head on the same items, the human
grades **0.28 of a grade lower** than the model (-0.279 [-0.539, -0.018], interval excluding zero). The model rater is systematically
**more lenient**, and leniency in the reference rater inflates the apparent gap
between rater and judge - which is the mechanism that would make v1's +0.327 too
high. Direction measured; magnitude still open.

And on the human labels alone the offset is **not statistically significant**:
+0.226 [-0.076, +0.571] spans zero at n=40. So the honest statement is now weaker than
v1's: the judge grades below both raters, but *how far* below is not established
by these labels. n=40 buys a direction, not a magnitude.

## All three comparisons, on the same tasks

| statistic | human vs judge | model vs judge | human vs model |
|---|---|---|---|
| TPR (rater says relevant -> judge found it) | 0.556 [0.385, 1.000] | 0.472 [0.309, 0.790] | n/a |
| TNR | 1.000 [1.000, 1.000] | 0.988 [0.962, 1.000] | n/a |
| Precision of the judge's 'relevant' | 1.000 [1.000, 1.000] | 0.950 [0.850, 1.000] | n/a |
| Cohen's kappa (binary) | 0.642 [0.425, 1.000] | 0.531 [0.298, 0.857] | 0.682 [0.381, 0.978] |
| Quadratic-weighted kappa (0-3) | 0.659 [0.492, 0.813] | 0.687 [0.541, 0.806] | 0.740 [0.555, 0.874] |
| Exact grade agreement | 0.505 [0.327, 0.682] | 0.497 [0.321, 0.674] | 0.547 [0.363, 0.742] |
| Agreement within one grade | 0.916 [0.790, 1.000] | 0.950 [0.858, 1.000] | 0.958 [0.874, 1.000] |
| Mean signed error (rater - judge) | 0.226 [-0.076, 0.571] | 0.505 [0.303, 0.739] | -0.279 [-0.539, -0.018] |

The asymmetric rows are `n/a` for rater-vs-rater on purpose: TPR and precision
presuppose a ground truth, and between two peer raters there isn't one. Only the
chance-corrected and symmetric statistics are meaningful in that column.

## Was the model rater a usable stand-in?

Partly, and now measurably so rather than as an assumption. The two raters reach
quadratic kappa **0.740** and agree
within one grade **96%** of the time, so
they are not reading different documents. But the model agreed with the judge on
the graded scale slightly *more* than the human did (0.687 vs 0.659), which is the upward bias v1
warned about, and it was simultaneously more lenient in absolute grading, which
biases the signed-error estimate upward. **v1's caveat was the right caveat, and
it was pointing at a real effect.** The cross-check was directionally sound and
quantitatively soft - which is roughly what a second model should be trusted for.

## Limits

- **n=40.** Every interval here is wide; the human column establishes a direction
  and a TPR, not a precise offset. A larger human sample is the obvious next step.
- **Still one human rater**, and still the system's author. This measures
  judge-vs-rater agreement, not inter-annotator agreement among independent people.
- The human labelled a stratified subset of the v1 sample, not a fresh draw, so the
  three comparisons share tasks by design - that is what makes them comparable, and
  it also means they are not independent of one another.
