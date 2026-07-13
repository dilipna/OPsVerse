from typing import Any

from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient, models

from opsverse_rag.schemas import RetrievedChunk, SearchFilters, SearchMode, SparseVec

DENSE = "dense"
SPARSE = "sparse"


class ChunkPoint(BaseModel):
    id: str
    dense: list[float]
    sparse: SparseVec
    payload: dict[str, Any]


def _build_filter(filters: SearchFilters | None) -> models.Filter | None:
    if filters is None:
        return None
    conditions: list[models.Condition] = [
        models.FieldCondition(key=field, match=models.MatchValue(value=value))
        for field, value in filters.model_dump().items()
        if value is not None
    ]
    return models.Filter(must=conditions) if conditions else None


class QdrantStore:
    def __init__(self, client: AsyncQdrantClient, collection: str, dense_dim: int = 1024):
        self._client = client
        self.collection = collection
        self.dense_dim = dense_dim

    async def ensure_collection(self) -> None:
        if await self._client.collection_exists(self.collection):
            return
        await self._client.create_collection(
            collection_name=self.collection,
            vectors_config={
                DENSE: models.VectorParams(size=self.dense_dim, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={
                # BM25 term frequencies from fastembed; IDF applied server-side
                SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )

    async def upsert(self, points: list[ChunkPoint]) -> None:
        await self._client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(
                    id=point.id,
                    vector={
                        DENSE: point.dense,
                        SPARSE: models.SparseVector(
                            indices=point.sparse.indices, values=point.sparse.values
                        ),
                    },
                    payload=point.payload,
                )
                for point in points
            ],
        )

    async def query(
        self,
        *,
        mode: SearchMode,
        k: int,
        dense: list[float] | None = None,
        sparse: SparseVec | None = None,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        flt = _build_filter(filters)
        prefetch_k = max(k * 2, 20)

        if mode is SearchMode.HYBRID:
            if dense is None or sparse is None:
                raise ValueError("hybrid mode needs both dense and sparse query vectors")
            response = await self._client.query_points(
                collection_name=self.collection,
                prefetch=[
                    models.Prefetch(query=dense, using=DENSE, limit=prefetch_k, filter=flt),
                    models.Prefetch(
                        query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                        using=SPARSE,
                        limit=prefetch_k,
                        filter=flt,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=k,
                with_payload=True,
            )
        elif mode is SearchMode.DENSE:
            if dense is None:
                raise ValueError("dense mode needs a dense query vector")
            response = await self._client.query_points(
                collection_name=self.collection,
                query=dense,
                using=DENSE,
                query_filter=flt,
                limit=k,
                with_payload=True,
            )
        else:
            if sparse is None:
                raise ValueError("sparse mode needs a sparse query vector")
            response = await self._client.query_points(
                collection_name=self.collection,
                query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                using=SPARSE,
                query_filter=flt,
                limit=k,
                with_payload=True,
            )

        return [
            RetrievedChunk(
                id=str(point.id),
                score=point.score,
                text=str(payload.get("text", "")),
                section=payload.get("section"),
                source=str(payload.get("source", "")),
                tool=payload.get("tool"),
                doc_type=payload.get("doc_type"),
                language=payload.get("language"),
                document_id=str(payload.get("document_id", "")),
            )
            for point in response.points
            if (payload := point.payload or {}) is not None
        ]
