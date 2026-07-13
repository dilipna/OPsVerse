# OpsVerse AI

Production-grade **LLM engineering platform** for the DevOps / MLOps / LLMOps community —
built to demonstrate the complete lifecycle of modern AI systems:

> data engineering → RAG → evaluation → fine-tuning (OpsLM) → gateway → inference
> optimization → observability → security → MCP

## Status

**Phase 1 — Foundation** (of 11). See [docs/adr/](docs/adr/) for architecture decisions.

## Stack

FastAPI · PostgreSQL · Redis · Qdrant · MinIO · uv workspaces · Docker Compose
(Later phases: BGE-M3 hybrid RAG, RAGAS/DeepEval, Unsloth QLoRA + DPO on Qwen3-4B,
LiteLLM gateway, vLLM/SGLang benchmarks, Langfuse, MCP server.)

## Quickstart

```bash
# 1. Infra stack (Postgres, Redis, Qdrant, MinIO)
docker compose -f infra/compose/docker-compose.yml up -d

# 2. Python environment (uv manages Python 3.12 automatically)
uv sync --all-packages

# 3. Apply DB migrations, then run the API and the job worker
(cd apps/api && uv run alembic upgrade head)
uv run uvicorn opsverse_api.main:app --reload --port 8100
uv run arq opsverse_api.worker.WorkerSettings

# 4. Verify
curl http://localhost:8100/health/ready   # per-dependency status

# 5. Ingest and search
curl -X POST http://localhost:8100/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_type":"github_repo","uri":"docker/awesome-compose","tool":"docker"}'
curl -X POST http://localhost:8100/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query":"how do I healthcheck a postgres container?","k":5}'
```

Configuration comes from `.env` (copy `.env.example`); every variable is prefixed `OPSVERSE_`.

## Development

```bash
uv run pytest -q            # tests
uv run ruff check .         # lint
uv run ruff format .        # format
uv run pyright              # types
```

## Repository layout

```
apps/api        FastAPI service (health, then ingest/search/chat/eval/benchmarks)
libs/core       shared settings & schemas (more libs arrive per phase)
infra/compose   local dev stack
docs/adr        architecture decision records
```
