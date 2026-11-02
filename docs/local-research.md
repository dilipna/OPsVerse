# Optional full-stack research setup

The public navigator does not need this infrastructure. The original local stack remains:

```bash
docker compose -f infra/compose/docker-compose.yml up -d --wait
uv sync --all-packages --frozen
# copy .env.example to .env and configure your own model endpoint as needed
(cd apps/api && uv run alembic upgrade head)
uv run uvicorn rype_api.main:app --port 8100
uv run arq rype_api.worker.WorkerSettings
```

`apps/web` is the optional full-stack UI; `opslm-demo` is the public website. Dependencies
include Postgres, Redis, Qdrant and MinIO. MCP setup: [README](../apps/mcp-server/README.md).
Full Docker/database/model deployment was not rehearsed here. CI builds the API, runs
existing tests and a real Qdrant retrieval smoke test. Inference needs a separate endpoint.
No paid jobs or model downloads are needed for the navigator verification chain.

## Upgrading a local stack from the OpsVerse name

The project was renamed to RYPE. Code, packages, settings and infrastructure names changed
with it, so a stack created under the old name needs one of these:

- **Start fresh (simplest).** The compose project, Postgres database and user, Qdrant
  collection and MinIO bucket are now `rype`, `rype_kb` and `rype-raw`, so
  `docker compose -f infra/compose/docker-compose.yml up -d` creates new, empty volumes.
  Re-run ingestion and the embedding sweep.
- **Keep the old data.** Rename every `OPSVERSE_*` variable in your `.env` to `RYPE_*`, then
  point the new names at the old resources, e.g. `RYPE_QDRANT_COLLECTION=opsverse_kb`,
  `RYPE_DATABASE_URL=postgresql+asyncpg://opsverse:opsverse@localhost:5432/opsverse`,
  `RYPE_MINIO_ACCESS_KEY=opsverse`, `RYPE_MINIO_SECRET_KEY=opsverse-secret`,
  `RYPE_MINIO_BUCKET_RAW=opsverse-raw`, and run compose with `-p opsverse` so it reuses the
  old volumes.

Settings now read only the `RYPE_` prefix; old `OPSVERSE_` variables are ignored.
