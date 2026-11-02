"""Benchmark the injection detectors on data they were not written against.

Detectors compared on the same rows:

- `regex`         the shipped heuristic (`scan_injection`, normalized text)
- `llm`           `LLMInjectionClassifier` through an OpenAI-compatible API
- `regex_or_llm`  flag when either flags: the layered design under consideration

Datasets:

- **External**, pinned in `evalsets/external/security-datasets.json`: a Hugging Face
  dataset at a fixed commit, with the SHA-256 of the exact file. A file that does not
  match is refused. `--record` resolves the current commit and writes the pin (first
  use only; review the diff before committing it).
- **Internal**: `evalsets/security-redteam-v1.jsonl`, the set the regexes were tuned on,
  kept as a reference point, not as evidence of generalization.

Reported per detector and dataset: recall (TPR), false-positive rate and precision,
each with a 95% Wilson interval; LLM errors counted separately, with fail-closed and
fail-open variants; and exact McNemar tests of what layering adds over `regex`:
attacks newly caught, and false alarms newly raised. Reports carry row indices and
aggregates only, never sample text.

Usage (needs network access to huggingface.co and the model API):
    export OPENROUTER_API_KEY=...
    # first run pins the datasets (review the pins diff before committing it)
    uv run python -m rype_security.benchmark --model openai/gpt-4o-mini --record
    uv run python -m rype_security.benchmark --model openai/gpt-4o-mini
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from rype_security.injection import scan_injection
from rype_security.llm_classifier import LLMInjectionClassifier, VerdictCache

PINS_PATH = Path("evalsets/external/security-datasets.json")
CACHE_DIR = Path("docs/reports/.security-benchmark-cache")
HF = "https://huggingface.co"


# --------------------------------------------------------------------------- data


@dataclass
class Row:
    index: int
    text: str
    is_attack: bool


@dataclass
class DatasetSpec:
    name: str
    repo: str
    split: str
    text_column: str = "text"
    label_column: str = "label"
    positive_label: Any = 1
    license: str = ""


EXTERNAL = {
    "deepset-test": DatasetSpec(
        "deepset-test", "deepset/prompt-injections", "test", license="Apache-2.0"
    ),
    "deepset-train": DatasetSpec(
        "deepset-train", "deepset/prompt-injections", "train", license="Apache-2.0"
    ),
}


class DatasetPinError(RuntimeError):
    """The pinned dataset is missing, or the downloaded bytes do not match the pin."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_pins(path: Path = PINS_PATH) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def record_pin(spec: DatasetSpec, client: httpx.Client) -> dict[str, Any]:
    """Resolve the dataset's current commit and the file for `spec.split`."""
    info = client.get(f"{HF}/api/datasets/{spec.repo}").raise_for_status().json()
    revision = info["sha"]
    files = [s["rfilename"] for s in info.get("siblings", [])]
    candidates = [
        f for f in files if f.endswith(".parquet") and f"{spec.split}-" in f.split("/")[-1]
    ]
    if len(candidates) != 1:
        raise DatasetPinError(
            f"expected one {spec.split} parquet file in {spec.repo}, found {candidates}"
        )
    data = _download(client, spec.repo, revision, candidates[0])
    return {
        "repo": spec.repo,
        "revision": revision,
        "file": candidates[0],
        "sha256": sha256(data),
        "license": spec.license,
        "recorded": datetime.now(UTC).strftime("%Y-%m-%d"),
    }


def _download(client: httpx.Client, repo: str, revision: str, file: str) -> bytes:
    url = f"{HF}/datasets/{repo}/resolve/{revision}/{file}"
    return client.get(url, follow_redirects=True).raise_for_status().content


def fetch_pinned(spec: DatasetSpec, pin: dict[str, Any], client: httpx.Client) -> bytes:
    """Bytes of the pinned file, from the local cache or the network, hash-checked."""
    cached = CACHE_DIR / f"{pin['sha256']}.parquet"
    data = (
        cached.read_bytes()
        if cached.exists()
        else _download(client, pin["repo"], pin["revision"], pin["file"])
    )
    if sha256(data) != pin["sha256"]:
        raise DatasetPinError(
            f"{spec.name}: downloaded file does not match the pinned SHA-256; refusing to use it"
        )
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def parse_parquet(data: bytes, spec: DatasetSpec) -> list[Row]:
    import pyarrow.parquet as pq  # optional extra: rype-security[benchmark]

    table = pq.read_table(io.BytesIO(data), columns=[spec.text_column, spec.label_column])
    texts = table.column(spec.text_column).to_pylist()
    labels = table.column(spec.label_column).to_pylist()
    return [
        Row(i, str(t), label == spec.positive_label)
        for i, (t, label) in enumerate(zip(texts, labels, strict=True))
        if isinstance(t, str) and t.strip()
    ]


