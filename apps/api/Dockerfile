# Build from the repository root: docker build -f apps/api/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Install third-party deps first so they cache independently of source changes.
COPY pyproject.toml uv.lock ./
COPY libs/core/pyproject.toml libs/core/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN uv sync --frozen --no-install-workspace --no-dev --package opsverse-api

COPY libs libs
COPY apps/api apps/api
RUN uv sync --frozen --no-dev --package opsverse-api

FROM python:3.12-slim-bookworm
WORKDIR /app
RUN groupadd -r opsverse && useradd -r -g opsverse opsverse
COPY --from=builder --chown=opsverse:opsverse /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER opsverse
EXPOSE 8000
CMD ["uvicorn", "opsverse_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
