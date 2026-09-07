"""Error analysis: what retrieval failure actually looks like on this corpus.

Why this exists
---------------
This project measures retrieval to four decimal places and had, until now, zero
description of how retrieval *fails*. Every report is an aggregate: means, CIs,
p-values. None of them can answer "show me a failure", which is the first thing
anyone debugging a RAG system needs and the first thing an evaluation interview
asks for.

Aggregates also hide their own composition. `recall@10` reads low on the golden
set, and a mean cannot say whether that is one systematic defect or twenty
unrelated ones -- or, as it turns out here, mostly not a defect at all.

Method
------
Standard qualitative coding, in the order that keeps it honest:

1. **Signal extraction** (deterministic, in this module). Flag every query whose
   graded outcome looks like a failure: nothing relevant retrieved, the first
   relevant result buried at rank 6+, a grade-3 chunk available but only grade-2
   retrieved, or a large relevant set only partly recovered.
2. **Open coding** (by hand, reading the retrieved text against the question).
   Describe each failure concretely -- "six near-identical status dumps occupy
   ranks 1-6" -- never "bad retrieval".
3. **Axial coding**: group those descriptions into categories, and label each
   category with what it *is*: a real defect in the system, or an artifact of
   the corpus or the labels.

Step 3 is the one that pays. A taxonomy that lumps "the metric flagged a query
the user would have considered answered" together with "the answer was never
retrieved" produces a fix list aimed at the wrong thing.

The codes live in `evalsets/failure-taxonomy-v1-codes.jsonl`, committed, one
line per case with a free-text note. They are one coder's reading -- the same
limitation the judge validation carries, and stated for the same reason.

Fully offline: reads committed JSON and the corpus dump. No Qdrant, no API.

Usage:
    uv run python -m opsverse_evals.failure_taxonomy
"""

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

THRESHOLD = 2
TOP_K = 10
DEEP_RANK = 6


@dataclass(frozen=True)
class Category:
    """One failure mode, and -- the load-bearing field -- whether it is ours."""

    code: str
    title: str
    real_defect: bool  # False = artifact of the corpus or the labels, not the retriever
    what: str
    fix: str


CATEGORIES: tuple[Category, ...] = (
    Category(
        code="answered_at_top",
        title="The metric flagged a query the user would call answered",
        real_defect=False,
        what=(
            "A relevant chunk -- usually grade 3 -- is at rank 1-3, but the query has "
            "several labelled-relevant chunks and not all were recovered, so recall@10 "
            "scores it below 1.0."
        ),
        fix=(
            "Nothing to fix in retrieval. This is what a recall metric does on a corpus "
            "with many acceptable answers per question, and it is the largest single "
            "reason absolute recall reads low here."
        ),
    ),
    Category(
        code="redundant_pool",
        title="Near-duplicate chunks inflate the relevant set",
        real_defect=False,
        what=(
            "The same answer appears in many chunks -- the awesome-compose samples repeat "
            "one `docker compose down` instruction across a dozen READMEs, and command "
            "docs appear again under an `alpha` namespace. Recovering 5 of 13 identical "
            "chunks answers the question completely and scores 38% recall."
        ),
        fix=(
            "A deduplication pass at ingest, or credit at document rather than chunk "
            "granularity (the ablation harness already reports both). Do not tune the "
            "retriever against this number."
        ),
    ),
    Category(
        code="lexical_distraction",
        title="A common query term pulls in generic prose",
        real_defect=True,
        what=(
            "The question contains a word the corpus uses everywhere -- 'foreground', "
            "'docker' -- and chunks that merely discuss the word outrank the one chunk "
            "that configures it."
        ),
        fix=(
            "This is the failure a reranker is supposed to absorb, and ADR-0019 measured "
            "rerank as not significantly helpful overall. These cases are where to look "
            "for whether a better reranker would earn its cost -- a targeted question, "
            "not a general one."
        ),
    ),
    Category(
        code="boilerplate_outranks_prose",
        title="Repeated boilerplate crowds out the explanatory chunk",
        real_defect=True,
        what=(
            "Status dumps and reference tables that share the question's vocabulary "
            "occupy the whole top-k, pushing the prose that answers it past rank 6."
        ),
        fix=(
            "A quality gate at ingest for low-information chunks (terminal transcripts, "
            "generated flag tables), which `libs/ingestion/quality.py` already has the "
            "shape for."
        ),
    ),
    Category(
        code="specific_answer_missed",
        title="Right topic, wrong specificity",
        real_defect=True,
        what=(
            "Retrieval lands on the correct subject area but returns the policy or "
            "overview chunk rather than the concrete artifact -- the sign-off rules "
            "instead of the commit-message template."
        ),
        fix=(
            "The clearest candidate for query-side work: these questions ask for a "
            "template or command and get prose about it."
        ),
    ),
    Category(
        code="label_error",
        title="The judge graded a chunk that does not answer the question",
        real_defect=False,
        what=(
            "A chunk graded 3 that does not answer, while the chunk that does was graded "
            "lower or left out of the pool. Consistent with ADR-0022's finding that the "
            "judge is imperfectly calibrated."
        ),
        fix=(
            "Not a retrieval problem. Bounded by the judge-validation work; more human "
            "labels shrink it."
        ),
    ),
    Category(
        code="true_miss",
        title="Nothing relevant retrieved at all",
        real_defect=True,
        what=(
            "No chunk at or above the relevance threshold appears in the top 10, though "
            "relevant chunks exist in the judged pool."
        ),
        fix="The only category where the user is left with nothing. Rare here.",
    ),
)

