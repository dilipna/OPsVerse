from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from opsverse_api.deps import get_retriever
from opsverse_rag import RetrievedChunk, Retriever, SearchFilters, SearchMode

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=8, ge=1, le=50)
    mode: SearchMode = SearchMode.HYBRID
    rerank: bool = False
    filters: SearchFilters | None = None


class SearchResponse(BaseModel):
    hits: list[RetrievedChunk]


@router.post("", response_model=SearchResponse)
async def search(
    body: SearchRequest, retriever: Annotated[Retriever, Depends(get_retriever)]
) -> SearchResponse:
    hits = await retriever.search(
        body.query, k=body.k, mode=body.mode, rerank=body.rerank, filters=body.filters
    )
    return SearchResponse(hits=hits)
