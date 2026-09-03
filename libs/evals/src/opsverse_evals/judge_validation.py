"""Validate the LLM relevance judge against human labels.

Why this exists
---------------
Every retrieval conclusion in this project rests on labels produced by one LLM
judge (`golden_set.py`, ADR-0019). The only check on that judge so far is
**seed recovery**: the chunk each question was written from should grade >= 2,
and 100/100 did. That is a sanity check, not an agreement measurement. It can
only detect a judge that is badly broken; a judge that is confidently and
consistently *wrong* about the other ~19 candidates per query passes it.

So the honest statement of the project's own limitation is: the golden set is
one rater's opinion, unvalidated. This module closes that gap by measuring the
judge against a human rater on a blinded sample, and reporting the agreement
statistics that make the judge's output either usable or not:

  * **TPR / TNR** at the relevance threshold (grade >= 2), taking the human as
    the reference. These are the numbers that say what a "relevant" label means.
  * **Cohen's kappa** (binary) and **quadratic-weighted kappa** (graded 0-3),
    which discount the agreement that chance alone would produce -- on a pool
    that is 84% non-relevant, raw agreement of 85% is worth nothing.
  * **Signed error per retrieval mode**, which is the question that actually
    threatens the published results. Absolute judge accuracy could be mediocre
    without invalidating a *comparison* between modes, as long as the judge's
    errors do not favour one mode over another. That is testable, and it is
    tested here.

The sampling design
-------------------
Only 15.8% of the 1,914 judgements are relevant (grade >= 2). A simple random
sample of ~190 items would contain ~30 positives, which estimates TPR with an
interval too wide to conclude anything. So sampling is **stratified on the
judge's binary call**, half from each stratum, and every item carries an inverse
sampling weight (stratum population / stratum sample size). Population rates are
recovered by weighting; the CIs come from a bootstrap that resamples *within*
stratum, matching the design (`stats.bootstrap_statistic_ci`).

Both the weighted (population) and the unweighted (within-sample) numbers are
reported. The unweighted ones are what a naive analysis of a balanced sample
would print, and they are not the population rates -- showing both is cheaper
than explaining the difference twice.

Blinding
--------
The annotator's file (`*-tasks.jsonl`) carries only a task id, the question and
the chunk text -- no chunk id, no case id, no judge grade -- and the tasks are
shuffled so strata are not blocked. The judge's grades live in a separate
`*-key.jsonl`. The annotator sees the *same* rubric and the *same* excerpt
window the judge saw (`EXCERPT_CHARS`), because an agreement number between two
raters who read different amounts of text measures the truncation, not the
raters.

Fully offline: reads the committed golden set, corpus dump and ablation raw
JSON. No Qdrant, no API, no network.

Usage:
    # 1. draw the blinded sample (writes tasks + key + the labeling page)
    uv run python -m opsverse_evals.judge_validation sample --n 192

    # 2. open the printed HTML file, label every task, click Download
    #    -> evalsets/judge-validation-v1-labels.jsonl

    # 3. score it
    uv run python -m opsverse_evals.judge_validation score
"""

import argparse
import json
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opsverse_evals.schemas import (
    GradedRetrievalDataset,
    HumanLabel,
    JudgeValidationKey,
    JudgeValidationTask,
)
from opsverse_evals.stats import bootstrap_statistic_ci

# Must equal `golden_set.EXCERPT_CHARS`: the human rater has to see exactly the
# text the judge saw, or the agreement number is contaminated by truncation.
# `tests/test_judge_validation.py` pins the two together.
EXCERPT_CHARS = 4000

# The relevance cut used everywhere else in the project (GradedRetrievalDataset
# .relevance_threshold, metrics.*_graded). Kept as a constant so the binary
# collapse in this module cannot silently disagree with the metrics.
THRESHOLD = 2

MAX_GRADE = 3

STRATUM_POS = "judge_relevant"
STRATUM_NEG = "judge_not_relevant"

# Verbatim from `golden_set.PROMPT` -- the annotator grades against the same
# rubric wording the judge was given. A paraphrased rubric would measure how the
# two rubrics differ.
RUBRIC = [
    ("3", "fully answers the question on its own"),
    ("2", "substantially relevant; answers part of it or gives most of what is needed"),
    ("1", "on-topic / same technology, but does not answer the question"),
    ("0", "not relevant to the question"),
]


