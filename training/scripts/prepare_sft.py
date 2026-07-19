"""Turn the generated instruction pairs into a train/val SFT dataset for TRL.

Runs locally (no GPU). Re-applies the contamination guard as a belt-and-braces
check (the generator already decontaminates, but eval sets may have grown),
splits deterministically, and writes chat-format JSONL that
`datasets.load_dataset("json", ...)` + TRL SFTTrainer consume directly:
each row is {"messages": [{"role","content"}, ...]}.

Usage:
    uv run python training/scripts/prepare_sft.py \
        --in data/instructions/instructions-v1.jsonl --out data/sft
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from opsverse_evals.contamination import ContaminationGuard
from opsverse_training.schemas import InstructionPair

SEED = 20260718
VAL_FRACTION = 0.1


def load_pairs(path: Path) -> list[InstructionPair]:
    return [
        InstructionPair.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_chat_jsonl(path: Path, pairs: list[InstructionPair]) -> None:
    with path.open("w", encoding="utf-8") as sink:
        for pair in pairs:
            row = {"messages": [m.model_dump() for m in pair.messages]}
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="inp",
        type=Path,
        default=Path("data/instructions/instructions-v1.jsonl"),
    )
    parser.add_argument("--out", type=Path, default=Path("data/sft"))
    parser.add_argument("--evalsets", type=Path, default=Path("evalsets"))
    args = parser.parse_args()

    pairs = load_pairs(args.inp)
    guard = ContaminationGuard.from_evalsets_dir(args.evalsets)
    if not guard.hashes:
        raise SystemExit("no frozen eval sets found — refusing to build an unguarded dataset")

    kept: list[InstructionPair] = []
    dropped = 0
    for pair in pairs:
        if guard.is_contaminated(pair.user_text):
            dropped += 1
        else:
            kept.append(pair)

    rng = random.Random(SEED)
    rng.shuffle(kept)
    n_val = max(1, round(len(kept) * VAL_FRACTION))
    val, train = kept[:n_val], kept[n_val:]

    args.out.mkdir(parents=True, exist_ok=True)
    write_chat_jsonl(args.out / "train.jsonl", train)
    write_chat_jsonl(args.out / "val.jsonl", val)

    manifest = {
        "source": str(args.inp),
        "total_pairs": len(pairs),
        "contaminated_dropped": dropped,
        "train": len(train),
        "val": len(val),
        "by_format": dict(Counter(p.format for p in kept)),
        "by_tool": dict(Counter(p.tool or "unknown" for p in kept)),
        "format": "chat/messages (TRL SFTTrainer ready)",
        "decontamination": {
            "guard": "opsverse_evals.contamination.ContaminationGuard",
            "eval_questions_protected": len(guard.hashes),
        },
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
