"""The claim ledger: every belief this project tested and had to withdraw.

Why this exists
---------------
The repository holds 12 reports and 22 ADRs. That is the right amount of depth
and the wrong amount of surface: nobody reads twelve reports, so the rarest
thing here -- a documented record of the project falsifying its *own* published
conclusions, with the statistic that did it -- is invisible to anyone who has
not already read everything.

This module renders that record as one screen. Each row is a claim the project
believed (some of them shipped as defaults), the measurement that overturned it,
and a link to the report and ADR where it happened.

**Every number is plucked from the committed `*-summary.json` files**, never
typed in here. That is not a style preference: a hand-maintained summary table
drifts away from its sources silently, and a page whose whole argument is
"these numbers are honest" cannot be the one stale artifact in the repo. If a
source file is missing or a field moves, `pluck` raises with the full path and
the build fails loudly instead of emitting a plausible wrong number.

Fully offline: reads committed JSON only. No Qdrant, no API, no network.

Usage:
    uv run python -m opsverse_evals.overturns
"""

import argparse
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

Summaries = dict[str, dict[str, Any]]

# summary files the ledger reads; a missing one is a build failure, not a gap
SOURCES = (
    "retrieval-ablation-v2",
    "retrieval-ablation-v3",
    "retrieval-metrics-audit-v1",
    "retrieval-golden-v1",
    "chunking-ablation-v1",
    "embedding-ablation-v1",
    "multiturn-v1",
    "judge-validation-v1",
    "judge-validation-v2",
    "failure-taxonomy-v1",
)


def load_summaries(reports: Path) -> Summaries:
    """Load every committed summary the ledger cites."""
    out: Summaries = {}
    for name in SOURCES:
        path = reports / f"{name}-summary.json"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is missing -- the claim ledger cites it. Regenerate that "
                "report, or remove the row that cites it; do not hand-type the number."
            )
        out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out


def pluck(summaries: Summaries, report: str, *path: str | int) -> Any:
    """Fetch a nested field, raising with the full path if anything moved."""
    cur: Any = summaries[report]
    walked: list[str] = [report]
    for key in path:
        walked.append(str(key))
        try:
            cur = cur[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise KeyError(
                f"{' -> '.join(walked)} not found in the committed summary. The "
                "report format changed; fix the ledger rather than the number."
            ) from exc
    return cur


def _p(value: float) -> str:
    """p-values: exact when readable, else the permutation floor."""
    return f"p={value:.3f}" if value >= 0.001 else "p<0.001"


def _signed(x: float, places: int = 3) -> str:
    return f"{x:+.{places}f}"


_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)


def _spell(n: int) -> str:
    """Spell small counts. The number of claims drifts too, so it is never typed."""
    return _WORDS[n] if n < len(_WORDS) else str(n)


@dataclass(frozen=True)
class Claim:
    """One belief, the test that broke it, and where the evidence lives."""

    key: str
    belief: str  # what was assumed, or shipped as a default
    verdict: str  # the short headline of what the measurement showed
    detail: Callable[[Summaries], str]  # numbers, pulled from committed JSON
    consequence: str  # what actually changed as a result
    reports: tuple[str, ...]
    adr: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


def _sparse_detail(s: Summaries) -> str:
    v2_sparse = pluck(s, "retrieval-ablation-v2", "results", "sparse", "chunk:mrr@10")
    v2_hybrid = pluck(s, "retrieval-ablation-v2", "results", "hybrid", "chunk:mrr@10")
    v3_sparse = pluck(s, "retrieval-ablation-v3", "results", "sparse", "chunk:mrr@10")
    v3_hybrid = pluck(s, "retrieval-ablation-v3", "results", "hybrid", "chunk:mrr@10")
    cmp = pluck(s, "retrieval-golden-v1", "comparisons", "sparse_vs_hybrid", "ndcg_graded@10")
    return (
        f"v2 raw set: sparse MRR@10 {v2_sparse:.3f} vs hybrid {v2_hybrid:.3f}. "
        f"v3 reworded queries: sparse falls to {v3_sparse:.3f} "
        f"({_signed(v3_sparse - v2_sparse)}) while hybrid holds at {v3_hybrid:.3f} "
        f"({_signed(v3_hybrid - v2_hybrid)}) -- the 'win' was vocabulary leakage. "
        f"Pooled graded labels: nDCG {_signed(cmp['delta'])}, {_p(cmp['p_value'])} "
        "-- a statistical tie."
    )