@dataclass(frozen=True)
class LabelPair:
    """One human/judge grade pair with its design weight.

    Frozen and self-contained so `bootstrap_statistic_ci` can resample these
    directly and recompute any statistic on the resample.
    """

    human: int
    judge: int
    weight: float
    stratum: str
    retrieved_by: tuple[str, ...]
    is_seed: bool

    @property
    def human_relevant(self) -> bool:
        return self.human >= THRESHOLD

    @property
    def judge_relevant(self) -> bool:
        return self.judge >= THRESHOLD


# --------------------------------------------------------------------------
# agreement statistics (pure functions over LabelPair, so they bootstrap)
# --------------------------------------------------------------------------


def _w(pairs: Sequence[LabelPair], weighted: bool) -> list[float]:
    return [p.weight if weighted else 1.0 for p in pairs]


def confusion(pairs: Sequence[LabelPair], weighted: bool = True) -> list[list[float]]:
    """4x4 contingency table, rows = human grade, cols = judge grade."""
    table = [[0.0] * (MAX_GRADE + 1) for _ in range(MAX_GRADE + 1)]
    for p, w in zip(pairs, _w(pairs, weighted), strict=True):
        table[p.human][p.judge] += w
    return table


def binary_counts(pairs: Sequence[LabelPair], weighted: bool = True) -> tuple[float, ...]:
    """(tp, fp, fn, tn) with the human as reference and the judge as the test."""
    tp = fp = fn = tn = 0.0
    for p, w in zip(pairs, _w(pairs, weighted), strict=True):
        if p.human_relevant and p.judge_relevant:
            tp += w
        elif not p.human_relevant and p.judge_relevant:
            fp += w
        elif p.human_relevant and not p.judge_relevant:
            fn += w
        else:
            tn += w
    return tp, fp, fn, tn


