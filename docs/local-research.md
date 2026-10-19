# Optional full-stack research setup

The public navigator does not need this infrastructure. The original local stack remains:

```bash
docker compose -f infra/compose/docker-compose.yml up -d --wait
uv sync --all-packages --frozen
# copy .env.example to .env and configure your own model endpoint as needed
(cd apps/api && uv run alembic upgrade head)
uv run uvicorn opsverse_api.main:app --port 8100
uv run arq opsverse_api.worker.WorkerSettings
```

`apps/web` is the optional full-stack UI; `opslm-demo` is the public website. Dependencies
include Postgres, Redis, Qdrant and MinIO. MCP setup: [README](../apps/mcp-server/README.md).
Full Docker/database/model deployment was not rehearsed here. CI builds the API, runs
existing tests and a real Qdrant retrieval smoke test. Inference needs a separate endpoint.
No paid jobs or model downloads are needed for the navigator verification chain.