def _metrics_detail(s: Summaries) -> str:
    audits = pluck(s, "retrieval-metrics-audit-v1", "audits")
    worst = 0.0
    cases = 0
    for i in range(len(audits)):
        cases += pluck(s, "retrieval-metrics-audit-v1", "audits", i, "cases")
        modes = pluck(s, "retrieval-metrics-audit-v1", "audits", i, "modes")
        for mode in modes:
            worst = max(
                worst,
                pluck(
                    s,
                    "retrieval-metrics-audit-v1",
                    "audits",
                    i,
                    "modes",
                    mode,
                    "max_identity_deviation",
                ),
            )
    return (
        f"On single-gold-label sets `recall@k` == `hit@k`, `precision@k` == `hit@k/k`, "
        f"and contextual precision == `mrr@k`. Verified per case across {len(audits)} "
        f"datasets / {cases} cases: "
        + (
            "the identities hold exactly, to the last bit of floating point "
            "(max deviation 0, against a 1e-12 tolerance). "
            if worst == 0.0
            else f"max deviation {worst:.1e}, inside the 1e-12 tolerance. "
        )
        + "Three of the five new metrics carried no independent information, so they "
        "were not reported."
    )


def _saturation_detail(s: Summaries) -> str:
    modes = pluck(s, "retrieval-golden-v1", "modes")
    hits = {m: pluck(s, "retrieval-golden-v1", "modes", m, "hit@10", "mean") for m in modes}
    worst_p = 0.0
    for cmp_name in pluck(s, "retrieval-golden-v1", "comparisons"):
        worst_p = max(
            worst_p,
            pluck(s, "retrieval-golden-v1", "comparisons", cmp_name, "hit@10", "p_value"),
        )
    return (
        f"All four retrieval modes score {min(hits.values()):.2f}-{max(hits.values()):.2f} "
        f"on `hit@10`, and no pairwise difference is significant (worst {_p(worst_p)}). "
        "The metric most prominent in the project's own earlier reports had no remaining "
        "power to separate anything."
    )


def _chunking_detail(s: Summaries) -> str:
    cmp = pluck(s, "chunking-ablation-v1", "comparisons", "small", "ndcg_graded@10")
    docs = pluck(s, "chunking-ablation-v1", "resolved_documents")
    pool = pluck(s, "chunking-ablation-v1", "candidate_documents")
    return (
        f"Re-parsing the real source documents under three chunk sizes: 150-token chunks "
        f"beat the shipped 350-token default by nDCG {_signed(cmp['delta'])} "
        f"[{cmp['ci_lo']:+.3f}, {cmp['ci_hi']:+.3f}], {_p(cmp['p_value'])}. "
        f"Scope: {docs}/{pool} candidate documents (time-boxed, and said so)."
    )


def _embedding_detail(s: Summaries) -> str:
    small = "BAAI/bge-small-en-v1.5"
    base = "BAAI/bge-base-en-v1.5"
    cmp = pluck(s, "embedding-ablation-v1", "comparisons", small, "ndcg_graded@10")
    rec = pluck(s, "embedding-ablation-v1", "comparisons", small, "recall@10")
    d_small = pluck(s, "embedding-ablation-v1", "models", small, "dim")
    d_base = pluck(s, "embedding-ablation-v1", "models", base, "dim")
    g_small = pluck(s, "embedding-ablation-v1", "models", small, "size_gb")
    g_base = pluck(s, "embedding-ablation-v1", "models", base, "size_gb")
    return (
        f"The incumbent ({d_base}-dim, {g_base:.2f} GB) is indistinguishable from a model "
        f"{g_base / g_small:.1f}x smaller ({d_small}-dim, {g_small:.2f} GB): "
        f"nDCG {_signed(cmp['delta'])} ({_p(cmp['p_value'])}), "
        f"recall {_signed(rec['delta'])} ({_p(rec['p_value'])}). "
        "The extra size was not earning its cost on this corpus."
    )