def tpr(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    """P(judge calls it relevant | human calls it relevant). Sensitivity."""
    tp, _, fn, _ = binary_counts(pairs, weighted)
    return tp / (tp + fn) if (tp + fn) else 0.0


def tnr(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    """P(judge calls it non-relevant | human calls it non-relevant). Specificity."""
    _, fp, _, tn = binary_counts(pairs, weighted)
    return tn / (tn + fp) if (tn + fp) else 0.0


def precision(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    """Of the items the judge labelled relevant, the share the human agrees on."""
    tp, fp, _, _ = binary_counts(pairs, weighted)
    return tp / (tp + fp) if (tp + fp) else 0.0


def npv(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    """Of the items the judge labelled non-relevant, the share the human agrees on."""
    _, _, fn, tn = binary_counts(pairs, weighted)
    return tn / (tn + fn) if (tn + fn) else 0.0


def cohen_kappa_binary(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    """Chance-corrected agreement on the relevant / not-relevant collapse.

    Raw agreement is a misleading statistic on a pool that is ~84% non-relevant:
    a judge that called everything non-relevant would score 0.84. Kappa measures
    the agreement above what the two raters' marginals would produce by chance,
    so that same degenerate judge scores 0.
    """
    tp, fp, fn, tn = binary_counts(pairs, weighted)
    total = tp + fp + fn + tn
    if total <= 0:
        return 0.0
    p_obs = (tp + tn) / total
    human_pos, judge_pos = (tp + fn) / total, (tp + fp) / total
    p_exp = human_pos * judge_pos + (1 - human_pos) * (1 - judge_pos)
    return (p_obs - p_exp) / (1 - p_exp) if p_exp < 1 else 1.0


def quadratic_weighted_kappa(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    """Chance-corrected agreement on the full 0-3 scale, penalising by distance^2.

    The right statistic for an ordinal scale: disagreeing 3-vs-2 is a near miss,
    disagreeing 3-vs-0 is a different judgement, and binary kappa cannot tell
    those apart because it throws the grades away.
    """
    obs = confusion(pairs, weighted)
    total = sum(sum(row) for row in obs)
    if total <= 0:
        return 0.0
    rows = [sum(row) for row in obs]
    cols = [sum(obs[i][j] for i in range(MAX_GRADE + 1)) for j in range(MAX_GRADE + 1)]
    denom_w = MAX_GRADE**2
    num = den = 0.0
    for i in range(MAX_GRADE + 1):
        for j in range(MAX_GRADE + 1):
            wt = ((i - j) ** 2) / denom_w
            num += wt * obs[i][j]
            den += wt * (rows[i] * cols[j] / total)
    return 1.0 - num / den if den > 0 else 1.0


def exact_agreement(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    table = confusion(pairs, weighted)
    total = sum(sum(row) for row in table)
    return sum(table[i][i] for i in range(MAX_GRADE + 1)) / total if total else 0.0


def adjacent_agreement(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    """Share agreeing within one grade -- the ordinal scale's near-miss rate."""
    table = confusion(pairs, weighted)
    total = sum(sum(row) for row in table)
    if not total:
        return 0.0
    close = sum(
        table[i][j] for i in range(MAX_GRADE + 1) for j in range(MAX_GRADE + 1) if abs(i - j) <= 1
    )
    return close / total


def mean_signed_error(pairs: Sequence[LabelPair], weighted: bool = True) -> float:
    """Weighted mean of (human - judge).

    Positive means the judge grades *below* the human (too strict); negative
    means it inflates. A near-zero value with a tight interval says the judge is
    unbiased on average, which is a weaker claim than being accurate and a
    different one -- both are reported.
    """
    ws = _w(pairs, weighted)
    total = sum(ws)
    if not total:
        return 0.0
    return sum((p.human - p.judge) * w for p, w in zip(pairs, ws, strict=True)) / total


# --------------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------------


def load_chunk_text(corpus: Path) -> dict[str, str]:
    """chunk_id -> text, from the committed corpus dump."""
    texts: dict[str, str] = {}
    with corpus.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                texts[rec["id"]] = rec.get("text", "")
    return texts


def retrieval_map(raw_path: Path) -> dict[tuple[str, str], list[str]]:
    """(case_id, chunk_id) -> the retrieval modes that surfaced that chunk.

    Read from the committed ablation raw JSON, so the mode-bias analysis needs
    no retrieval run of its own.
    """
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], list[str]] = {}
    for mode, cases in raw["results"].items():
        for case in cases:
            for chunk_id in case["retrieved_chunk_ids"]:
                out.setdefault((case["case_id"], chunk_id), []).append(mode)
    return out


def draw_sample(
    golden: GradedRetrievalDataset,
    texts: dict[str, str],
    modes: dict[tuple[str, str], list[str]],
    n_total: int,
    seed: int,
) -> tuple[list[JudgeValidationTask], list[JudgeValidationKey]]:
    """Stratified sample of judged (query, candidate) pairs, blinded for labeling.

    Half the sample comes from each stratum of the judge's binary call. Within a
    stratum the draw is a simple random sample, so the grade mix inside it stays
    representative in expectation and one weight per stratum is sufficient.
    """
    population: dict[str, list[tuple[str, str, str, int, bool]]] = {
        STRATUM_POS: [],
        STRATUM_NEG: [],
    }
    for case in golden.cases:
        for chunk_id, grade in case.grades.items():
            if not texts.get(chunk_id):
                continue
            stratum = STRATUM_POS if grade >= THRESHOLD else STRATUM_NEG
            population[stratum].append(
                (case.id, chunk_id, case.question, grade, chunk_id == case.seed_chunk_id)
            )

    rng = random.Random(seed)
    per_stratum = n_total // 2
    drawn: list[tuple[tuple[str, str, str, int, bool], str, float, str]] = []
    for stratum, items in population.items():
        take = min(per_stratum, len(items))
        picked = rng.sample(items, take)
        weight = len(items) / take if take else 0.0
        for i, item in enumerate(picked):
            # alternate dev/test *within* stratum so both halves stay balanced
            drawn.append((item, stratum, weight, "dev" if i % 2 == 0 else "test"))

    # shuffle so strata are not blocked in the labeling order: an annotator who
    # notices a run of relevant items starts predicting instead of judging
    rng.shuffle(drawn)

    tasks: list[JudgeValidationTask] = []
    keys: list[JudgeValidationKey] = []
    for idx, (item, stratum, weight, split) in enumerate(drawn, 1):
        case_id, chunk_id, question, grade, is_seed = item
        task_id = f"t{idx:04d}"
        tasks.append(
            JudgeValidationTask(
                task_id=task_id,
                question=question,
                chunk_text=texts[chunk_id][:EXCERPT_CHARS],
            )
        )
        keys.append(
            JudgeValidationKey(
                task_id=task_id,
                case_id=case_id,
                chunk_id=chunk_id,
                judge_grade=grade,
                stratum=stratum,
                weight=weight,
                split=split,
                retrieved_by=sorted(modes.get((case_id, chunk_id), [])),
                is_seed_chunk=is_seed,
            )
        )
    return tasks, keys


def write_jsonl(path: Path, records: Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(r.model_dump_json() for r in records) + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# the labeling page
# --------------------------------------------------------------------------

_LABELER_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin:0; font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;
  background:#0f1115; color:#e6e6e6; }
header { position:sticky; top:0; background:#161922; border-bottom:1px solid #2a2f3a;
  padding:10px 18px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
h1 { font-size:14px; margin:0; font-weight:600; letter-spacing:.02em; }
#bar { flex:1; height:6px; background:#2a2f3a; border-radius:3px; overflow:hidden;
  min-width:160px; }
#fill { height:100%; width:0; background:#4ea1ff; transition:width .15s; }
#count { font-variant-numeric:tabular-nums; font-size:13px; color:#9aa4b2; }
button { font:inherit; padding:6px 12px; border-radius:6px; border:1px solid #39404e;
  background:#222736; color:#e6e6e6; cursor:pointer; }
button:hover { background:#2c3244; }
main { max-width:900px; margin:0 auto; padding:22px 18px 120px; }
.q { font-size:18px; font-weight:600; margin:0 0 6px; }
.meta { color:#8b94a3; font-size:12px; margin-bottom:18px; }
pre { white-space:pre-wrap; word-wrap:break-word; background:#141821; border:1px solid #262b36;
  border-radius:8px; padding:16px; font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;
  max-height:52vh; overflow:auto; }
footer { position:fixed; bottom:0; left:0; right:0; background:#161922;
  border-top:1px solid #2a2f3a; padding:12px 18px; display:flex; gap:10px;
  justify-content:center; flex-wrap:wrap; }
.g { min-width:190px; text-align:left; }
.g b { display:inline-block; width:16px; }
.done { color:#57d9a3; }
#rubric { color:#8b94a3; font-size:12px; max-width:900px; margin:0 auto; padding:0 18px 8px; }
"""

_LABELER_JS = """
const KEY = 'opsverse-judge-labels-v1';
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { labels = {}; }
let i = 0;
// resume at the first unlabelled task
while (i < TASKS.length && labels[TASKS[i].task_id] !== undefined) i++;
if (i >= TASKS.length) i = Math.max(0, TASKS.length - 1);

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {}
}
function done() { return Object.keys(labels).length; }
function render() {
  const t = TASKS[i];
  document.getElementById('q').textContent = t.question;
  document.getElementById('text').textContent = t.chunk_text;
  document.getElementById('text').scrollTop = 0;
  const cur = labels[t.task_id];
  document.getElementById('meta').textContent =
    'task ' + (i + 1) + ' of ' + TASKS.length + (cur === undefined ? '' : '  -  graded ' + cur);
  document.getElementById('count').textContent = done() + ' / ' + TASKS.length + ' labelled';
  document.getElementById('fill').style.width = (100 * done() / TASKS.length) + '%';
  document.querySelectorAll('.g').forEach(b => {
    b.classList.toggle('done', cur !== undefined && +b.dataset.g === cur);
  });
}
function grade(g) {
  labels[TASKS[i].task_id] = g;
  save();
  if (i < TASKS.length - 1) i++;
  render();
}
function move(d) { i = Math.min(TASKS.length - 1, Math.max(0, i + d)); render(); }
document.addEventListener('keydown', e => {
  if (['0','1','2','3'].includes(e.key)) { grade(+e.key); e.preventDefault(); }
  else if (e.key === 'ArrowLeft') { move(-1); e.preventDefault(); }
  else if (e.key === 'ArrowRight') { move(1); e.preventDefault(); }
});
function download() {
  const lines = TASKS.filter(t => labels[t.task_id] !== undefined)
    .map(t => JSON.stringify({ task_id: t.task_id, human_grade: labels[t.task_id] }));
  const blob = new Blob([lines.join('\\n') + '\\n'], { type: 'application/x-ndjson' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'judge-validation-v1-labels.jsonl';
  a.click();
}
render();
"""


def render_labeler(tasks: Sequence[JudgeValidationTask], title: str) -> str:
    """A single self-contained HTML page: no server, no network, no build step.

    Progress is autosaved to localStorage after every keystroke, because this is
    a multi-hour task and losing it to a closed tab would be unrecoverable.
    """
    payload = json.dumps([t.model_dump() for t in tasks], ensure_ascii=False)
    # a literal </script> inside the JSON would close the tag early
    payload = payload.replace("</", "<\\/")
    buttons = "\n".join(
        f'      <button class="g" data-g="{g}" onclick="grade({g})"><b>{g}</b> {desc}</button>'
        for g, desc in RUBRIC
    )
    rubric_line = " &nbsp;|&nbsp; ".join(f"<b>{g}</b> {desc}" for g, desc in RUBRIC)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_LABELER_CSS}</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div id="bar"><div id="fill"></div></div>
  <span id="count"></span>
  <button onclick="download()">Download labels</button>
</header>
<div id="rubric">Grade the excerpt against the question. Keys <b>0-3</b> to grade
(auto-advances), <b>&larr; &rarr;</b> to move. {rubric_line}</div>
<main>
  <p class="q" id="q"></p>
  <div class="meta" id="meta"></div>
  <pre id="text"></pre>
</main>
<footer>
{buttons}
</footer>
<script>
const TASKS = {payload};
{_LABELER_JS}
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def build_pairs(
    keys: Sequence[JudgeValidationKey], labels: Sequence[HumanLabel]
) -> list[LabelPair]:
    """Join the judge key to the human labels. Unlabelled tasks are dropped."""
    human = {label.task_id: label.human_grade for label in labels}
    pairs: list[LabelPair] = []
    for key in keys:
        grade = human.get(key.task_id)
        if grade is None:
            continue
        pairs.append(
            LabelPair(
                human=max(0, min(MAX_GRADE, grade)),
                judge=key.judge_grade,
                weight=key.weight,
                stratum=key.stratum,
                retrieved_by=tuple(key.retrieved_by),
                is_seed=key.is_seed_chunk,
            )
        )
    return pairs


def _ci(pairs: Sequence[LabelPair], fn: Any, seed: int, weighted: bool = True) -> dict[str, Any]:
    interval = bootstrap_statistic_ci(
        pairs,
        lambda sample: fn(sample, weighted),
        strata=[p.stratum for p in pairs],
        seed=seed,
    )
    return interval.as_dict()


def score(
    keys: Sequence[JudgeValidationKey],
    labels: Sequence[HumanLabel],
    seed: int = 20260903,
) -> dict[str, Any]:
    """Every agreement statistic, with stratified-bootstrap intervals."""
    pairs = build_pairs(keys, labels)
    if not pairs:
        raise ValueError("no labelled tasks: label the tasks and export labels first")

    stats: dict[str, Any] = {}
    for name, fn in (
        ("tpr", tpr),
        ("tnr", tnr),
        ("precision", precision),
        ("npv", npv),
        ("cohen_kappa_binary", cohen_kappa_binary),
        ("quadratic_weighted_kappa", quadratic_weighted_kappa),
        ("exact_agreement", exact_agreement),
        ("adjacent_agreement", adjacent_agreement),
        ("mean_signed_error", mean_signed_error),
    ):
        stats[name] = _ci(pairs, fn, seed)

    unweighted = {
        name: round(fn(pairs, False), 4)
        for name, fn in (
            ("tpr", tpr),
            ("tnr", tnr),
            ("precision", precision),
            ("npv", npv),
            ("cohen_kappa_binary", cohen_kappa_binary),
            ("quadratic_weighted_kappa", quadratic_weighted_kappa),
            ("exact_agreement", exact_agreement),
        )
    }

    # per-mode signed error: does judge error favour any retrieval mode?
    all_modes = sorted({m for p in pairs for m in p.retrieved_by})
    per_mode: dict[str, Any] = {}
    for mode in all_modes:
        subset = [p for p in pairs if mode in p.retrieved_by]
        if len(subset) < 10:
            per_mode[mode] = {"n": len(subset), "insufficient": True}
            continue
        per_mode[mode] = {
            **_ci(subset, mean_signed_error, seed),
            "judged_relevant_share": round(
                sum(p.weight for p in subset if p.judge_relevant) / sum(p.weight for p in subset),
                4,
            ),
        }

    seed_pairs = [p for p in pairs if p.is_seed]
    seed_recovery = (
        sum(1 for p in seed_pairs if p.human_relevant) / len(seed_pairs) if seed_pairs else None
    )

    by_split: dict[str, Any] = {}
    key_split = {k.task_id: k.split for k in keys}
    label_split = [key_split.get(label.task_id, "dev") for label in labels]
    for split in ("dev", "test"):
        chosen = [label for label, s in zip(labels, label_split, strict=True) if s == split]
        subset = build_pairs(keys, chosen)
        if len(subset) >= 20:
            by_split[split] = {
                "n": len(subset),
                "cohen_kappa_binary": round(cohen_kappa_binary(subset), 4),
                "quadratic_weighted_kappa": round(quadratic_weighted_kappa(subset), 4),
                "tpr": round(tpr(subset), 4),
                "tnr": round(tnr(subset), 4),
            }

    tp, fp, fn_, tn = binary_counts(pairs, False)
    return {
        "dataset": "judge-validation-v1",
        "n_labelled": len(pairs),
        "n_tasks": len(keys),
        "strata": {
            stratum: sum(1 for p in pairs if p.stratum == stratum)
            for stratum in (STRATUM_POS, STRATUM_NEG)
        },
        "weights": {k.stratum: round(k.weight, 3) for k in keys},
        "weighted": stats,
        "unweighted": unweighted,
        "confusion_unweighted": confusion(pairs, False),
        "binary_counts_unweighted": {"tp": tp, "fp": fp, "fn": fn_, "tn": tn},
        "per_mode_signed_error": per_mode,
        "human_seed_recovery": seed_recovery,
        "n_seed_chunks": len(seed_pairs),
        "by_split": by_split,
    }


def _fmt(entry: dict[str, Any]) -> str:
    return f"{entry['mean']:+.3f} [{entry['ci_lo']:+.3f}, {entry['ci_hi']:+.3f}]"


def _fmt_pos(entry: dict[str, Any]) -> str:
    return f"{entry['mean']:.3f} [{entry['ci_lo']:.3f}, {entry['ci_hi']:.3f}]"


def render(report: dict[str, Any], judge_model: str, date: str) -> str:
    w = report["weighted"]
    u = report["unweighted"]
    lines = [
        "# Judge validation v1 - does the LLM relevance judge agree with a human?",
        "",
        f"Generated {date} by `opsverse_evals.judge_validation` from the committed",
        "golden set, corpus dump and human label file. No Qdrant, no API, no network.",
        "",
        f"Judge under test: **`{judge_model}`** (the judge that labelled",
        "`retrieval-golden-v1`, ADR-0019). Human rater: the project author, one rater,",
        f"**{report['n_labelled']}** blinded (question, candidate) pairs.",
        "",
        "## Why this exists",
        "",
        "Every retrieval conclusion in this project rests on one LLM judge's labels. The",
        "only check on it so far was **seed recovery** - the chunk each question was written",
        "from graded >= 2, 100/100. That detects a badly broken judge and nothing else: a",
        "judge that is confidently wrong about the other ~19 candidates per query passes it",
        "unchanged. Until now the honest description of the golden set was *one rater's",
        "opinion, unvalidated*, and that limitation is stated in every report that uses it.",
        "",
        "## Design",
        "",
        "- **Stratified on the judge's binary call.** Only 15.8% of the 1,914 judgements are",
        "  relevant (grade >= 2), so a simple random sample would carry too few positives to",
        "  estimate TPR usefully. Half the sample is drawn from each stratum.",
        "- **Inverse sampling weights** (stratum population / stratum sample) recover the",
        "  population rates from the balanced sample. Both weighted and unweighted numbers",
        "  are printed below; the weighted ones are the population estimates.",
        "- **Stratified bootstrap** (2,000 resamples within stratum) for every interval,",
        "  because kappa and TPR are table ratios, not means of per-item scores.",
        "- **Blinded.** The labeling file carries no chunk id, no case id and no judge grade;",
        "  tasks are shuffled so strata are not blocked. Same rubric wording and same",
        "  4,000-character excerpt window the judge saw.",
        "",
        "## Agreement",
        "",
        "| statistic | weighted (population) | unweighted (in-sample) |",
        "|---|---|---|",
        f"| TPR - judge finds what the human calls relevant | {_fmt_pos(w['tpr'])} |"
        f" {u['tpr']:.3f} |",
        f"| TNR - judge rejects what the human calls irrelevant | {_fmt_pos(w['tnr'])} |"
        f" {u['tnr']:.3f} |",
        f"| Precision - judge's 'relevant' the human confirms | {_fmt_pos(w['precision'])} |"
        f" {u['precision']:.3f} |",
        f"| NPV - judge's 'not relevant' the human confirms | {_fmt_pos(w['npv'])} |"
        f" {u['npv']:.3f} |",
        f"| Cohen's kappa (binary, relevance cut) | {_fmt_pos(w['cohen_kappa_binary'])} |"
        f" {u['cohen_kappa_binary']:.3f} |",
        f"| Quadratic-weighted kappa (graded 0-3) |"
        f" {_fmt_pos(w['quadratic_weighted_kappa'])} | {u['quadratic_weighted_kappa']:.3f} |",
        f"| Exact grade agreement | {_fmt_pos(w['exact_agreement'])} |"
        f" {u['exact_agreement']:.3f} |",
        f"| Agreement within one grade | {_fmt_pos(w['adjacent_agreement'])} | - |",
        f"| Mean signed error (human - judge) | {_fmt(w['mean_signed_error'])} | - |",
        "",
        "Kappa reference points (Landis & Koch, the conventional reading): 0.21-0.40 fair,",
        "0.41-0.60 moderate, 0.61-0.80 substantial, 0.81+ almost perfect. Raw agreement is",
        "not reported as a headline because a pool that is ~84% non-relevant makes it easy:",
        "a judge that rejected everything would score ~0.84 raw and 0.00 kappa.",
        "",
        "### Confusion matrix (unweighted counts, rows = human, cols = judge)",
        "",
        "| human \\ judge | 0 | 1 | 2 | 3 |",
        "|---|---|---|---|---|",
    ]
    for i, row in enumerate(report["confusion_unweighted"]):
        cells = " | ".join(f"{int(v)}" for v in row)
        lines.append(f"| **{i}** | {cells} |")

    bc = report["binary_counts_unweighted"]
    lines += [
        "",
        f"At the relevance cut (grade >= 2), unweighted: tp={int(bc['tp'])}, fp={int(bc['fp'])},",
        f"fn={int(bc['fn'])}, tn={int(bc['tn'])}.",
        "",
        "## Does judge error favour any retrieval mode?",
        "",
        "This is the question that decides whether the published *comparisons* survive.",
        "Absolute judge accuracy could be mediocre without invalidating a mode-vs-mode",
        "delta, provided the judge's errors do not systematically favour one mode. Each row",
        "is the weighted mean of (human - judge) over the sampled candidates that mode",
        "retrieved; positive means the judge under-graded what that mode found.",
        "",
        "| retrieval mode | n | mean signed error [95% CI] | judged relevant |",
        "|---|---|---|---|",
    ]
    for mode, entry in report["per_mode_signed_error"].items():
        if entry.get("insufficient"):
            lines.append(f"| {mode} | {entry['n']} | too few sampled items | - |")
        else:
            lines.append(
                f"| {mode} | {entry['n']} | {_fmt(entry)} | {entry['judged_relevant_share']:.2f} |"
            )

    seed_rate = report["human_seed_recovery"]
    lines += [
        "",
        "Intervals that overlap each other give no evidence of mode-dependent bias. That is",
        "the condition the golden-set comparisons need; it is weaker than the judge being",
        "accurate, and it is the right one, because a bias shared equally by all four modes",
        "cancels in a paired comparison between them.",
        "",
        "## Human seed recovery",
        "",
    ]
    if seed_rate is None:
        lines.append("No originating (seed) chunks fell in the sample.")
    else:
        n_seed = report["n_seed_chunks"]
        lines += [
            "The judge recovered **100%** of originating chunks at grade >= 2 (ADR-0019).",
            f"On the {n_seed} seed chunks that fell in this sample, the human rater graded",
            f"**{seed_rate:.0%}** of them >= 2. A gap here would mean the seed-recovery check",
            "was easier than the judging task it was standing in for.",
        ]

    if report["by_split"]:
        lines += [
            "",
            "## dev / test split",
            "",
            "The sample is split in half within each stratum. No judge prompt was tuned",
            "against these labels, so both halves are held out today; the split exists so",
            "that a future revision of the judge prompt has an untouched test set rather",
            "than being evaluated on data it was fitted to.",
            "",
            "| split | n | binary kappa | quadratic kappa | TPR | TNR |",
            "|---|---|---|---|---|---|",
        ]
        for split, s in report["by_split"].items():
            lines.append(
                f"| {split} | {s['n']} | {s['cohen_kappa_binary']:.3f} |"
                f" {s['quadratic_weighted_kappa']:.3f} | {s['tpr']:.3f} | {s['tnr']:.3f} |"
            )

    lines += [
        "",
        "## Limits",
        "",
        "- **One human rater.** This measures judge-vs-human agreement, not inter-annotator",
        "  agreement, so it cannot separate 'the judge is wrong' from 'this rater is",
        "  unusual'. A second independent rater is the next step, and until there is one the",
        "  human column is a reference, not ground truth.",
        "- **The rater is the system's author**, which is a real bias risk in the",
        "  optimistic direction. Blinding removes the ability to look up the judge's answer;",
        "  it does not remove knowing how the retriever works.",
        f"- **n = {report['n_labelled']}** pairs across {report['n_tasks']} sampled tasks. The",
        "  intervals above are what that buys; they are printed on every number for that",
        "  reason.",
        "- Agreement is measured on this corpus and this rubric only.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_sample(args: argparse.Namespace) -> None:
    golden = GradedRetrievalDataset.load_jsonl(args.golden)
    texts = load_chunk_text(args.corpus)
    modes = retrieval_map(args.raw)
    tasks, keys = draw_sample(golden, texts, modes, args.n, args.seed)

    write_jsonl(args.tasks, tasks)
    write_jsonl(args.key, keys)
    labeler = args.labeler
    labeler.parent.mkdir(parents=True, exist_ok=True)
    labeler.write_text(render_labeler(tasks, "OpsVerse judge validation v1"), encoding="utf-8")

    pos = sum(1 for k in keys if k.stratum == STRATUM_POS)
    weights = {k.stratum: round(k.weight, 2) for k in keys}
    print(f"sampled {len(tasks)} tasks: {pos} judge-relevant, {len(keys) - pos} judge-not")
    print(f"  weights: {weights}")
    print(f"  tasks (blinded): {args.tasks}")
    print(f"  key (judge grades): {args.key}")
    print(f"\nOpen this file in a browser and label every task:\n  {labeler.resolve()}")
    print(f"Then click 'Download labels' and save it as:\n  {args.labels}")


def cmd_score(args: argparse.Namespace) -> None:
    keys = [
        JudgeValidationKey.model_validate_json(line)
        for line in args.key.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    labels = [
        HumanLabel.model_validate_json(line)
        for line in args.labels.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = score(keys, labels, seed=args.seed)

    golden = GradedRetrievalDataset.load_jsonl(args.golden)
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(report, golden.judge_model, date), encoding="utf-8")
    summary = args.out.with_name(args.out.stem + "-summary.json")
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    w = report["weighted"]
    print(f"labelled {report['n_labelled']}/{report['n_tasks']} tasks")
    print(f"  TPR              {_fmt_pos(w['tpr'])}")
    print(f"  TNR              {_fmt_pos(w['tnr'])}")
    print(f"  kappa (binary)   {_fmt_pos(w['cohen_kappa_binary'])}")
    print(f"  kappa (quadratic){_fmt_pos(w['quadratic_weighted_kappa'])}")
    print(f"  signed error     {_fmt(w['mean_signed_error'])}")
    print(f"\nwrote {args.out} and {summary}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sample", help="draw the blinded sample and build the labeling page")
    s.add_argument("--golden", type=Path, default=Path("evalsets/retrieval-golden-v1.jsonl"))
    s.add_argument("--corpus", type=Path, default=Path("data/corpus/chunks.jsonl"))
    s.add_argument("--raw", type=Path, default=Path("docs/reports/retrieval-ablation-v2-raw.json"))
    s.add_argument("--tasks", type=Path, default=Path("evalsets/judge-validation-v1-tasks.jsonl"))
    s.add_argument("--key", type=Path, default=Path("evalsets/judge-validation-v1-key.jsonl"))
    s.add_argument("--labels", type=Path, default=Path("evalsets/judge-validation-v1-labels.jsonl"))
    s.add_argument(
        "--labeler", type=Path, default=Path("evalsets/judge-validation-v1-labeler.html")
    )
    s.add_argument("--n", type=int, default=192, help="total tasks (split evenly across strata)")
    s.add_argument("--seed", type=int, default=20260903)
    s.set_defaults(func=cmd_sample)

    c = sub.add_parser("score", help="score human labels against the judge")
    c.add_argument("--golden", type=Path, default=Path("evalsets/retrieval-golden-v1.jsonl"))
    c.add_argument("--key", type=Path, default=Path("evalsets/judge-validation-v1-key.jsonl"))
    c.add_argument("--labels", type=Path, default=Path("evalsets/judge-validation-v1-labels.jsonl"))
    c.add_argument("--out", type=Path, default=Path("docs/reports/judge-validation-v1.md"))
    c.add_argument("--seed", type=int, default=20260903)
    c.set_defaults(func=cmd_score)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
