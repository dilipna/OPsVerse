"""Small cached CPU text compatibility check; no download, GPU or LLM call."""

import argparse
import json
import math
import os
import sys
from importlib.metadata import version
from pathlib import Path

from opsverse_rag.embeddings import FastEmbedEmbedder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--pillow-module", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.pillow_module:
        sys.path.insert(0, str(args.pillow_module.resolve()))
        assert version("pillow") == "12.3.0", (
            "The isolated baseline must actually use Pillow 12.3.0"
        )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from fastembed import TextEmbedding

    # Bound threads and use the existing small cached ONNX model. This exercises
    # the application's text wrapper, not FastEmbed's unsupported image paths.
    embedder = FastEmbedEmbedder("BAAI/bge-small-en-v1.5", dense_dim=384)
    embedder.__dict__["_dense"] = TextEmbedding(
        model_name="BAAI/bge-small-en-v1.5",
        cache_dir=str(args.cache),
        threads=1,
        local_files_only=True,
    )
    documents = [
        "Checkpointed ingestion preserves source evidence.",
        "A bounded prototype needs review.",
    ]
    vectors = embedder.embed_dense(documents)
    for vector in vectors:
        assert len(vector) == 384 and all(math.isfinite(x) for x in vector)
        assert abs(sum(x * x for x in vector) - 1) < 1e-4
    difference = None
    reference_pillow = None
    if args.reference:
        reference = json.loads(args.reference.read_text(encoding="utf-8"))
        assert reference["fastembed"] == version("fastembed")
        assert reference["pillow"] == "12.3.0"
        assert reference["threads"] == 1
        reference_pillow = reference["pillow"]
        difference = max(
            abs(x - y)
            for a, b in zip(reference["vectors"][:2], vectors, strict=True)
            for x, y in zip(a, b, strict=True)
        )
    report = {
        "pass": difference is None or difference < 1e-6,
        "fastembed": version("fastembed"),
        "pillow": version("pillow"),
        "model": "BAAI/bge-small-en-v1.5",
        "documents": 2,
        "dimensions": 384,
        "threads": 1,
        "reference_max_absolute_difference": difference,
        "reference_pillow": reference_pillow,
        "scope": (
            "Actual application text wrapper with cached small ONNX model and one thread. "
            "A reference comparison requires matching runtime/model/thread configuration. "
            "No 768-dimension default-model, image/PDF, or LLM quality claim."
        ),
        "vectors": vectors,
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "vectors"}, indent=2))
    if difference is not None:
        assert difference < 1e-6, f"Reference parity failed: maximum difference {difference}"


if __name__ == "__main__":
    main()