def load_redteam(path: Path = Path("evalsets/security-redteam-v1.jsonl")) -> list[Row]:
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return [Row(i, r["text"], r["label"] == "injection") for i, r in enumerate(rows)]


# ------------------------------------------------------------------------ metrics


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (sound at n small or p near 0/1)."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


@dataclass
class Score:
    tp: int = 0
    fn: int = 0
    fp: int = 0
    tn: int = 0
    errors_on_attacks: int = 0
    errors_on_benign: int = 0
    missed: list[int] = field(default_factory=list)
    false_alarms: list[int] = field(default_factory=list)

    def add(self, row: Row, flagged: bool | None) -> None:
        if flagged is None:  # classifier error: kept apart, never guessed
            if row.is_attack:
                self.errors_on_attacks += 1
            else:
                self.errors_on_benign += 1
            return
        if row.is_attack:
            self.tp, self.fn = self.tp + flagged, self.fn + (not flagged)
            if not flagged:
                self.missed.append(row.index)
        else:
            self.fp, self.tn = self.fp + flagged, self.tn + (not flagged)
            if flagged:
                self.false_alarms.append(row.index)

    def summary(self) -> dict[str, Any]:
        attacks, benign = self.tp + self.fn, self.fp + self.tn
        flagged = self.tp + self.fp
        # Fail-closed treats an error as "flagged", fail-open as "passed".
        closed_tpr = (self.tp + self.errors_on_attacks) / max(1, attacks + self.errors_on_attacks)
        closed_fpr = (self.fp + self.errors_on_benign) / max(1, benign + self.errors_on_benign)
        open_tpr = self.tp / max(1, attacks + self.errors_on_attacks)
        return {
            "attacks_scored": attacks,
            "benign_scored": benign,
            "tpr": round(self.tp / attacks, 4) if attacks else None,
            "tpr_ci95": [round(x, 4) for x in wilson(self.tp, attacks)],
            "fpr": round(self.fp / benign, 4) if benign else None,
            "fpr_ci95": [round(x, 4) for x in wilson(self.fp, benign)],
            "precision": round(self.tp / flagged, 4) if flagged else None,
            "precision_ci95": [round(x, 4) for x in wilson(self.tp, flagged)],
            "errors": self.errors_on_attacks + self.errors_on_benign,
            "fail_closed": {"tpr": round(closed_tpr, 4), "fpr": round(closed_fpr, 4)},
            "fail_open_tpr": round(open_tpr, 4),
            "confusion": {"tp": self.tp, "fn": self.fn, "fp": self.fp, "tn": self.tn},
            "missed_indices": self.missed,
            "false_alarm_indices": self.false_alarms,
        }


