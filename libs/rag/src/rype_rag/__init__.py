"""Hybrid retrieval over Qdrant: dense (BGE-M3) + sparse (BM25) with RRF fusion,
optional cross-encoder reranking."""

from rype_rag.chat import ChatEvent, ChatService, ChatTurn
from rype_rag.retriever import Retriever
from rype_rag.schemas import RetrievedChunk, SearchFilters, SearchMode
from rype_rag.store import ChunkPoint, QdrantStore

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
