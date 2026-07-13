import hashlib
import uuid
from typing import Annotated, Any, Literal

import anyio.to_thread
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from opsverse_api.db.models import Document, IngestJob
from opsverse_api.deps import get_arq_pool, get_object_store, get_session
from opsverse_core.object_store import ObjectStore

router = APIRouter(prefix="/ingest", tags=["ingest"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

Session = Annotated[AsyncSession, Depends(get_session)]
Queue = Annotated[ArqRedis, Depends(get_arq_pool)]
Store = Annotated[ObjectStore, Depends(get_object_store)]


class IngestRequest(BaseModel):
    source_type: Literal["url", "github_repo"]
    uri: str = Field(min_length=1, description="URL, or owner/repo for github_repo")
    tool: str | None = None
    # github_repo only: keep just files under this repo-relative prefix,
    # e.g. "content/en/docs" for kubernetes/website. Large doc repos exceed
    # the per-repo file cap; the prefix targets the part worth indexing.
    path_prefix: str | None = None


class JobOut(BaseModel):
    job_id: uuid.UUID
    status: str
    stats: dict[str, Any] | None = None
    error: str | None = None


async def _enqueue(session: AsyncSession, queue: ArqRedis, job: IngestJob) -> JobOut:
    session.add(job)
    await session.commit()
    await queue.enqueue_job("run_ingest_job", str(job.id))
    return JobOut(job_id=job.id, status=job.status)


@router.post("", status_code=202, response_model=JobOut)
async def create_ingest(body: IngestRequest, session: Session, queue: Queue) -> JobOut:
    job = IngestJob(kind=body.source_type, payload=body.model_dump())
    return await _enqueue(session, queue, job)


@router.post("/upload", status_code=202, response_model=JobOut)
async def upload(file: UploadFile, session: Session, queue: Queue, store: Store) -> JobOut:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 50MB limit")
    if not raw:
        raise HTTPException(status_code=422, detail="empty file")

    filename = file.filename or "upload.txt"
    sha = hashlib.sha256(raw).hexdigest()
    key = f"raw/{sha}/{filename}"
    await anyio.to_thread.run_sync(store.put_bytes, key, raw)

    document = Document(source_type="upload", uri=key, sha256=sha)
    session.add(document)
    await session.flush()
    job = IngestJob(
        kind="upload",
        payload={"document_id": str(document.id), "filename": filename},
    )
    return await _enqueue(session, queue, job)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, session: Session) -> JobOut:
    job = await session.get(IngestJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobOut(job_id=job.id, status=job.status, stats=job.stats, error=job.error)