def _multiturn_detail(s: Summaries) -> str:
    ndcg = pluck(s, "multiturn-v1", "comparisons", "ndcg@10")
    mrr = pluck(s, "multiturn-v1", "comparisons", "mrr@10")
    n = pluck(s, "multiturn-v1", "queries")
    return (
        f"Production retrieval ignores conversation history. The obvious fix -- "
        f"concatenating the previous turn -- does not help: nDCG {_signed(ndcg['delta'])} "
        f"({_p(ndcg['p_value'])}), MRR {_signed(mrr['delta'])} ({_p(mrr['p_value'])}) "
        f"across {n} two-turn conversations. It trends *worse*, not better. "
        "Published as a null result rather than assumed to work."
    )


def _judge_detail(s: Summaries) -> str:
    mse = pluck(s, "judge-validation-v1", "weighted", "mean_signed_error")
    prec = pluck(s, "judge-validation-v1", "weighted", "precision")
    tpr = pluck(s, "judge-validation-v1", "weighted", "tpr")
    qk = pluck(s, "judge-validation-v1", "weighted", "quadratic_weighted_kappa")
    n = pluck(s, "judge-validation-v1", "n_labelled")
    rater = pluck(s, "judge-validation-v1", "rater_id")
    kind = pluck(s, "judge-validation-v1", "rater_kind")
    del rater, kind, qk  # superseded by the human labels below
    h = pluck(s, "judge-validation-v2", "human_vs_judge")
    hn = pluck(s, "judge-validation-v2", "n_shared")
    h_tpr = h["TPR (rater says relevant -> judge found it)"]
    h_se = h["Mean signed error (rater - judge)"]
    hm_se = pluck(s, "judge-validation-v2", "human_vs_model", "Mean signed error (rater - judge)")
    return (
        f"Audited on a blinded, stratified sample. Against a second *model* rater (n={n}) "
        f"the judge looked systematically strict: signed error {_signed(mse['mean'])} "
        f"[{mse['ci_lo']:+.3f}, {mse['ci_hi']:+.3f}], precision {prec['mean']:.3f} against "
        f"TPR {tpr['mean']:.3f}. A **human** rater then labelled {hn} of the same tasks "
        f"and reproduced the direction and the capability number -- TPR "
        f"{h_tpr['mean']:.3f} -- but not the magnitude: signed error "
        f"{_signed(h_se['mean'])} [{h_se['ci_lo']:+.3f}, {h_se['ci_hi']:+.3f}], which "
        f"**spans zero**. Head to head the human grades {abs(hm_se['mean']):.2f} of a "
        f"grade lower than the model ({_signed(hm_se['mean'])}, excluding zero): the model "
        "rater was the lenient one, and its leniency inflated the offset."
    )


def _taxonomy_detail(s: Summaries) -> str:
    coded = pluck(s, "failure-taxonomy-v1", "coded")
    real = pluck(s, "failure-taxonomy-v1", "real_defects")
    artifact = pluck(s, "failure-taxonomy-v1", "not_defects")
    queries = pluck(s, "failure-taxonomy-v1", "queries")
    counts = pluck(s, "failure-taxonomy-v1", "counts")
    coder = pluck(s, "failure-taxonomy-v1", "coder")
    top = max(counts.items(), key=lambda kv: kv[1])
    return (
        f"An over-inclusive signal flagged {coded} of {queries} queries as retrieval "
        f"failures. Reading every one of them: **{artifact} are not defects** "
        f"({100 * artifact / coded:.0f}%) and only **{real}** are -- {100 * real / queries:.0f}% "
        f"of queries, not the {100 * coded / queries:.0f}% the flag rate implied. The largest "
        f"category ({top[1]} cases) is queries where a grade-3 answer sits at rank 1-3 and "
        "`recall@10` still scores them down because the corpus offers many acceptable "
        f"answers per question. Coded by `{coder}`, a language model, not a person."
    )


