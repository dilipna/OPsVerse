"""Does retrieval survive a follow-up question? Measure it, then measure the fix.

`stream_chat` sends only the current turn's raw text to the retriever
(`retrieval_query = query` in `libs/rag/chat.py`) — history reaches the
generator's prompt but never reaches retrieval. This scores that gap directly
and tests the cheapest plausible mitigation:

* **turn2_only** — what production actually does today: retrieve on the
  follow-up alone.
* **concat_history** — retrieve on `f"{turn1} {turn2}"`. The simplest fix with
  no architecture change: fold history into the retrieval query string.

Both run through the shipped hybrid retriever against the live corpus
(`opsverse_kb`) — this measures the deployed system, not a throwaway index.

Usage:
    uv run python -m opsverse_evals.multiturn_eval
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opsverse_core.settings import get_settings
from opsverse_evals.metrics import hit_at_k, mrr_at_k, ndcg_at_k
from opsverse_evals.run_ablation import build_retriever
from opsverse_evals.schemas import MultiTurnDataset
from opsverse_evals.stats import bootstrap_ci, paired_permutation_test
from opsverse_rag.schemas import SearchMode

K = 10


async def run(dataset_path: Path, out: Path) -> dict[str, Any]:
    settings = get_settings()
    dataset = MultiTurnDataset.load_jsonl(dataset_path)
    retriever = build_retriever(settings)
    print(f"{len(dataset.cases)} multi-turn cases")

    conditions = {
        "turn2_only": lambda c: c.turn2_question,
        "concat_history": lambda c: f"{c.turn1_question} {c.turn2_question}",
    }
    scores: dict[str, dict[str, list[float]]] = {name: {} for name in conditions}
    t0 = time.perf_counter()

    for name, build_query in conditions.items():
        for case in dataset.cases:
            query = build_query(case)
            hits = await retriever.search(query, k=K, mode=SearchMode.HYBRID, rerank=False)
            ranked = [h.id for h in hits]
            rel = set(case.relevant_chunk_ids)
            m = scores[name]
            m.setdefault("hit@10", []).append(hit_at_k(ranked, rel, K))
            m.setdefault("mrr@10", []).append(mrr_at_k(ranked, rel, K))
            m.setdefault("ndcg@10", []).append(ndcg_at_k(ranked, rel, K))
    elapsed = time.perf_counter() - t0
    print(f"scored both conditions in {elapsed:.1f}s")

    summary = summarise(scores, len(dataset.cases))
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out.write_text(render(summary, stamp), encoding="utf-8")
    summary_path = out.with_name("multiturn-v1-summary.json")
    summary_path.write_text(
        json.dumps(
            {"report": "multiturn-v1", "kind": "multiturn-eval", "date": stamp, **summary},
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out} and {summary_path}")
    for name, m in summary["conditions"].items():
        print(f"  {name:<16} hit@10 {m['hit@10']['mean']:.4f}  mrr@10 {m['mrr@10']['mean']:.4f}")
    return summary


def summarise(scores: dict[str, dict[str, list[float]]], n: int) -> dict[str, Any]:
    conditions = {
        name: {metric: bootstrap_ci(vals).as_dict() for metric, vals in metrics.items()}
        for name, metrics in scores.items()
    }
    comparisons = {}
    if "turn2_only" in scores and "concat_history" in scores:
        for metric in scores["turn2_only"]:
            comparisons[metric] = paired_permutation_test(
                scores["concat_history"][metric], scores["turn2_only"][metric]
            ).as_dict()
    return {"queries": n, "conditions": conditions, "comparisons": comparisons}


def render(s: dict[str, Any], date: str) -> str:
    lines = [
        "# Multi-turn retrieval eval v1 - does a follow-up break retrieval?",
        "",
        f"Generated {date} by `opsverse_evals.multiturn_eval` against the live",
        f"`opsverse_kb` collection, hybrid mode (production default). **{s['queries']} "
        "two-turn cases**, each built so turn 2 is elliptical/coreferential and only",
        "resolves given turn 1.",
        "",
        "## The gap",
        "",
        "`stream_chat` (`libs/rag/chat.py`) sends only the current turn's raw text to the",
        "retriever: `retrieval_query = query`. History reaches the generator's prompt, never",
        "the retriever. Every eval set before this one was single-turn and could not see this.",
        "",
        "## Two conditions",
        "",
        "- **`turn2_only`** - what production does today: retrieve on the follow-up alone.",
        "- **`concat_history`** - the cheapest plausible fix: retrieve on",
        '  `f"{turn1} {turn2}"`. No architecture change, no query rewriting model.',
        "",
        "## Results (mean, 95% bootstrap CI)",
        "",
        "| condition | hit@10 | mrr@10 | ndcg@10 |",
        "|---|---|---|---|",
    ]
    for name, m in s["conditions"].items():
        lines.append(
            f"| `{name}` | {m['hit@10']['mean']:.3f} "
            f"<sub>[{m['hit@10']['ci_lo']:.3f},{m['hit@10']['ci_hi']:.3f}]</sub> | "
            f"{m['mrr@10']['mean']:.3f} "
            f"<sub>[{m['mrr@10']['ci_lo']:.3f},{m['mrr@10']['ci_hi']:.3f}]</sub> | "
            f"{m['ndcg@10']['mean']:.3f} "
            f"<sub>[{m['ndcg@10']['ci_lo']:.3f},{m['ndcg@10']['ci_hi']:.3f}]</sub> |"
        )

    if s["comparisons"]:
        lines += [
            "",
            "## Does concatenating history actually help? (paired permutation test)",
            "",
            "| metric | delta (concat - turn2_only) | 95% CI | p | verdict |",
            "|---|---|---|---|---|",
        ]
        for metric, c in s["comparisons"].items():
            verdict = "**significant**" if c["significant"] else "not significant"
            lines.append(
                f"| {metric} | {c['delta']:+.4f} | [{c['ci_lo']:+.4f}, {c['ci_hi']:+.4f}] | "
                f"{c['p_value']:.4f} | {verdict} |"
            )

        any_sig = any(c["significant"] for c in s["comparisons"].values())
        mean_delta = sum(c["delta"] for c in s["comparisons"].values()) / len(s["comparisons"])
        if any_sig and mean_delta > 0:
            verdict_line = (
                "**Concatenating history measurably helps.** Worth adopting as an interim fix"
                " while a proper query-rewriting step is built."
            )
        elif any_sig and mean_delta < 0:
            verdict_line = (
                "**Concatenating history measurably hurts.** Turn 1 is deliberately about a"
                " *different* topic than turn 2, so naive concatenation adds off-topic terms to"
                " the query — plausible mechanism, not proven here. Turn2-only stays the better"
                " default; the honest fix is query rewriting, not string concatenation."
            )
        else:
            direction = "trends lower" if mean_delta < 0 else "trends higher"
            verdict_line = (
                f"**No significant effect either way at n={s['queries']}.** The naive"
                f" concatenation {direction} on average but the gap does not clear the noise"
                " floor — this sample size cannot distinguish 'no effect' from 'a small effect'."
                " It does **not** support adopting concatenation as a fix."
            )
        lines += ["", verdict_line]

    lines += [
        "",
        "## Honest limits",
        "",
        "- **Constructed, not observed.** These are LLM-written conversations designed to be",
        "  elliptical, not conversations sampled from real usage (none are logged). They test",
        "  whether the failure mode exists and is measurable, not its frequency in the wild.",
        "- **`concat_history` is a naive baseline**, not a proposed design — this eval tests",
        "  whether the cheapest possible fix works, not what the actual fix should be. If it",
        "  doesn't help, the honest next step is query rewriting (an LLM call that resolves the",
        "  reference before retrieval) or a dedicated conversational encoder.",
        "- Single golden chunk per case (matches `retrieval-v1/v2/v3`'s convention); the",
        "  degeneracy documented in ADR-0018 applies here too — hit@k and mrr@k are what this",
        "  set can say, not recall/precision.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evalsets/multiturn-v1.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("docs/reports/multiturn-v1.md"))
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.out))


if __name__ == "__main__":
    main()
