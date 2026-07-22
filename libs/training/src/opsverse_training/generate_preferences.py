"""Build the DPO preference dataset from the committed SFT data (ADR-0015).

For every SFT example, keep the grounded answer as `chosen` and synthesize a
confident-but-ungrounded `rejected` with the bulk model. Writes TRL
conversational DPO rows to data/dpo/{train,val}.jsonl. Resumable: a
`.partial.jsonl` per split keyed by source id; re-running continues.

    uv run python -m opsverse_training.generate_preferences          # full run
    uv run python -m opsverse_training.generate_preferences --limit 20

Free-tier aware: throttled, uses the bulk `eval_generator_model`
(gemini-3.1-flash-lite), never the 20/day chat model. The prompts come from the
already-decontaminated SFT set, so no extra contamination guard is needed here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_training.preferences import (
    PreferenceError,
    build_preference_pair,
    build_reject_messages,
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _done_prompts(partial: Path) -> set[str]:
    if not partial.exists():
        return set()
    return {
        json.loads(line)["prompt"][0]["content"]
        for line in partial.read_text(encoding="utf-8").splitlines()
        if line
    }


async def _build_split(
    llm: LiteLLMClient,
    model_name: str,
    sft_path: Path,
    out_path: Path,
    partial: Path,
    interval_s: float,
) -> int:
    rows = _read_jsonl(sft_path)
    done = _done_prompts(partial)
    if done:
        print(f"  resuming {out_path.name}: {len(done)} already done")

    written = len(done)
    with partial.open("a", encoding="utf-8") as sink:
        for row in rows:
            msgs = row.get("messages", [])
            if len(msgs) < 2 or msgs[0]["content"] in done:
                continue
            try:
                result = await llm.complete(build_reject_messages(msgs[0]["content"]))
                pair = build_preference_pair(
                    row, reject_fn=lambda _q, text=result.text: text, generator_model=model_name
                )
            except (PreferenceError, LLMError) as exc:
                print(f"  skip: {exc}")
                continue

            sink.write(json.dumps(pair.to_trl()) + "\n")
            sink.flush()
            written += 1
            if written % 25 == 0:
                print(f"  {out_path.name}: {written}")
            await asyncio.sleep(interval_s)

    # finalize: the partial (TRL rows) becomes the committed split
    out_path.write_text(partial.read_text(encoding="utf-8"), encoding="utf-8")
    return written


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sft-dir", type=Path, default=Path("data/sft"))
    parser.add_argument("--out", type=Path, default=Path("data/dpo"))
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None, help="cap rows per split (smoke test)")
    args = parser.parse_args()

    settings = get_settings()
    model = args.model or settings.eval_generator_model
    llm = LiteLLMClient(
        [model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=90,
        max_tokens=512,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for split in ("train", "val"):
        sft_path = args.sft_dir / f"{split}.jsonl"
        if args.limit is not None:  # smoke: trim the source
            rows = _read_jsonl(sft_path)[: args.limit]
            tmp = args.out / f"{split}.sft-trimmed.jsonl"
            tmp.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            sft_path = tmp
        out_path = args.out / f"{split}.jsonl"
        partial = args.out / f"{split}.partial.jsonl"
        total += await _build_split(llm, model, sft_path, out_path, partial, args.interval)

    print(f"wrote {total} preference pairs -> {args.out}/(train|val).jsonl")


if __name__ == "__main__":
    asyncio.run(main())
