# Who grades the grader? I audited my LLM judge — and then had to audit the audit

*OpsVerse AI is an LLM inference and evaluation platform for DevOps knowledge.
Every retrieval conclusion in it rested on labels from a single LLM judge. This
is what happened when I finally checked that judge — and what happened when I
checked the thing I checked it with.*

## The uncomfortable dependency

My retrieval evaluation is, by the standards of a side project, careful. Pooled
TREC-style relevance judgements across four retrieval modes. Graded 0–3, not
binary. Candidate order randomised per query so no system's ranking leaks into
the labels. 1,914 judgements over 100 queries. Bootstrap confidence intervals on
every mean, paired permutation tests on every comparison.

All of it rests on one LLM deciding which chunks are relevant.

I had exactly one check on that judge: **seed recovery**. Each question was
generated *from* a specific chunk, so that chunk should be graded relevant. It
was, 100 times out of 100.

That number looks reassuring and isn't. Seed recovery asks the judge one easy
question per query — "is the chunk this question was literally written from
relevant?" — and says nothing about the other eighteen candidates in the pool. A
judge that is confidently, consistently wrong about those passes it unchanged.

So the honest description of my golden set was *one rater's opinion,
unvalidated*. Which is fine to write in a limitations section, and not fine to
leave there forever.

## Designing the audit

Two decisions did most of the work.

**Stratify on the judge's own call.** Only 15.8% of the 1,914 judgements are
relevant. A random sample of ~190 items would carry ~30 positives, and a true
positive rate estimated from 30 items has an interval too wide to conclude
anything. So I sampled half from each stratum — 96 items the judge called
relevant, 96 it didn't — and gave each item an inverse sampling weight
(303/96 and 1611/96) to recover population rates from the deliberately
unrepresentative sample.

That weighting is not a detail. Unweighted, the sample says TPR = 0.876.
Weighted, it says **0.571**. The unweighted number is what a naive reading of a
balanced sample reports, and it is wrong by a mile. I print both, because the
gap is the whole lesson.

**Enforce the blinding instead of claiming it.** The annotator file carries a
task id, the question, and the chunk text. No chunk id, no case id, no judge
grade — a unit test asserts none of them leak into it. Tasks are shuffled so the
strata aren't blocked, because a rater who notices a run of relevant items starts
predicting rather than judging. And the rater sees the *same rubric* and the
*same 4,000-character excerpt window* the judge saw; a test pins that constant to
the judge's, because agreement between two raters who read different amounts of
text measures the truncation, not the raters.

Chance-corrected agreement, not raw agreement, is the headline. On a pool that's
84% non-relevant, a judge that rejected everything scores 0.84 raw. Cohen's kappa
scores it 0.

## What the audit found

The judge is **systematically strict**. Signed error +0.327 [+0.226, +0.430] on
the 0–3 scale — an interval excluding zero, so a calibration offset rather than
noise. And the asymmetry is sharp: **precision 0.968, TPR 0.571**. When this
judge calls a chunk relevant, it almost always is. It misses about half of what
the reference rater counts as relevant.

That has a consequence worth stating in both directions, because only one of
them is comfortable:

- **Bad:** my absolute `recall@k` and `nDCG@k` read low. The relevant-chunk count
  per query is a conservative undercount.
- **Fine:** the bias is near-equal across all four retrieval modes (+0.317 to
  +0.412, intervals heavily overlapping), and a bias shared equally *cancels* in
  a paired comparison. So every mode-vs-mode conclusion I'd published survived.

**The levels move; the deltas stand.** That distinction is the reason the audit
was worth running rather than just worrying about.

## The part where the audit needed auditing

Here's the thing I should be most honest about. My reference rater for that audit
was **a second language model**, not a person.

I said so at the time — in the report's title, in a warning block at the top, in
its limits section. Two LLMs share training data and failure modes, so
model-model agreement is biased *upward*: an optimistic ceiling, not a ground
truth. It can detect a badly miscalibrated judge. It cannot certify a
well-calibrated one.

Then I did the boring thing and labelled 40 of the same tasks by hand.

