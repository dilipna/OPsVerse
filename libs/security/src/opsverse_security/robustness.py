"""Robustness of the injection detector under character-level obfuscation.

The v1 red-team set scores 1.0 / 1.0 / 1.0, but it was written alongside the
detector, so that score shows coverage of the set, not robustness. This eval
asks a narrower, falsifiable question: **does detection survive simple
character-level rewrites of the same cases?**

No new attack text is written. Each case in `security-redteam-v1.jsonl`
(attacks and benign DevOps sentences alike) is passed through deterministic
transforms that keep it readable to a person or a model:

- `zero_width`  invisible U+200B inserted inside longer words
- `lookalike`   some Latin vowels swapped for identical-looking Cyrillic letters
- `full_width`  ASCII letters swapped for full-width forms
- `line_split`  every space replaced by a newline
- `case_noise`  alternating upper/lower case

Both detectors are scored: `raw` (regexes on the input as given, as shipped
before this change) and `normalized` (the default scan). Benign rows go
through the same transforms, so a fix that just flags anything odd-looking
shows up as lost specificity.

Out of scope, stated so the number is not over-read: rewording, translation
and encodings change the words themselves, and no character-level fix can
catch them. That is the case for a learned classifier layer (threat model
T-01, planned), not something this report measures.

Usage:
    uv run python -m opsverse_security.robustness            # writes docs/reports
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opsverse_security.injection import scan_injection

_LONG_WORD = re.compile(r"[A-Za-z]{4,}")
_LOOKALIKE = str.maketrans({"a": "\u0430", "e": "\u0435", "o": "\u043e"})


def _zero_width(text: str) -> str:
    return _LONG_WORD.sub(lambda m: m.group(0)[:2] + "\u200b" + m.group(0)[2:], text)


def _lookalike(text: str) -> str:
    return text.translate(_LOOKALIKE)


def _full_width(text: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" and c.isalpha() else c for c in text)


def _line_split(text: str) -> str:
    return text.replace(" ", "\n")


def _case_noise(text: str) -> str:
    return "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))


TRANSFORMS: dict[str, Callable[[str], str]] = {
    "identity": lambda t: t,
    "zero_width": _zero_width,
    "lookalike": _lookalike,
    "full_width": _full_width,
    "line_split": _line_split,
    "case_noise": _case_noise,
}
DETECTORS = {"raw": False, "normalized": True}


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def evaluate(dataset_path: Path) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    results: dict[str, dict[str, Any]] = {}
    for detector, normalize in DETECTORS.items():
        for name, transform in TRANSFORMS.items():
            tp = fn = fp = tn = 0
            missed: list[str] = []
            false_alarms: list[str] = []
            for row in rows:
                flagged = scan_injection(transform(row["text"]), normalize=normalize).is_suspicious
                if row["label"] == "injection":
                    tp, fn = tp + flagged, fn + (not flagged)
                    if not flagged:
                        missed.append(row["id"])
                else:
                    fp, tn = fp + flagged, tn + (not flagged)
                    if flagged:
                        false_alarms.append(row["id"])
            results[f"{detector}/{name}"] = {
                "tpr_recall": _rate(tp, tp + fn),
                "specificity": _rate(tn, tn + fp),
                "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
                "missed_attacks": missed,
                "false_alarms": false_alarms,
            }
    return results


def render_markdown(results: dict[str, dict[str, Any]], dataset: str, date: str) -> str:
    lines = [
        "# Injection detector robustness v1",
        "",
        f"*Generated {date} by `python -m opsverse_security.robustness` from `{dataset}`.*",
        "",
        "Each red-team case (15 attacks, 18 benign DevOps sentences) is rewritten with a",
        "character-level transform that keeps it readable, then scored by the raw regex",
        "detector and by the normalized default. No new attack text was written.",
        "",
        "| Transform | Raw TPR | Normalized TPR | Raw specificity | Normalized specificity |",
        "|---|---|---|---|---|",
    ]
    for name in TRANSFORMS:
        raw, norm = results[f"raw/{name}"], results[f"normalized/{name}"]
        lines.append(
            f"| `{name}` | {raw['tpr_recall']:.2f} | {norm['tpr_recall']:.2f} | "
            f"{raw['specificity']:.2f} | {norm['specificity']:.2f} |"
        )
    misses = sorted(
        {m for k, v in results.items() if k.startswith("normalized/") for m in v["missed_attacks"]}
    )
    lines += [
        "",
        "## Reading it",
        "",
        "- TPR is recall on the 15 attacks; specificity is 1 - false-positive rate on the 18",
        "  benign sentences, which were chosen to share vocabulary with attacks.",
        f"- Attacks still missed by the normalized detector: {', '.join(misses) or 'none'}.",
        "- The transforms and the normalization were written together, so this guards",
        "  against these known tricks regressing; it is not an independent robustness test.",
        "- n = 33 per transform. One case moves a rate by 0.07 (attacks) or 0.06 (benign),",
        "  so treat this as a regression check, not a precise estimate.",
        "",
        "## What this does not measure",
        "",
        "Rewording, translation and encodings change the words, not the characters, and",
        "regexes cannot be expected to catch them. Those belong to the planned learned",
        "classifier layer (threat model T-01). A perfect score here means the character",
        "tricks above no longer work, not that injection is detected in general.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evalsets/security-redteam-v1.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("docs/reports"))
    args = parser.parse_args()

    results = evaluate(args.dataset)
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    summary = {
        "report": "security-robustness-v1",
        "kind": "security-detection",
        "date": date,
        "dataset": "security-redteam-v1",
        "cases": 33,
        "results": {
            k: {"tpr_recall": v["tpr_recall"], "specificity": v["specificity"]}
            for k, v in results.items()
        },
        "detail": results,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "security-robustness-v1-summary.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8"
    )
    (args.out / "security-robustness-v1.md").write_text(
        render_markdown(results, args.dataset.as_posix(), date), encoding="utf-8"
    )
    print(render_markdown(results, args.dataset.as_posix(), date))


if __name__ == "__main__":
    main()
