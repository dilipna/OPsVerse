"""Hybrid retrieval over Qdrant: dense (BGE-M3) + sparse (BM25) with RRF fusion,
optional cross-encoder reranking."""

from opsverse_rag.chat import ChatEvent, ChatService, ChatTurn
from opsverse_rag.retriever import Retriever
from opsverse_rag.schemas import RetrievedChunk, SearchFilters, SearchMode
from opsverse_rag.store import ChunkPoint, QdrantStore

__all__ = [
    "ChatEvent",
    "ChatService",
    "ChatTurn",
    "ChunkPoint",
    "QdrantStore",
    "RetrievedChunk",
    "Retriever",
    "SearchFilters",
    "SearchMode",
]