The direction replicated cleanly. The judge finds **56%** of what the human calls
relevant against **47%** of what the model does — it misses roughly half the
relevant material under either reference. That's the finding that survived, and
it's the one that matters.

The magnitude did not:

| Mean signed error (rater − judge) | estimate |
|---|---|
| Model rater, full sample (n=190) | +0.327 [+0.226, +0.430] |
| Model rater, on the same 40 tasks | +0.505 [+0.303, +0.739] |
| **Human rater, on those 40 tasks** | **+0.226 [−0.076, +0.571]** |

The human interval **spans zero**. And head to head on identical items, the human
graded **0.279 [−0.539, −0.018]** of a grade *lower* than the model — an interval
excluding zero. **The model rater was the lenient one**, and leniency in your
reference rater inflates the apparent gap between rater and judge.

Stated precisely, because it would be easy to overclaim in either direction: the
two offset intervals overlap, so +0.327 isn't *refuted*. It's un-confirmed, with
a measured mechanism for why it's probably too high. The honest position is now
weaker than the one I published a week ago. **n=40 buys a direction, not a
magnitude.**

The caveat I'd written on instinct turned out to be measurable, and it held: the
model agreed with the judge on the graded scale slightly more than the human did
(quadratic kappa 0.687 vs 0.659) while grading more leniently overall. The
cross-check was **directionally sound and quantitatively soft** — which is a fair
summary of what a second model should be trusted for.

## And separately: most of my "failures" weren't

While I was at it, I did the other thing my evaluation had never done. I'd
measured retrieval to four decimal places and could not show you a single
failure. Every report was an aggregate, and an aggregate can't tell you whether a
low `recall@10` is one systematic defect or twenty unrelated ones.

So: a deliberately over-inclusive signal flagged 28 of 100 queries as failures.
I read all 28 against their questions, described each concretely — "six
near-identical status dumps occupy ranks 1–6", never "bad retrieval" — and then
grouped the descriptions, labelling each group with whether it was a real defect
or an artifact of the corpus or the labels.

**23 of the 28 (82%) are not retrieval defects.** Five are — 5% of queries, not
the 28% the flag rate implied.

The two biggest categories are the metric describing my corpus rather than my
retriever. Eighteen cases where a grade-3 answer sits at rank 1–3 and `recall@10`
marks the query down anyway, because the corpus offers many acceptable answers
per question. Four where the "relevant set" is near-duplicates of itself — the
awesome-compose samples repeat one `docker compose down` instruction across a
dozen READMEs, so recovering 5 of 13 identical chunks answers the question
completely and scores 38% recall.

That's a second, independent mechanism behind the low absolute recall, sitting
alongside the judge's strictness. And it changed my fix list completely:
**nothing on it is motivated by raising `recall@10`**, because most of what would
raise that number wouldn't help a single user.

(The coding was done by a language model, not by me — named in the report and in
its limits, for exactly the reason the last section exists. Re-coding ten of
those cases by hand is the cheapest available test of the 82% claim, and it's
still open.)

## What I'd take from this

Three things, in increasing order of how much they cost me to learn.

**A sanity check is not a validation.** 100% seed recovery felt like evidence and
was closer to a tautology. If your check can be passed by a system that's wrong
about everything you didn't check, it isn't measuring what you think.

**Aggregates hide their own composition.** A mean can't tell you whether it's one
big problem or a property of your data. The only way to find out is to read the
failures — all of them, individually, against the actual question. It took an
afternoon and it invalidated the fix list I would otherwise have worked from.

**Every layer of measurement needs its own measurement, and you have to be
willing to publish it when the new layer contradicts the old one.** I audited my
judge and found it strict. Then I audited my auditor and found it lenient, which
means the strictness I'd reported was overstated. The second result is less
flattering than the first and more likely to be true, and there is no version of
this where I get to keep only the flattering one.

---

*Reports, raw JSON, the committed label files, and the ADRs behind all of this
are in [the repo](https://github.com/dilipna/OPsVerse) — including a one-page
[claim ledger](https://ops-verse.vercel.app/overturns.html) of every conclusion
this project has had to withdraw.*
