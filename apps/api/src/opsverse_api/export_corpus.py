"""Export the ingested corpus from Postgres to JSONL for DVC versioning.

Writes data/corpus/{documents,chunks}.jsonl plus a manifest with counts and
the git revision, so a corpus version is reproducible and diffable. Track the
folder with `dvc add data/corpus` and `dvc push` (remote: MinIO, see
.dvc/config).

Usage:
    uv run python -m opsverse_api.export_corpus [--out data/corpus]
"""

import argparse
import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from opsverse_core.settings import get_settings


def git_rev() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


async def export(out: Path) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    out.mkdir(parents=True, exist_ok=True)

    async with engine.connect() as conn:
        docs = (
            (
                await conn.execute(
                    sa.text(
                        "SELECT id::text, source_type, uri, sha256, status, doc_type, tool,"
                        " created_at FROM documents ORDER BY created_at, id"
                    )
                )
            )
            .mappings()
            .all()
        )
        chunks = (
            (
                await conn.execute(
                    sa.text(
                        "SELECT id::text, document_id::text, ord, text, token_count, section,"
                        " language, embedding_status FROM chunks"
                        " ORDER BY document_id, ord"
                    )
                )
            )
            .mappings()
            .all()
        )
    await engine.dispose()

    with (out / "documents.jsonl").open("w", encoding="utf-8") as sink:
        for row in docs:
            record = dict(row)
            record["created_at"] = record["created_at"].isoformat()
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (out / "chunks.jsonl").open("w", encoding="utf-8") as sink:
        for row in chunks:
            sink.write(json.dumps(dict(row), ensure_ascii=False) + "\n")

    by_tool: dict[str, int] = {}
    for row in docs:
        by_tool[row["tool"] or "unknown"] = by_tool.get(row["tool"] or "unknown", 0) + 1
    manifest = {
        "exported_at": datetime.now(UTC).isoformat(),
        "git_rev": git_rev(),
        "documents": len(docs),
        "chunks": len(chunks),
        "documents_by_tool": dict(sorted(by_tool.items())),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/corpus"))
    args = parser.parse_args()
    asyncio.run(export(args.out))


if __name__ == "__main__":
    main()