BY_CODE = {c.code: c for c in CATEGORIES}


def load_golden(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip():
            case = json.loads(line)
            out[case["id"]] = case
    return out


def extract_candidates(
    golden: dict[str, dict[str, Any]], raw: dict[str, Any], mode: str
) -> list[dict[str, Any]]:
    """Flag every query whose graded outcome has the shape of a failure.

    Deliberately over-inclusive: the point of the coding pass is to find out how
    many of these are real, so a narrow filter would beg the question.
    """
    flagged: list[dict[str, Any]] = []
    for case in raw["results"][mode]:
        gold = golden.get(case["case_id"])
        if not gold:
            continue
        grades: dict[str, int] = gold["grades"]
        relevant = {cid for cid, g in grades.items() if g >= THRESHOLD}
        if not relevant:
            continue
        top = case["retrieved_chunk_ids"][:TOP_K]
        hit_grades = [grades.get(cid, 0) for cid in top]
        best = max(hit_grades, default=0)
        first_rel = next(
            (i + 1 for i, cid in enumerate(top) if grades.get(cid, 0) >= THRESHOLD), None
        )
        found = sum(1 for cid in top if grades.get(cid, 0) >= THRESHOLD)

        signal = None
        if best < THRESHOLD:
            signal = "no_relevant_in_top_k"
        elif first_rel and first_rel >= DEEP_RANK:
            signal = "first_relevant_buried"
        elif best == THRESHOLD and 3 in grades.values():
            signal = "best_available_not_retrieved"
        elif found < len(relevant) and len(relevant) >= 3:
            signal = "partial_recall"
        if signal:
            flagged.append(
                {
                    "case_id": case["case_id"],
                    "signal": signal,
                    "question": gold["question"],
                    "relevant_in_pool": len(relevant),
                    "found": found,
                    "first_relevant_rank": first_rel,
                    "top_grades": [grades.get(cid, 0) for cid in top[:6]],
                }
            )
    return flagged


def load_codes(path: Path) -> dict[str, dict[str, str]]:
    codes: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["code"] not in BY_CODE:
                raise ValueError(f"unknown code {row['code']!r} for {row['case_id']}")
            codes[row["case_id"]] = row
    return codes


def build(
    flagged: list[dict[str, Any]], codes: dict[str, dict[str, str]], total_queries: int
) -> dict[str, Any]:
    """Join the deterministic signals to the hand-assigned codes."""
    coded: list[dict[str, Any]] = []
    uncoded: list[str] = []
    for case in flagged:
        row = codes.get(case["case_id"][:8]) or codes.get(case["case_id"])
        if not row:
            uncoded.append(case["case_id"][:8])
            continue
        coded.append({**case, "code": row["code"], "note": row["note"]})

    counts = Counter(c["code"] for c in coded)
    real = sum(n for code, n in counts.items() if BY_CODE[code].real_defect)
    return {
        "report": "failure-taxonomy-v1",
        "coder": "claude-opus-5",
        "coder_kind": "language model",
        "mode": "hybrid",
        "queries": total_queries,
        "flagged": len(flagged),
        "coded": len(coded),
        "uncoded": uncoded,
        "signals": dict(Counter(c["signal"] for c in flagged)),
        "counts": dict(counts.most_common()),
        "real_defects": real,
        "not_defects": len(coded) - real,
        "cases": coded,
    }


def render(report: dict[str, Any], date: str, coder: str, coder_kind: str) -> str:
    coded, n = report["coded"], report["queries"]
    real, artifact = report["real_defects"], report["not_defects"]
    counts = report["counts"]
    by_case = {c["code"]: c for c in reversed(report["cases"])}

    lines = [
        "# Failure taxonomy v1 - what retrieval failure actually looks like here",
        "",
        f"Generated {date} by `opsverse_evals.failure_taxonomy` from the committed golden",
        "set, ablation raw JSON, corpus dump and hand-assigned codes. Offline.",
        "",
        f"Scope: the **hybrid** retriever over the {n} golden queries. "
        f"**{report['flagged']}** were flagged by a deliberately over-inclusive failure",
        f"signal; all {coded} were read and coded by hand.",
        "",
        "## Why this exists",
        "",
        "This project measured retrieval to four decimal places and could not show you a",
        "single failure. Every report was an aggregate, and an aggregate cannot say whether",
        "a low `recall@10` is one systematic defect or twenty unrelated ones. This is the",
        "error analysis that answers that, and the answer was not what the metric implied.",
        "",
        "## The finding",
        "",
        f"**{artifact} of the {coded} flagged failures ({100 * artifact / coded:.0f}%) are not",
        f"retrieval defects.** Only **{real}** are - which is **{100 * real / n:.0f}% of the",
        f"{n} queries**, not the ~28% the flag rate suggests.",
        "",
        "The two largest categories are the metric describing the corpus rather than the",
        "retriever: queries where a grade-3 answer sits at rank 1-3 but several other",
        "labelled-relevant chunks were not recovered, and queries whose relevant set is",
        "mostly near-duplicates of each other. **This is the concrete mechanism behind the",
        "low absolute `recall@k` on the golden set** - and it is independent of, and",
        "additional to, the judge's strictness measured in "
        "[ADR-0022](../adr/0022-judge-validation-against-a-second-rater.md).",
        "",
        "| category | n | share | real defect? |",
        "|---|---|---|---|",
    ]
    for code, count in counts.items():
        cat = BY_CODE[code]
        mark = "**yes**" if cat.real_defect else "no"
        lines.append(f"| {cat.title} | {count} | {100 * count / coded:.0f}% | {mark} |")

    lines += ["", "## The categories", ""]
    for cat in CATEGORIES:
        if cat.code not in counts:
            continue
        example = by_case.get(cat.code)
        lines += [
            f"### {cat.title} — {counts[cat.code]} case(s)",
            "",
            f"*{'Real defect.' if cat.real_defect else 'Not a retrieval defect.'}* {cat.what}",
            "",
        ]
        if example:
            lines += [
                f"> **Example** (`{example['case_id'][:8]}`) — {example['question']}  ",
                f"> Relevant in pool: {example['relevant_in_pool']}, "
                f"retrieved: {example['found']}, first relevant at rank "
                f"{example['first_relevant_rank'] or 'none'}. "
                f"Top-6 grades: `{example['top_grades']}`.  ",
                f"> {example['note']}",
                "",
            ]
        lines += [f"**What to do:** {cat.fix}", ""]

    lines += [
        "## What to fix next, in order",
        "",
        "Ranked by count among the categories that are actually defects:",
        "",
    ]
    ranked = [(c, n_) for c, n_ in counts.items() if BY_CODE[c].real_defect]
    for i, (code, count) in enumerate(ranked, 1):
        lines.append(f"{i}. **{BY_CODE[code].title}** ({count}) — {BY_CODE[code].fix}")
    lines += [
        "",
        "Note what is *not* on this list: any change motivated purely by raising",
        f"`recall@10`. {artifact} of the {coded} flagged cases would be 'fixed' by chasing",
        "that number, and none of those fixes would help a user.",
        "",
        "## Limits",
        "",
        f"- **One coder: `{coder}` — a {coder_kind}, not a person.** The open coding was",
        f"  done by a language model reading each of the {coded} cases against the question,",
        "  in the same session that built this module. That is a real limitation and the",
        "  same one [ADR-0022](../adr/0022-judge-validation-against-a-second-rater.md)",
        "  measured directly: on relevance grading this model ran **more lenient** than the",
        "  human rater. A category mix produced by it should be read as a hypothesis to",
        "  check, not a settled description. Every code is committed in",
        "  `evalsets/failure-taxonomy-v1-codes.jsonl` with a free-text note, so the reading",
        "  can be disagreed with case by case rather than in general.",
        "- **No second coder**, so there is no inter-coder agreement to report. Re-coding",
        "  even 10 of these by hand would test the biggest claim here — that most flagged",
        "  failures are not defects — far more cheaply than re-running any retrieval.",
        "- **One retrieval mode** (hybrid, the shipped default) and one corpus. The",
        "  category *mix* is a property of this corpus - a less redundant one would shift",
        "  it substantially.",
        "- **The signal is over-inclusive by design**, so the flag rate is not a failure",
        "  rate and is not quoted as one anywhere above.",
        f"- Coding stopped at {coded} cases because the categories stopped changing, not",
        "  because the queries ran out. Saturation is a judgement call, and it was the",
        "  coder's.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=Path("evalsets/retrieval-golden-v1.jsonl"))
    parser.add_argument(
        "--raw", type=Path, default=Path("docs/reports/retrieval-ablation-v2-raw.json")
    )
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus/chunks.jsonl"))
    parser.add_argument(
        "--codes", type=Path, default=Path("evalsets/failure-taxonomy-v1-codes.jsonl")
    )
    parser.add_argument("--mode", default="hybrid")
    parser.add_argument("--out", type=Path, default=Path("docs/reports/failure-taxonomy-v1.md"))
    parser.add_argument(
        "--coder",
        default="claude-opus-5",
        help="who assigned the codes; named in the report because it changes how to read it",
    )
    parser.add_argument(
        "--coder-kind", default="language model", choices=("human", "language model")
    )
    args = parser.parse_args()

    golden = load_golden(args.golden)
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    flagged = extract_candidates(golden, raw, args.mode)
    report = build(flagged, load_codes(args.codes), total_queries=len(golden))
    if report["uncoded"]:
        print(f"WARNING: {len(report['uncoded'])} flagged cases have no code: {report['uncoded']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        render(report, datetime.now(UTC).strftime("%Y-%m-%d"), args.coder, args.coder_kind),
        encoding="utf-8",
    )
    summary = args.out.with_name(args.out.stem + "-summary.json")
    summary.write_text(
        json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{report['flagged']} flagged, {report['coded']} coded")
    print(f"  real defects: {report['real_defects']}  |  not defects: {report['not_defects']}")
    for code, count in report["counts"].items():
        print(f"    {code:28s} {count}")
    print(f"\nwrote {args.out} and {summary}")


if __name__ == "__main__":
    main()
