# ADR-0002: Qdrant over pgvector and Pinecone

Date: 2026-07-12 · Status: Accepted

## Context

Phase 3 requires **hybrid retrieval** (dense + sparse/BM25-style), rich metadata filtering
(tool, version, doc type), and local-first operation under Docker Compose with zero hosting
budget.

## Decision

**Qdrant**, one collection with named dense + sparse vectors (BGE-M3 produces both), payload
metadata for filtering.

## Consequences

- Hybrid search is a single engine feature (server-side fusion of named vectors), not a
  client-side merge of two systems — simpler ranking code and one operational dependency.
- Filtered search is first-class and indexed; version-awareness filters (Phase 11) come free.
- Runs in Compose with a volume; the same image deploys anywhere later.
- Tradeoff: one more service to operate versus pgvector-inside-Postgres. Accepted because
  pgvector has no native sparse-vector/hybrid story, which would force a bolt-on BM25 layer.

## Alternatives considered

- **pgvector** — rejected for missing native sparse/hybrid support; would need pg_search or
  app-side RRF over `tsvector`, spreading retrieval logic across two query languages.
- **Pinecone** — rejected: hosted-only conflicts with the free-tier constraint and the
  local-first demo story; also weaker as a portfolio signal than operating the store yourself.
- Revisit if corpus scale or ops burden changes; the retrieval interface in `libs/rag` keeps
  the store swappable.
