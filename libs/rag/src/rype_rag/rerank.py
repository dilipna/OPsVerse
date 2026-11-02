from functools import cached_property
from typing import Protocol

from rype_rag.model_integrity import PinMode, verify_loaded


class Reranker(Protocol):
    def rerank(self, query: str, texts: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Cross-encoder reranking via fastembed; model loads lazily on first call."""

    def __init__(self, model: str = "BAAI/bge-reranker-v2-m3", pin_mode: PinMode = "off"):
        self._model_name = model
        self._pin_mode: PinMode = pin_mode

    @cached_property
    def _model(self):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        return verify_loaded(
            self._model_name, TextCrossEncoder(model_name=self._model_name), self._pin_mode
        )

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        return list(self._model.rerank(query, texts))