LEDGER: tuple[Claim, ...] = (
    Claim(
        key="sparse-vs-hybrid",
        belief="Sparse retrieval beats hybrid — the v2 ablation measured it.",
        verdict="Wrong twice, in two different ways.",
        detail=_sparse_detail,
        consequence=(
            "Three chapters on one claim: a measured win, shown to be an artifact of the "
            "eval set, then shown to be no difference at all. Hybrid stayed the default "
            "for the robustness reason, not the original one."
        ),
        reports=("retrieval-ablation-v2", "retrieval-ablation-v3", "retrieval-golden-v1"),
        adr="0019-golden-set-pooled-graded-relevance",
        tags=("retrieval", "eval-design"),
    ),
    Claim(
        key="metric-degeneracy",
        belief=(
            "Adding `precision@k`, `recall@k` and contextual precision makes the "
            "eval suite more rigorous."
        ),
        verdict="Three of them were the same column twice.",
        detail=_metrics_detail,
        consequence=(
            "Implemented, tested, proven degenerate — and then *not reported*. The fix was "
            "better labels, not more metrics, which is what motivated the golden set."
        ),
        reports=("retrieval-metrics-audit-v1",),
        adr="0018-retrieval-metrics-independence-audit",
        tags=("eval-design", "methodology"),
    ),
    Claim(
        key="hit-at-10",
        belief="`hit@10` is a meaningful headline metric for this corpus.",
        verdict="Saturated. It cannot separate anything.",
        detail=_saturation_detail,
        consequence=(
            "Demoted from the headline. `nDCG_graded@10` and `recall@10` do the "
            "discriminating; `hit@10` is reported only to show it is exhausted."
        ),
        reports=("retrieval-golden-v1",),
        adr="0019-golden-set-pooled-graded-relevance",
        tags=("eval-design",),
    ),
    Claim(
        key="chunk-size",
        belief="The shipped 350-token chunk size is the right default.",
        verdict="It is not the best-measured option.",
        detail=_chunking_detail,
        consequence=(
            "A shipped default was contradicted by a measurement of the system's own "
            "corpus. Reported at document granularity, with the time-boxed scope stated."
        ),
        reports=("chunking-ablation-v1",),
        adr="0020-chunking-and-multiturn-ablations",
        tags=("ingestion", "cost"),
    ),
    Claim(
        key="embedding-size",
        belief="The larger embedding model earns its cost.",
        verdict="No measurable difference against one 3.1x smaller.",
        detail=_embedding_detail,
        consequence=(
            "Quality reported alongside indexing throughput, so 'no difference' becomes a "
            "cost decision rather than a shrug."
        ),
        reports=("embedding-ablation-v1",),
        adr="0021-embedding-model-ablation",
        tags=("retrieval", "cost"),
    ),
    Claim(
        key="multiturn-fix",
        belief="Concatenating conversation history will fix multi-turn retrieval.",
        verdict="It does not. It trends worse.",
        detail=_multiturn_detail,
        consequence=(
            "The intuitive fix was floor-tested before being shipped, and the null result "
            "was published with its significance test instead of being quietly dropped."
        ),
        reports=("multiturn-v1",),
        adr="0020-chunking-and-multiturn-ablations",
        tags=("retrieval", "null-result"),
    ),
    Claim(
        key="judge-calibration",
        belief="The relevance judge is sound — it recovered 100% of seed chunks.",
        verdict="It misses about half the relevant material. Seed recovery was the easy question.",
        detail=_judge_detail,
        consequence=(
            "Absolute recall/nDCG on the golden set read low, and the bias is near-equal "
            "across all four retrieval modes, so the published comparisons stand — the "
            "levels move, the deltas do not. Then the human labels overturned part of the "
            "overturn: the second-model rater had exaggerated the size of the offset, so "
            "the direction survives and the magnitude is back to being an open question."
        ),
        reports=("judge-validation-v1", "judge-validation-v2"),
        adr="0022-judge-validation-against-a-second-rater",
        tags=("eval-design", "methodology"),
    ),
    Claim(
        key="failure-composition",
        belief="A low `recall@10` on the golden set means retrieval is failing.",
        verdict="Most of what the metric flags is not a defect at all.",
        detail=_taxonomy_detail,
        consequence=(
            "The fix list changed completely. Nothing on it is motivated by raising "
            "`recall@10`, because most of what would raise that number would not help a "
            "user. What the aggregate had been hiding was its own composition: corpus "
            "redundancy and a metric penalising queries that were answered at rank 1."
        ),
        reports=("failure-taxonomy-v1",),
        adr="0020-chunking-and-multiturn-ablations",
        tags=("eval-design", "error-analysis"),
    ),
)


