# Flagship foundation — local checkpoint

October 23, 2026. Starting commit `c385cc5f867834dc63dc93daa98d323dc98c48fe`.
This is development evidence, not a public release or a completed flagship rebuild.

## Fresh baseline

- 319 Python tests passed, with two upstream warnings.
- Ruff lint/format, Pyright and raw-source-to-browser corpus checks passed.
- Original 31 browser-library/handler tests passed before changes.
- Original term-overlap/BM25 document-level outcomes reproduced. Their historical
  selection data remains regression data; it is not a new holdout.

## Reproduced defects and local repairs

The shared answer validator accepted an abstention with an actionable command and
unknown fields such as `approved: true`. Five counterexamples were exercised both
directly and through the actual HTTP handler before the repair: ten failures, plus
one positive control. The validator now requires exact root/claim/command fields and
rejects claims or commands in an abstention. Citation validation remains structural,
not factual entailment. No command executor was added.

The combined retrieval query sometimes omitted an observed documentation family.
A separate 14-case synthetic **development** set was written and evaluated before
implementing signal-scoped retries. Baseline document-family coverage was 14/20;
candidate coverage is 19/20. Complete family coverage increased from 8 to 11 of the
12 cases with positive family targets. Both empty-query controls remain empty.
The remaining four-family case exceeds the three-passage limit; the workspace now
shows the missing signal explicitly. These are family-presence labels, not answer
correctness, causal diagnosis or a held-out quality gain. Cases were authored after
source inspection and are now public development/regression data.

The first candidate improved the aggregate but replaced the rollout family in the
four-family case with three other families. Per-case comparison caught that swap.
The revised policy preserves families already represented by the baseline before
allocating slots to missing families. The final candidate has no per-case family
coverage regression on this development set. CI checks the frozen dataset identity
and per-case baseline, rather than relying only on the aggregate.

The policy makes at most four retrieval attempts, retains up to three passages and
6,000 evidence characters, and records truncation. It is bounded lexical correction,
not an autonomous self-critiquing model agent or a real token-budget assembler.
The HTTP handler prepares/retrieves once rather than repeating retrieval internally.
New policy source hashes are included in model-report provenance and display checks.

## Validation after the repair

- 48 Node tests passed, including missing-family deletion, context boundary,
  deterministic replay, empty-corpus/no-model and output-boundary cases.
- After the budget-boundary repair, all 333 Python tests passed with three upstream
  warnings. Eighteen focused gateway tests passed. No paid provider was called.
- TypeScript and Next 16.4.1 production build passed with ordinary checks enabled.
- Six real production HTTP pages passed landmark checks after fixing the legacy
  sample console's missing main landmark.
- Actual local production servers exercised excerpts, no-evidence abstention and a
  synthetic valid model response. Invalid output, inconsistent abstention, missing
  upstream and oversized/invalid input reject. No-evidence model calls: zero.
- Synthetic HTTP fixtures are not real model-quality evidence.
- The Next upgrade refreshed vulnerable locked transitive dependencies. npm reported
  four high and one critical findings before the upgrade and zero afterward. CI now
  requires npm audit at high severity and the production HTTP contract check.
- Python dependency advisory remediation and full-stack deployment are not complete.

## Product candidate

The local incident workspace has clearer intake, evidence canvas, visible retrieval
decisions, source-family gaps, context-use indicators and optional analyst notes.
Exports identify unreviewed notes and the corpus revision. The rendered interface,
responsive behavior and actual browser download still need browser QA. Chrome access
approval timed out; no visual-pass claim is made. No further desktop app automation
is planned after the user's computer-care request.

## Remaining flagship work

1. Browser/responsive/keyboard/export verification and design refinement; the shared
   style now also applies to library, evaluation and engineering pages but has not
   yet passed visual QA.
2. A full quality/error review of source-family routing, ambiguous signals and
   unsupported questions; use a separately frozen evaluation for new quality claims.
3. Provider-bound budget review: synthetic tests reproduced the original fail-open
   behavior on missing/unavailable/corrupt counters. The local candidate now refuses
   calls in those paths when its spend guard is enabled. It still checks spend after
   completed calls and does not reserve in-flight spend. This is a post-call threshold,
   not a reliable hard billing cap. No provider call was made. Reservation and retry
   accounting remain necessary before stronger budget claims.
4. Model artifact/quality comparison remains pending. Available RAM was below the
   existing 2.5 GiB CPU-model protocol minimum. Do not load models or close unrelated
   applications to bypass that boundary. No DPO or model benefit claim.
5. Full security/release checks, source/evidence packaging, exact public-release
   approval, staging and real production verification. Existing production unchanged.

Program evidence logs are in the task's `outputs/validation/opsverse-*` files.
Source edits are confined to the isolated OpsVerse checkout; no personal files,
other projects, OS settings or unrelated services were changed.