def evaluate(
    rows: Iterable[Row],
    llm: Callable[[str], bool | None] | None,
    progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    scores = {"regex": Score()}
    if llm is not None:
        scores["llm"], scores["regex_or_llm"] = Score(), Score()
    # The layered detector flags everything the regex flags, so the paired
    # question is what the LLM *adds*: attacks newly caught, and false alarms
    # newly raised on benign rows. Both are discordant counts for McNemar.
    gained = added_false_alarms = 0
    for n, row in enumerate(rows, 1):
        regex = scan_injection(row.text).is_suspicious
        scores["regex"].add(row, regex)
        if llm is not None:
            verdict = llm(row.text)
            scores["llm"].add(row, verdict)
            combined = True if regex else verdict  # an LLM error cannot clear a regex hit
            scores["regex_or_llm"].add(row, combined)
            if combined and not regex:
                if row.is_attack:
                    gained += 1
                else:
                    added_false_alarms += 1
        if progress:
            progress(n)
    result: dict[str, Any] = {name: s.summary() for name, s in scores.items()}
    if llm is not None:
        result["layering"] = {
            "attacks_gained": gained,
            "attacks_gained_p": round(mcnemar_exact(0, gained), 6),
            "false_alarms_added": added_false_alarms,
            "false_alarms_added_p": round(mcnemar_exact(0, added_false_alarms), 6),
        }
    return result


# ------------------------------------------------------------------------- report


def _fmt(summary: dict[str, Any], key: str) -> str:
    value, ci = summary.get(key), summary.get(f"{key}_ci95")
    if value is None or ci is None:
        return "n/a"
    return f"{value:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Injection classifier benchmark v1",
        "",
        f"*Generated {report['date']} by `python -m rype_security.benchmark`. "
        f"LLM: `{report['model']}` (prompt {report['prompt_version']}).*",
        "",
        "Recall, false-positive rate and precision with 95% Wilson intervals. LLM errors are",
        "excluded from the main rates and shown separately, with the fail-closed rates that",
        "treat an error as a flag. Reports list row indices only; no sample text.",
        "",
    ]
    for name, block in report["datasets"].items():
        meta = block["meta"]
        lines += [
            f"## {name}",
            "",
            f"{meta['description']} Rows: {meta['rows']} ({meta['attacks']} attacks, "
            f"{meta['benign']} benign).",
            "",
            "| Detector | Recall | False-positive rate | Precision | Errors |",
            "|---|---|---|---|---|",
        ]
        for detector in ("regex", "llm", "regex_or_llm"):
            if detector in block["results"]:
                s = block["results"][detector]
                lines.append(
                    f"| `{detector}` | {_fmt(s, 'tpr')} | {_fmt(s, 'fpr')} | "
                    f"{_fmt(s, 'precision')} | {s['errors']} |"
                )
        if (m := block["results"].get("layering")) is not None:
            lines += [
                "",
                f"Layering the LLM on the regexes caught {m['attacks_gained']} more attacks "
                f"(exact McNemar p = {m['attacks_gained_p']}) and raised "
                f"{m['false_alarms_added']} more false alarms (p = {m['false_alarms_added_p']}).",
            ]
        lines.append("")
    lines += [
        "## Limits",
        "",
        "- Labels are the dataset authors'. External sets mix languages and include",
        "  borderline rows; a disagreement is not automatically a detector error.",
        "- An LLM classifier is itself an attack surface and adds latency and cost per",
        "  document; this report measures whether it earns that before it is wired in.",
        "- One model, one prompt version, temperature 0. Other models need their own runs.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", required=True, help="model id on the OpenAI-compatible API")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--datasets", default="deepset-test,deepset-train,redteam-v1")
    parser.add_argument(
        "--record", action="store_true", help="pin datasets missing from the pins file"
    )
    parser.add_argument("--out", type=Path, default=Path("docs/reports"))
    args = parser.parse_args()

    pins = load_pins()
    names = [n.strip() for n in args.datasets.split(",") if n.strip()]
    classifier = LLMInjectionClassifier(
        args.model, base_url=args.base_url, cache=VerdictCache(CACHE_DIR / "verdicts.jsonl")
    )

    def llm(text: str) -> bool | None:
        verdict = classifier.classify(text)
        return None if verdict.label == "error" else verdict.is_injection

    datasets: dict[str, Any] = {}
    with httpx.Client(timeout=120) as http:
        for name in names:
            if name == "redteam-v1":
                rows = load_redteam()
                description = "Internal red-team set the regexes were tuned on (reference only)."
            else:
                spec = EXTERNAL[name]
                if name not in pins:
                    if not args.record:
                        raise DatasetPinError(f"{name} is not pinned; rerun with --record")
                    pins[name] = record_pin(spec, http)
                    PINS_PATH.parent.mkdir(parents=True, exist_ok=True)
                    PINS_PATH.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")
                rows = parse_parquet(fetch_pinned(spec, pins[name], http), spec)
                pin = pins[name]
                description = (
                    f"`{pin['repo']}` ({pin['license']}) split `{spec.split}` at commit "
                    f"`{pin['revision'][:12]}`, file SHA-256 `{pin['sha256'][:12]}`."
                )
            print(f"{name}: {len(rows)} rows", flush=True)
            results = evaluate(rows, llm, progress=lambda n: print(f"  {n}", end="\r", flush=True))
            datasets[name] = {
                "meta": {
                    "description": description,
                    "rows": len(rows),
                    "attacks": sum(r.is_attack for r in rows),
                    "benign": sum(not r.is_attack for r in rows),
                },
                "results": results,
            }
    classifier.close()

    report = {
        "report": "security-classifier-v1",
        "kind": "security-detection",
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "model": args.model,
        "prompt_version": "v1",
        "datasets": datasets,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "security-classifier-v1-summary.json").write_text(
        json.dumps(report, indent=1) + "\n", encoding="utf-8"
    )
    (args.out / "security-classifier-v1.md").write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
