from functools import cached_property
from typing import Protocol

from opsverse_rag.schemas import SparseVec


class Embedder(Protocol):
    dense_dim: int

    def embed_dense(self, texts: list[str]) -> list[list[float]]: ...

    def embed_sparse(self, texts: list[str]) -> list[SparseVec]: ...


class FastEmbedEmbedder:
    """Dense + BM25-sparse embeddings via fastembed (ONNX, CPU-friendly).

    Models load lazily on first embed call (one-time download), so
    constructing this object is cheap. dense_dim must match the model.
    """

    def __init__(
        self,
        dense_model: str = "BAAI/bge-base-en-v1.5",
        sparse_model: str = "Qdrant/bm25",
        dense_dim: int = 768,
    ):
        self._dense_name = dense_model
        self._sparse_name = sparse_model
        self.dense_dim = dense_dim

    @cached_property
    def _dense(self):
        from fastembed import TextEmbedding  # heavy import kept out of module load

        return TextEmbedding(model_name=self._dense_name)

    @cached_property
    def _sparse(self):
        from fastembed import SparseTextEmbedding

        return SparseTextEmbedding(model_name=self._sparse_name)

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._dense.embed(texts)]

    def embed_sparse(self, texts: list[str]) -> list[SparseVec]:
        return [
            SparseVec(indices=emb.indices.tolist(), values=emb.values.tolist())
            for emb in self._sparse.embed(texts)
        ]