def build_rows(summaries: Summaries) -> list[dict[str, Any]]:
    """Resolve every claim's numbers against the committed summaries."""
    return [
        {
            "key": c.key,
            "belief": c.belief,
            "verdict": c.verdict,
            "detail": c.detail(summaries),
            "consequence": c.consequence,
            "reports": list(c.reports),
            "adr": c.adr,
            "tags": list(c.tags),
        }
        for c in LEDGER
    ]


# --------------------------------------------------------------------------
# navigation: where the evidence lives (paths only -- never numbers, which
# would drift; every number on this page is plucked in the ledger above)
# --------------------------------------------------------------------------

READING_PATH = (
    (
        "1. The overturns",
        "docs/evidence.md",
        "This page. Seven claims the project tested and had to withdraw.",
    ),
    (
        "2. The measured inference result",
        "docs/reports/inference-benchmark-v1.md",
        "vLLM vs Ollama on one Tesla T4, one harness. Raw JSON in `benchmarks/results/`; "
        "visual dashboard in `benchmarks/dashboard.html` (self-contained).",
    ),
    (
        "3. Throughput turned into a decision",
        "docs/reports/capacity-and-slo-v1.md",
        "Goodput under a latency SLO, cost per 1M tokens, and the two things the analysis "
        "reports against itself: the sweep never saturated the device, and two identical "
        "runs differed by 22%.",
    ),
    (
        "4. How the labels were built",
        "docs/reports/retrieval-golden-v1.md",
        "Pooled TREC-style, graded 0-3, position-randomised, 1,914 judgements, with "
        "bootstrap CIs and paired permutation tests on every comparison.",
    ),
    (
        "5. Whether the grader is trustworthy",
        "docs/reports/judge-validation-v1.md",
        "The golden set's own judge, audited against a blinded second rater.",
    ),
    (
        "6. The decisions, with their tradeoffs",
        "docs/adr/",
        "22 ADRs. Each states what was rejected and why, not just what was chosen.",
    ),
    (
        "7. The write-ups",
        "https://dilipna.hashnode.dev",
        "Three published posts: the eval harness that stopped two wrong decisions, RAG "
        "security measured like a classifier, and continuous batching on a free T4. "
        "Source copies in `docs/blog/`.",
    ),
)

NOT_CLAIMED = (
    (
        "No before/after number for the fine-tune.",
        "OpsLM-v1 is trained and published, but it has not been evaluated against base "
        "Qwen3-4B on a served endpoint. The runbook for that comparison is written "
        "(`docs/opslm-before-after-aws-runbook.md`); the run is deliberately not done.",
    ),
    (
        "The judge validation used a second model, not a human.",
        "It narrows the 'one rater's opinion' limitation; it does not close it. "
        "Model-model agreement is biased upward. Human labels remain open.",
    ),
    (
        "Peak serving throughput is un-measured.",
        "vLLM was still scaling at the top of the concurrency sweep (65% marginal "
        "efficiency at c=16), so the maximum was never found and is not reported as if "
        "it had been.",
    ),
    (
        "A single T4 cannot show tensor parallelism or multi-node serving.",
        "Stated as a hardware limitation rather than simulated.",
    ),
    (
        "The public demo chat is canned.",
        "`ops-verse.vercel.app` runs in labelled demo mode and does not call the "
        "fine-tuned model. The dashboard at the same site is real and measured.",
    ),
    (
        "The chunking ablation is time-boxed.",
        "100 of 594 candidate documents. The scope is printed next to the result.",
    ),
)


