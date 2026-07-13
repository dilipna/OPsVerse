# ADR-0001: Monorepo with uv workspaces

Date: 2026-07-12 · Status: Accepted

## Context

OpsVerse spans an API service, a web UI, an MCP server, training scripts, and several shared
Python libraries (ingestion, RAG, evals, security). These pieces share Pydantic schemas and
settings, and they evolve together — a chunking change touches ingestion, RAG, and evals in
one commit.

## Decision

One repository, managed as a **uv workspace**: apps under `apps/`, shared libraries under
`libs/`, each with its own `pyproject.toml`, one shared lockfile at the root.

## Consequences

- Cross-cutting changes (schema + consumers) land atomically; no version dance between repos.
- `uv sync` gives every developer and CI job an identical environment from one `uv.lock`.
- Workspace source dependencies (`opsverse-core = { workspace = true }`) keep imports honest —
  apps consume libraries through declared dependencies, not path hacks.
- Tradeoff: CI runs the whole workspace on every PR. Acceptable at this scale; if it slows,
  add path-filtered jobs rather than splitting repos.

## Alternatives considered

- **Polyrepo** — rejected: version-pinning overhead across 5+ internal packages for a
  single-developer project buys isolation nobody needs.
- **Poetry/pip-tools monorepo** — rejected: no first-class workspace concept; uv's is native,
  and uv is also the fastest installer for CI.
