from functools import cached_property
from typing import Protocol


class Reranker(Protocol):
    def rerank(self, query: str, texts: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Cross-encoder reranking via fastembed; model loads lazily on first call."""

    def __init__(self, model: str = "BAAI/bge-reranker-v2-m3"):
        self._model_name = model

    @cached_property
    def _model(self):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        return TextCrossEncoder(model_name=self._model_name)

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        return list(self._model.rerank(query, texts))
