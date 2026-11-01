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

The flagship candidate changes the research gateway's failure policy: with a
positive daily spend threshold, unavailable Redis or an invalid spend counter
refuses new provider calls. Cache failure alone is a normal miss. A zero threshold
explicitly disables the spend guard; it is not an authorization to use paid services.
The threshold still accounts after calls and does not reserve in-flight spend, so it
must not be treated as a hard billing ceiling. Public browser retrieval is independent
of this gateway and needs neither Redis nor provider credentials.
