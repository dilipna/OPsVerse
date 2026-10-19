"""Build the public browser corpus through the real ingestion pipeline, without models.

uv run python -m opsverse_evals.runbook_fixture [--check]
"""

import argparse
import hashlib
import json
from pathlib import Path

from opsverse_ingestion.pipeline import ingest_bytes

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = ROOT / "opslm-demo/public/runbooks.json"


def build() -> dict:
    fixture = ROOT / "evalsets/runbooks"
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    chunks = []
    stats = []
    for document in manifest["documents"]:
        raw = (fixture / "raw" / document["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != document["sha256"]:
            raise ValueError(f"source hash mismatch: {document['id']}")
        result = ingest_bytes(raw, document["file"], tool="kubernetes")
        if not result.chunks:
            raise ValueError(f"no usable chunks: {document['id']}")
        for chunk in result.chunks:
            chunks.append(
                {
                    "id": f"{document['id']}:{chunk.ord}",
                    "document": document["id"],
                    "section": chunk.section or document["id"],
                    "text": chunk.text,
                    "source": document["source"],
                    "canonical": document["canonical"],
                }
            )
        stats.append({"id": document["id"], **result.stats.model_dump()})
    return {
        "schema": 1,
        "mode": "extractive-term-overlap",
        "manifest": manifest,
        "chunks": chunks,
        "ingestion": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != text:
            raise SystemExit("browser corpus is stale: regenerate with runbook_fixture")
        print("raw-source hashes, ingestion and browser corpus match")
    else:
        OUTPUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
