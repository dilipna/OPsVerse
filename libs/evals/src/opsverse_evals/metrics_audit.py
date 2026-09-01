"""Audit which retrieval metrics actually carry independent information.

Motivation: it is easy to add `precision@k` / `recall@k` / "contextual
precision" to a report and mistake breadth for rigour. On an eval set where
every query has exactly one gold label -- which is what
`generate_retrieval_set.py` produces, one question per chunk -- three of those
metrics are algebraic restatements of metrics already reported:

    recall@k               == hit@k
    precision@k            == hit@k / k
    contextual_precision@k == mrr@k

This module proves that empirically against the committed per-case results
rather than asserting it, and writes a report. It reads
`docs/reports/retrieval-ablation-v*-raw.json` (already committed) so it needs
no Qdrant, no API and no network -- the audit is reproducible from the repo
alone.

Run:  uv run python -m opsverse_evals.metrics_audit
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
    precision_at_k,
    recall_at_k,
)
from opsverse_evals.schemas import RetrievalDataset

KS = (1, 3, 5, 10)
TOL = 1e-12


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def audit_dataset(evalset: Path, raw: Path) -> dict[str, Any]:
    """Recompute every metric per case and check the degeneracy identities."""
    dataset = RetrievalDataset.load_jsonl(evalset)
    gold = {c.id: set(c.relevant_chunk_ids) for c in dataset.cases}
    label_sizes = {len(v) for v in gold.values()}

    payload = json.loads(raw.read_text(encoding="utf-8"))
    k_max = payload["k"]

    modes: dict[str, Any] = {}
    violations: list[str] = []

    for mode, cases in payload["results"].items():
        agg: dict[str, list[float]] = {}
        worst = 0.0
        for case in cases:
            ranked = case["retrieved_chunk_ids"]
            rel = gold.get(case["case_id"])
            if not rel:
                continue
            for k in KS:
                h = hit_at_k(ranked, rel, k)
                r = recall_at_k(ranked, rel, k)
                p = precision_at_k(ranked, rel, k)
                m = mrr_at_k(ranked, rel, k)
                cp = contextual_precision_at_k(ranked, rel, k)
                agg.setdefault(f"hit@{k}", []).append(h)
                agg.setdefault(f"recall@{k}", []).append(r)
                agg.setdefault(f"precision@{k}", []).append(p)
                agg.setdefault(f"mrr@{k}", []).append(m)
                agg.setdefault(f"ctx_precision@{k}", []).append(cp)
                # the three identities, checked per case not per mean
                worst = max(worst, abs(r - h), abs(p - h / k), abs(cp - m))
        modes[mode] = {
            "means": {name: round(_mean(vals), 6) for name, vals in agg.items()},
            "max_identity_deviation": worst,
            "cases": len(cases),
        }
        if worst > TOL:
            violations.append(f"{mode}: max deviation {worst:.3e}")

    return {
        "dataset": dataset.name,
        "version": dataset.version,
        "cases": len(dataset.cases),
        "k": k_max,
        "gold_labels_per_query": sorted(label_sizes),
        "single_label": label_sizes == {1},
        "modes": modes,
        "identities_hold": not violations,
        "violations": violations,
    }


def render(audits: list[dict[str, Any]], date: str) -> str:
    lines = [
        "# Retrieval metrics audit v1 - which metrics are independent?",
        "",
        f"Generated {date} by `opsverse_evals.metrics_audit` from the committed",
        "`retrieval-ablation-v*-raw.json`. No Qdrant, no network: reproducible from the repo.",
        "",
        "## Why this exists",
        "",
        "`precision@k`, `recall@k` and contextual precision are standard RAG-evaluation",
        "metrics and they are now implemented in `opsverse_evals.metrics`. But adding them",
        "to these eval sets would **not** have added information, and reporting them as if",
        "it had would be the same mistake this project caught in ablation v2 - a number that",
        "looks like evidence and isn't.",
        "",
        "Every question in `retrieval-v1/v2/v3` is generated from exactly one chunk, so each",
        "query has exactly **one** gold label. Under that condition:",
        "",
        "```",
        "recall@k               == hit@k       (1 relevant item: you find it or you don't)",
        "precision@k            == hit@k / k   (at most one hit in the numerator)",
        "contextual_precision@k == mrr@k       (AP over a single relevant item = 1/rank)",
        "```",
        "",
        "The tables below verify this **per case**, not on the aggregate - the aggregate could",
        "hide compensating errors.",
        "",
    ]

    for a in audits:
        label = "single-label" if a["single_label"] else "multi-label"
        lines += [
            f"## `{a['dataset']}` (v{a['version']}) - {a['cases']} queries, k={a['k']}",
            "",
            f"Gold labels per query: **{a['gold_labels_per_query']}** ({label})",
            "",
            "| mode | hit@10 | recall@10 | precision@10 | mrr@10 |"
            " ctx_precision@10 | max deviation |",
            "|---|---|---|---|---|---|---|",
        ]
        for mode, m in a["modes"].items():
            mm = m["means"]
            lines.append(
                f"| {mode} | {mm['hit@10']:.4f} | {mm['recall@10']:.4f} | "
                f"{mm['precision@10']:.4f} | {mm['mrr@10']:.4f} | "
                f"{mm['ctx_precision@10']:.4f} | {m['max_identity_deviation']:.2e} |"
            )
        verdict = (
            "identities hold exactly across every case"
            if a["identities_hold"]
            else f"VIOLATIONS: {a['violations']}"
        )
        lines += ["", f"**Result: {verdict}.**", ""]

    lines += [
        "## What this means",
        "",
        "- `recall@10` and `hit@10` are the *same column twice*. `precision@10` is `hit@10/10`.",
        "  Quoting all three as separate evidence would inflate an evaluation suite without",
        "  strengthening it.",
        "- The metrics are implemented, tested and correct **for the general multi-label case**",
        "  (`libs/evals/tests/test_metrics_and_schemas.py` pins both the identities and the",
        "  point at which they break). They are ready for an eval set that earns them.",
        "- To make them independent, relevance judgements must be **graded over the retrieved",
        "  candidates**, not inherited from the generating chunk - that is a labelling problem,",
        "  not a metrics problem, and it is the honest next step.",
        "",
        "## What was *not* done, and why",
        "",
        "**Contextual recall was not implemented.** Its definition requires a ground-truth",
        "answer to attribute claims against, and this project has no reference answers: the",
        "faithfulness judge in `rag_suite.py` is deliberately *reference-free*, grading each",
        "claim against the retrieved context. Adding contextual recall means first writing gold",
        "answers - real work with a real cost, not a metric to switch on.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evalsets", type=Path, default=Path("evalsets"))
    parser.add_argument("--reports", type=Path, default=Path("docs/reports"))
    parser.add_argument(
        "--out", type=Path, default=Path("docs/reports/retrieval-metrics-audit-v1.md")
    )
    args = parser.parse_args()

    audits = []
    for version in ("1", "2", "3"):
        evalset = args.evalsets / f"retrieval-v{version}.jsonl"
        raw = args.reports / f"retrieval-ablation-v{version}-raw.json"
        if not evalset.exists() or not raw.exists():
            missing = evalset if not evalset.exists() else raw
            print(f"skip v{version}: missing {missing}")
            continue
        audit = audit_dataset(evalset, raw)
        audits.append(audit)
        status = "OK" if audit["identities_hold"] else "VIOLATION"
        print(
            f"v{version}: {audit['cases']} cases, single_label={audit['single_label']} -> {status}"
        )

    if not audits:
        raise SystemExit("no datasets audited")

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    args.out.write_text(render(audits, stamp), encoding="utf-8")
    summary = args.out.with_name("retrieval-metrics-audit-v1-summary.json")
    summary.write_text(
        json.dumps(
            {
                "report": "retrieval-metrics-audit-v1",
                "kind": "metrics-audit",
                "date": stamp,
                "audits": audits,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.out} and {summary}")


if __name__ == "__main__":
    main()