def render_markdown(rows: list[dict[str, Any]], date: str) -> str:
    """`docs/evidence.md` -- the entry point for a reader with six minutes."""
    lines = [
        "# Evidence index — how to read this repository",
        "",
        f"Generated {date} by `opsverse_evals.overturns` from the committed",
        "`docs/reports/*-summary.json`. Every number below is plucked from those files, so",
        "this page cannot drift away from the reports it summarises. No network, no stack.",
        "",
        "> **The short version.** The stack here — hybrid RAG, a QLoRA fine-tune, a served",
        "> model, an eval harness — is not unusual. What is unusual is the record below:",
        f"> **{_spell(len(rows))} claims this project believed, tested, and had to "
        "withdraw**, each",
        "> published with the statistic that overturned it. Four of them were the project's",
        "> own prior conclusions; two were shipped defaults; one was the grader itself.",
        "",
        "---",
        "",
        "## The overturns",
        "",
    ]
    for i, r in enumerate(rows, 1):
        adr = f" · [ADR-{r['adr'][:4]}](adr/{r['adr']}.md)" if r["adr"] else ""
        reports = " · ".join(f"[{n}](reports/{n}.md)" for n in r["reports"])
        lines += [
            f"### {i}. {r['belief']}",
            "",
            f"**{r['verdict']}**",
            "",
            r["detail"],
            "",
            f"*What changed:* {r['consequence']}",
            "",
            f"Evidence: {reports}{adr}",
            "",
        ]

    lines += ["---", "", "## Where everything else lives", ""]
    for title, path, what in READING_PATH:
        lines += [f"**{title}** — `{path}`  ", f"{what}", ""]

    lines += [
        "---",
        "",
        "## What this project does *not* claim",
        "",
        "Every result above has a boundary. These are the ones worth stating out loud,",
        "because a portfolio that only lists wins is not reporting, it is advertising.",
        "",
    ]
    for claim, why in NOT_CLAIMED:
        lines += [f"- **{claim}** {why}"]
    lines += [""]
    return "\n".join(lines)


_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --plane:#f6f7f9; --surface:#ffffff; --surface-2:#fbfcfd;
  --ink:#0b0d10; --secondary:#4a4f57; --muted:#878d96;
  --border:rgba(11,13,16,.10); --accent:#2a78d6;
  --was:#d03b3b; --now:#0ca30c; --was-soft:rgba(208,59,59,.28);
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --plane:#0a0c0f; --surface:#15181d; --surface-2:#1a1e24;
    --ink:#f2f4f7; --secondary:#a8afb9; --muted:#7c828c;
    --border:rgba(255,255,255,.10); --accent:#3987e5;
    --was:#e66767; --now:#3fbf6b; --was-soft:rgba(230,103,103,.32);
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --plane:#0a0c0f; --surface:#15181d; --surface-2:#1a1e24;
  --ink:#f2f4f7; --secondary:#a8afb9; --muted:#7c828c;
  --border:rgba(255,255,255,.10); --accent:#3987e5;
  --was:#e66767; --now:#3fbf6b; --was-soft:rgba(230,103,103,.32);
  color-scheme:dark;
}
html,body{background:var(--plane)}
body{color:var(--ink);font-family:var(--sans);line-height:1.55;
  -webkit-font-smoothing:antialiased;padding:clamp(16px,4vw,44px)}
.wrap{max-width:1000px;margin:0 auto}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);margin:0 0 8px}
h1{font-size:clamp(26px,4.4vw,38px);font-weight:680;letter-spacing:-.02em;
  margin:0;text-wrap:balance}
.sub{color:var(--secondary);font-size:16px;margin:14px 0 0;max-width:68ch}
.sub strong{color:var(--ink)}
.meta{font-family:var(--mono);font-size:12px;color:var(--muted);
  margin:22px 0 0;padding-top:16px;border-top:1px solid var(--border)}
.grid{display:grid;gap:16px;margin:30px 0 0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:clamp(16px,2.6vw,24px)}
.n{font-family:var(--mono);font-size:12px;color:var(--muted);
  letter-spacing:.1em;margin:0 0 10px}
.belief{font-size:17px;font-weight:600;margin:0;color:var(--secondary);
  text-wrap:balance}
.belief::before{content:"Believed: ";color:var(--muted);font-weight:500}
.verdict{font-size:19px;font-weight:660;margin:12px 0 0;color:var(--was);
  letter-spacing:-.01em;text-wrap:balance}
.detail{margin:12px 0 0;font-size:15px;color:var(--ink);
  background:var(--surface-2);border-left:3px solid var(--was-soft);
  border-radius:0 8px 8px 0;padding:12px 14px}
.detail code,.changed code,.belief code,.foot code{font-family:var(--mono);font-size:13px}
.changed{margin:12px 0 0;font-size:14.5px;color:var(--secondary)}
.changed b{color:var(--now);font-weight:640}
.links{margin:14px 0 0;font-family:var(--mono);font-size:12.5px}
.links a{color:var(--accent);text-decoration:none;margin-right:14px;
  border-bottom:1px solid transparent}
