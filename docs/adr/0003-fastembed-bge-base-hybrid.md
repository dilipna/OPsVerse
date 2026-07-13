# ADR-0003: fastembed + bge-base-en-v1.5 dense / BM25 sparse for hybrid retrieval

Date: 2026-07-12 · Status: Accepted

## Context

Retrieval needs dense + sparse vectors, produced locally at zero cost, on CPU,
on a Windows/WSL dev machine. The original plan named BGE-M3 (which emits both
dense and sparse vectors) via fastembed.

## Decision

- **Runtime: fastembed (ONNX)** — no PyTorch dependency (~2GB saved), fast CPU
  inference, one library for dense + sparse + reranking.
- **Dense: `BAAI/bge-base-en-v1.5` (768d)** — fastembed 0.8 does not ship
  BGE-M3 for dense embedding (verified via `TextEmbedding.list_supported_models()`),
  so the plan's model was unavailable in the chosen runtime. bge-base beats
  bge-large on CPU latency ~3× with a small quality gap, and the corpus is
  English-only technical documentation.
- **Sparse: `Qdrant/bm25`** — term-frequency vectors with IDF applied
  server-side by Qdrant (`Modifier.IDF`); classic BM25 keyword behaviour.
- **Reranker: `BAAI/bge-reranker-base`** (bge-reranker-v2-m3 likewise not in
  fastembed's supported list).
- **Fusion: RRF** server-side in Qdrant over the two named vectors.

All four choices are `OPSVERSE_*` settings, not code constants; swapping to a
sentence-transformers/BGE-M3 stack later is an embedder implementation +
re-embed sweep, nothing else.

## Consequences

- Whole retrieval stack runs pip-install-light and CPU-only; embedding ~400
  chunks takes minutes, not hours.
- 768d dense vectors (vs 1024d planned): smaller index, slightly lower ceiling;
  retrieval evaluation in Phase 3 will quantify whether an upgrade is worth it.
- Multilingual queries lose dense quality (bge-base is English); accepted for
  this corpus.
