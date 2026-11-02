"""Hash-pinned model artifacts (threat model T-09, supply chain).

fastembed fetches models by *name*, which pins neither a revision nor the bytes:
whatever the upstream repository serves at download time is what gets loaded. This
module pins the bytes instead. `registry/model-pins.json` records the SHA-256 of every
file in each model's directory; after fastembed downloads a model and before it embeds
anything, the directory is hashed and compared.

- A mismatch, an extra file or a missing file **always** refuses the model.
- An *unpinned* model follows the mode: `enforce` refuses it, `warn` logs and loads,
  `off` skips checking. Production should run `enforce` (the Kubernetes config does).

Record pins after a deliberate, reviewed download:
    uv run python -m rype_rag.model_integrity record BAAI/bge-base-en-v1.5 Qdrant/bm25
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

PINS_PATH = Path("registry/model-pins.json")
PinMode = Literal["enforce", "warn", "off"]
_IGNORED_PARTS = {".cache", ".huggingface", ".locks"}


class ModelIntegrityError(RuntimeError):
    """A model's files do not match their pinned hashes, or it is unpinned under enforce."""


def hash_model_dir(model_dir: Path) -> dict[str, str]:
    """SHA-256 of every regular file under `model_dir`, keyed by relative path.

    Symlinks are followed (Hugging Face snapshots link into a blob store), and
    download bookkeeping directories are ignored.
    """
    if not model_dir.is_dir():
        raise ModelIntegrityError(f"model directory not found: {model_dir}")
    hashes: dict[str, str] = {}
    for path in sorted(model_dir.rglob("*")):
        rel = path.relative_to(model_dir)
        if _IGNORED_PARTS & set(rel.parts) or path.name.endswith(".lock") or not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        hashes[rel.as_posix()] = digest.hexdigest()
    return hashes


def load_pins(path: Path = PINS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def verify_model_dir(
    name: str, model_dir: Path, mode: PinMode, pins: dict[str, Any] | None = None
) -> None:
    if mode == "off":
        return
    pins = load_pins() if pins is None else pins
    pinned = pins.get(name)
    if pinned is None:
        message = f"model {name!r} has no pinned hashes in {PINS_PATH}"
        if mode == "enforce":
            raise ModelIntegrityError(message)
        logger.warning("%s; loading unverified (mode=warn)", message)
        return
    expected: dict[str, str] = pinned["files"]
    actual = hash_model_dir(model_dir)
    problems = [
        *(f"missing {f}" for f in sorted(expected.keys() - actual.keys())),
        *(f"unexpected {f}" for f in sorted(actual.keys() - expected.keys())),
        *(
            f"changed {f}"
            for f in sorted(expected.keys() & actual.keys())
            if expected[f] != actual[f]
        ),
    ]
    if problems:
        raise ModelIntegrityError(f"model {name!r} failed integrity check: {', '.join(problems)}")


def model_dir_of(loaded: Any) -> Path | None:
    """The on-disk directory of a fastembed model wrapper, if it exposes one."""
    inner = getattr(loaded, "model", loaded)
    path = getattr(inner, "_model_dir", None)
    return Path(path) if path else None


def verify_loaded(name: str, loaded: Any, mode: PinMode, pins: dict[str, Any] | None = None) -> Any:
    """Verify a freshly constructed fastembed model; return it unchanged if it passes."""
    if mode == "off":
        return loaded
    model_dir = model_dir_of(loaded)
    if model_dir is None:
        message = f"cannot locate the files of model {name!r} to verify them"
        if mode == "enforce":
            raise ModelIntegrityError(message)
        logger.warning(message)
        return loaded
    verify_model_dir(name, model_dir, mode, pins)
    return loaded


def _construct(name: str) -> Any:
    from fastembed import SparseTextEmbedding, TextEmbedding
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    for factory in (TextEmbedding, SparseTextEmbedding, TextCrossEncoder):
        supported = {m["model"] for m in factory.list_supported_models()}
        if name in supported:
            return factory(model_name=name)
    raise SystemExit(f"{name} is not a fastembed text, sparse or rerank model")


def record(names: list[str], path: Path = PINS_PATH) -> dict[str, Any]:
    pins = load_pins(path)
    for name in names:
        model_dir = model_dir_of(_construct(name))
        if model_dir is None:
            raise SystemExit(f"cannot locate files for {name}")
        files = hash_model_dir(model_dir)
        pins[name] = {
            "files": files,
            "recorded": datetime.now(UTC).strftime("%Y-%m-%d"),
            "total_files": len(files),
        }
        print(f"pinned {name}: {len(files)} files")
    path.write_text(json.dumps(pins, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return pins


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="download models and pin their file hashes")
    rec.add_argument("models", nargs="+")
    ver = sub.add_parser("verify", help="load models and check them against the pins")
    ver.add_argument("models", nargs="+")
    args = parser.parse_args()
    if args.command == "record":
        record(args.models)
    else:
        for name in args.models:
            verify_loaded(name, _construct(name), "enforce")
            print(f"verified {name}")


if __name__ == "__main__":
    main()