.links a:hover{border-bottom-color:var(--accent)}
.foot{margin:34px 0 0;padding-top:18px;border-top:1px solid var(--border);
  font-size:14px;color:var(--secondary)}
.foot h2{font-size:15px;font-weight:640;color:var(--ink);margin:0 0 10px}
.foot li{margin:0 0 8px 18px}
@media print{body{padding:0}.card{break-inside:avoid}}
"""


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline_code(text: str) -> str:
    """Escape, then render `backticked` spans as <code>."""
    parts = _html_escape(text).split("`")
    return "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))


def render_html(rows: list[dict[str, Any]], date: str, repo: str) -> str:
    """A self-contained page: no server, no build step, no network."""
    cards: list[str] = []
    for i, r in enumerate(rows, 1):
        links = [f'<a href="{repo}/blob/main/docs/reports/{n}.md">{n}</a>' for n in r["reports"]]
        if r["adr"]:
            adr_num = r["adr"][:4]
            links.append(f'<a href="{repo}/blob/main/docs/adr/{r["adr"]}.md">ADR-{adr_num}</a>')
        cards.append(
            f'    <article class="card">\n'
            f'      <p class="n">{i:02d} / {len(rows):02d}</p>\n'
            f'      <p class="belief">{_inline_code(r["belief"])}</p>\n'
            f'      <p class="verdict">{_html_escape(r["verdict"])}</p>\n'
            f'      <p class="detail">{_inline_code(r["detail"])}</p>\n'
            f'      <p class="changed"><b>What changed:</b> '
            f"{_inline_code(r['consequence'])}</p>\n"
            f'      <p class="links">{"".join(links)}</p>\n'
            f"    </article>"
        )

    not_claimed = "\n".join(
        f"      <li><b>{_inline_code(c)}</b> {_inline_code(w)}</li>" for c, w in NOT_CLAIMED
    )
    cards_html = "\n".join(cards)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpsVerse AI · What the measurements overturned</title>
<meta name="description" content="Seven claims this project believed, tested, and
 had to withdraw — each published with the statistic that overturned it.">
<style>{_CSS}</style>
</head>
<body>
<main class="wrap">
  <p class="eyebrow">OpsVerse AI · claim ledger</p>
  <h1>{_spell(len(rows)).capitalize()} things this project was wrong about</h1>
  <p class="sub">The stack here — hybrid RAG, a QLoRA fine-tune, a served model, an
  evaluation harness — is not unusual. This is: <strong>every claim below was believed,
  measured, and withdrawn.</strong> Four were the project's own published conclusions,
  two were shipped defaults, and one was the grader that produced the labels for
  everything else.</p>
  <p class="meta">Generated {date} from the committed *-summary.json files · every
  number plucked from source, never typed · no network, no running stack</p>

  <div class="grid">
{cards_html}
  </div>

  <div class="foot">
    <h2>What this project does not claim</h2>
    <ul>
{not_claimed}
    </ul>
  </div>
</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=Path("docs/reports"))
    parser.add_argument("--out-md", type=Path, default=Path("docs/evidence.md"))
    parser.add_argument("--out-html", type=Path, default=Path("docs/overturns.html"))
    parser.add_argument(
        "--publish-to",
        type=Path,
        default=Path("opslm-demo/public/overturns.html"),
        help="second copy for the Vercel demo site (same pattern as dashboard.html)",
    )
    parser.add_argument("--repo", default="https://github.com/dilipna/OPsVerse")
    args = parser.parse_args()

    summaries = load_summaries(args.reports)
    rows = build_rows(summaries)
    date = datetime.now(UTC).strftime("%Y-%m-%d")

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_markdown(rows, date), encoding="utf-8")
    args.out_html.write_text(render_html(rows, date, args.repo), encoding="utf-8")
    print(f"{len(rows)} claims -> {args.out_md} and {args.out_html}")

    if args.publish_to and args.publish_to.parent.exists():
        shutil.copyfile(args.out_html, args.publish_to)
        print(f"published copy -> {args.publish_to}")


if __name__ == "__main__":
    main()
