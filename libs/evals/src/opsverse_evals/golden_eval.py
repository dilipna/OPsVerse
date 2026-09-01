"""Score every retrieval mode against the golden (pooled, graded) set.

This is the payoff for ADR-0018. That ADR showed `precision@k`, `recall@k` and
contextual precision were algebraic restatements of `hit@k` / `mrr@k` on the
single-gold-label sets, and costed the fix: relevance judged over a pooled
candidate set instead of inherited from the generating chunk. `golden_set.py`
built that; this module measures with it and reports three things the older
ablations could not:

1. **The metrics are now independent.** The same degeneracy check from
   `metrics_audit.py` is re-run here and is expected to *fail* -- that failure
   is the evidence the labels improved.
2. **Graded nDCG**, which distinguishes "found the chunk that fully answers"
   from "found something on-topic". Binary relevance cannot.
3. **Uncertainty and significance.** Every mean carries a bootstrap CI, and
   every mode-vs-mode gap carries a paired permutation test. A ranking without
   those is an anecdote with decimal places.

Reads the committed ablation raw JSON for ranked lists, so it re-scores the
*same* retrieval runs against better labels -- no re-retrieval, no Qdrant.

Run:  uv run python -m opsverse_evals.golden_eval
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opsverse_evals.metrics import (
    contextual_precision_at_k,
    hit_at_k,
    mrr_at_k,
    ndcg_at_k_graded,
    precision_at_k,
    recall_at_k,
)
from opsverse_evals.schemas import GradedRetrievalDataset
from opsverse_evals.stats import bootstrap_ci, paired_permutation_test

K = 10
BASELINE = "hybrid"  # the shipped default; everything is compared against it


def per_query_scores(
    golden: GradedRetrievalDataset, raw_path: Path, k: int = K
) -> dict[str, dict[str, list[float]]]:
    """mode -> metric -> per-query score vector, aligned on a common query order."""
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    by_case = {c.id: c for c in golden.cases}
    threshold = golden.relevance_threshold

    # a single, fixed query order so every vector is pairable across modes
    order = [c.id for c in golden.cases]
    out: dict[str, dict[str, list[float]]] = {}

    for mode, cases in raw["results"].items():
        ranked_by_case = {c["case_id"]: c["retrieved_chunk_ids"] for c in cases}
        metrics: dict[str, list[float]] = {}
        for case_id in order:
            gold = by_case.get(case_id)
            ranked = ranked_by_case.get(case_id)
            if gold is None or ranked is None:
                continue
            rel = gold.relevant_ids(threshold)
            grades = gold.grades
            metrics.setdefault("hit@10", []).append(hit_at_k(ranked, rel, k))
            metrics.setdefault("mrr@10", []).append(mrr_at_k(ranked, rel, k))
            metrics.setdefault("precision@10", []).append(precision_at_k(ranked, rel, k))
            metrics.setdefault("recall@10", []).append(recall_at_k(ranked, rel, k))
            metrics.setdefault("ctx_precision@10", []).append(
                contextual_precision_at_k(ranked, rel, k)
            )
            metrics.setdefault("ndcg_graded@10", []).append(ndcg_at_k_graded(ranked, grades, k))
        out[mode] = metrics
    return out


def degeneracy_still_holds(scores: dict[str, dict[str, list[float]]], k: int = K) -> dict[str, Any]:
    """Re-run the ADR-0018 identity check. On a good golden set it must FAIL."""
    worst_recall = 0.0
    worst_ctx = 0.0
    for metrics in scores.values():
        for r, h in zip(metrics["recall@10"], metrics["hit@10"], strict=True):
            worst_recall = max(worst_recall, abs(r - h))
        for c, m in zip(metrics["ctx_precision@10"], metrics["mrr@10"], strict=True):
            worst_ctx = max(worst_ctx, abs(c - m))
    return {
        "recall_vs_hit_max_gap": worst_recall,
        "ctx_precision_vs_mrr_max_gap": worst_ctx,
        "still_degenerate": worst_recall < 1e-12 and worst_ctx < 1e-12,
    }


def analyse(golden_path: Path, raw_path: Path) -> dict[str, Any]:
    golden = GradedRetrievalDataset.load_jsonl(golden_path)
    scores = per_query_scores(golden, raw_path)

    label_counts = [len(c.relevant_ids(golden.relevance_threshold)) for c in golden.cases]
    grade_hist: dict[int, int] = {}
    for c in golden.cases:
        for g in c.grades.values():
            grade_hist[g] = grade_hist.get(g, 0) + 1
    seeds = [c.seed_grade for c in golden.cases if c.seed_grade is not None]

    summary: dict[str, Any] = {
        "dataset": golden.name,
        "judge_model": golden.judge_model,
        "relevance_threshold": golden.relevance_threshold,
        "queries": len(golden.cases),
        "mean_pool_size": (
            round(sum(c.pool_size for c in golden.cases) / len(golden.cases), 2)
            if golden.cases
            else 0
        ),
        "relevant_per_query": {
            "mean": round(sum(label_counts) / len(label_counts), 2) if label_counts else 0,
            "min": min(label_counts) if label_counts else 0,
            "max": max(label_counts) if label_counts else 0,
            "multi_label_queries": sum(1 for x in label_counts if x > 1),
            "zero_label_queries": sum(1 for x in label_counts if x == 0),
        },
        "grade_histogram": dict(sorted(grade_hist.items())),
        "seed_recovery_rate": (
            round(sum(1 for g in seeds if g >= 2) / len(seeds), 4) if seeds else None
        ),
        "degeneracy": degeneracy_still_holds(scores),
        "modes": {},
        "comparisons": {},
    }

    for mode, metrics in scores.items():
        summary["modes"][mode] = {
            name: bootstrap_ci(vals).as_dict() for name, vals in sorted(metrics.items())
        }

    base = scores.get(BASELINE, {})
    for mode, metrics in scores.items():
        if mode == BASELINE:
            continue
        cmp: dict[str, Any] = {}
        for name, vals in sorted(metrics.items()):
            if name not in base:
                continue
            cmp[name] = paired_permutation_test(vals, base[name]).as_dict()
        summary["comparisons"][f"{mode}_vs_{BASELINE}"] = cmp

    return summary


def render(s: dict[str, Any], date: str) -> str:
    rel = s["relevant_per_query"]
    deg = s["degeneracy"]
    lines = [
        "# Golden retrieval set v1 - pooled, graded, with uncertainty",
        "",
        f"Generated {date} by `opsverse_evals.golden_eval`. Labels from "
        f"`evalsets/retrieval-golden-v1.jsonl` (judge: `{s['judge_model']}`); ranked lists "
        "re-scored from the committed ablation raw JSON, so this compares *labels*, not runs.",
        "",
        "## What changed versus the shipped eval sets",
        "",
        "`retrieval-v1/v2/v3` give each question one gold label - the chunk it was generated",
        "from. [ADR-0018](../adr/0018-retrieval-metrics-independence-audit.md) showed that",
        "makes `recall@k` = `hit@k`, `precision@k` = `hit@k/k` and contextual precision =",
        "`mrr@k`. This set replaces those labels with **pooled, graded** judgements:",
        "",
        "- **Pooling (TREC-style):** candidates pooled from dense + sparse + hybrid +",
        f"  hybrid+rerank, deduplicated - **mean pool {s['mean_pool_size']} candidates/query**",
        "  versus 10 if only one system were judged. No mode is scored solely on what it",
        "  itself retrieved.",
        "- **Graded 0-3** (TREC convention), so nDCG can separate a full answer from an",
        "  on-topic near-miss.",
        "- **Position-randomised**: candidate order shuffled per query with a deterministic",
        "  seed, so the judge cannot inherit any system's ranking.",
        "",
        "## The labels",
        "",
        f"- **{s['queries']} queries**, relevance threshold "
        f"**grade >= {s['relevance_threshold']}**",
        f"- Relevant chunks per query: mean **{rel['mean']}**, range {rel['min']}-{rel['max']}",
        f"- **{rel['multi_label_queries']}/{s['queries']}** queries have more than one relevant",
        f"  chunk (the whole point); {rel['zero_label_queries']} have none",
        f"- Grade histogram (all judgements): `{s['grade_histogram']}`",
    ]
    if s["seed_recovery_rate"] is not None:
        lines.append(
            f"- **Seed recovery {s['seed_recovery_rate']:.0%}** - share of originating chunks the "
            "judge independently graded >=2. A judge-sanity check: the question was written "
            "*from* that chunk, so a low rate would mean the judge, not the retriever, is the "
            "problem."
        )
    lines += [
        "",
        "## Did the degeneracy actually break?",
        "",
        "Re-running the ADR-0018 identity check against these labels - here a **failure is the",
        "desired result**, because it means the metrics now measure different things:",
        "",
        f"- `max |recall@10 - hit@10|` = **{deg['recall_vs_hit_max_gap']:.4f}**",
        f"- `max |ctx_precision@10 - mrr@10|` = **{deg['ctx_precision_vs_mrr_max_gap']:.4f}**",
        "",
        f"**Still degenerate: {deg['still_degenerate']}** "
        + (
            "-- labels did NOT fix it, investigate"
            if deg["still_degenerate"]
            else "-- the metrics are now independent."
        ),
        "",
        "## Results (mean with 95% bootstrap CI, 2000 resamples)",
        "",
        "| mode | hit@10 | recall@10 | precision@10 | mrr@10 | ctx_prec@10 | nDCG_graded@10 |",
        "|---|---|---|---|---|---|---|",
    ]

    def cell(m: dict[str, Any], name: str) -> str:
        d = m.get(name)
        if not d:
            return "-"
        return f"{d['mean']:.3f} <sub>[{d['ci_lo']:.3f},{d['ci_hi']:.3f}]</sub>"

    for mode, m in s["modes"].items():
        lines.append(
            f"| {mode} | {cell(m, 'hit@10')} | {cell(m, 'recall@10')} | "
            f"{cell(m, 'precision@10')} | {cell(m, 'mrr@10')} | "
            f"{cell(m, 'ctx_precision@10')} | {cell(m, 'ndcg_graded@10')} |"
        )

    lines += [
        "",
        f"## Is any gap real? (paired permutation test vs `{BASELINE}`, 10k permutations)",
        "",
        "Paired by query, because per-query difficulty dominates the variance. `p < 0.05`",
        "two-sided is called significant; anything else is reported as **not** distinguishable",
        "at this sample size rather than quietly ranked.",
        "",
        "| comparison | metric | delta | 95% CI | p | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for pair, cmps in s["comparisons"].items():
        for name, c in cmps.items():
            verdict = "**significant**" if c["significant"] else "not significant"
            lines.append(
                f"| {pair} | {name} | {c['delta']:+.4f} | "
                f"[{c['ci_lo']:+.4f}, {c['ci_hi']:+.4f}] | {c['p_value']:.4f} | {verdict} |"
            )

    lines += [
        "",
        "## Honest limits",
        "",
        "- **The judge is a single LLM.** These are LLM-graded relevance labels, not human",
        "  ones. Seed recovery is a sanity check on the judge, not a substitute for human",
        "  agreement; a second-annotator study is the next step, not a claim made here.",
        "- **The pool is bounded by what the four modes retrieved.** A chunk no mode surfaced",
        "  in its top-10 is unjudged and counts as irrelevant. That is the standard pooling",
        "  assumption and it inflates recall for every system equally.",
        f"- **n = {s['queries']} queries.** The CIs are the honest width of that; several gaps",
        "  below are not resolvable at this n, and are labelled so.",
        "- Re-scored from committed ranked lists, so this isolates the effect of *labels*.",
        "  It is not a fresh retrieval run.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=Path("evalsets/retrieval-golden-v1.jsonl"))
    parser.add_argument(
        "--raw", type=Path, default=Path("docs/reports/retrieval-ablation-v2-raw.json")
    )
    parser.add_argument("--out", type=Path, default=Path("docs/reports/retrieval-golden-v1.md"))
    args = parser.parse_args()

    summary = analyse(args.golden, args.raw)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    args.out.write_text(render(summary, stamp), encoding="utf-8")
    summary_path = args.out.with_name("retrieval-golden-v1-summary.json")
    summary_path.write_text(
        json.dumps(
            {
                "report": "retrieval-golden-v1",
                "kind": "retrieval-golden",
                "date": stamp,
                **summary,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    deg = summary["degeneracy"]
    print(f"queries: {summary['queries']}, mean pool {summary['mean_pool_size']}")
    print(f"multi-label queries: {summary['relevant_per_query']['multi_label_queries']}")
    print(f"still degenerate: {deg['still_degenerate']} (want False)")
    print(f"wrote {args.out} and {summary_path}")


if __name__ == "__main__":
    main()
