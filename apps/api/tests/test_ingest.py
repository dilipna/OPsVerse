import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from opsverse_api.db.models import Chunk, Document, IngestJob
from opsverse_api.worker import run_ingest_job

MARKDOWN = b"""# Kubernetes Autoscaling

The Horizontal Pod Autoscaler adjusts replica counts based on observed CPU
utilization or custom metrics exposed through the metrics API adapters.
"""


def client_for(env) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test")


async def test_url_job_created_and_enqueued(env):
    async with client_for(env) as client:
        resp = await client.post(
            "/v1/ingest", json={"source_type": "url", "uri": "https://docs.docker.com/get.html"}
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert env.queue.jobs == [("run_ingest_job", (body["job_id"],))]


async def test_get_missing_job_is_404(env):
    async with client_for(env) as client:
        resp = await client.get(f"/v1/ingest/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_upload_then_worker_produces_chunks(env):
    async with client_for(env) as client:
        resp = await client.post(
            "/v1/ingest/upload",
            files={"file": ("k8s-hpa.md", MARKDOWN, "text/markdown")},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # raw bytes landed in the object store
        assert any(key.endswith("k8s-hpa.md") for key in env.store.objects)

        # run the worker inline against the same DB/store
        ctx = {"sessionmaker": env.sessionmaker, "store": env.store}
        await run_ingest_job(ctx, job_id)

        status = await client.get(f"/v1/ingest/{job_id}")

    body = status.json()
    assert body["status"] == "succeeded", body
    assert body["stats"]["chunks_kept"] >= 1

    async with env.sessionmaker() as session:
        document = (await session.execute(select(Document))).scalar_one()
        assert document.status == "ready"
        assert document.doc_type == "markdown"
        assert document.tool == "kubernetes"
        chunks = (await session.execute(select(Chunk))).scalars().all()
        assert chunks and chunks[0].section == "Kubernetes Autoscaling"


async def test_worker_marks_unparseable_upload_failed(env):
    binary = b"\x00\x01\x02binary"
    async with client_for(env) as client:
        resp = await client.post(
            "/v1/ingest/upload", files={"file": ("data.md", binary, "text/markdown")}
        )
        job_id = resp.json()["job_id"]
        ctx = {"sessionmaker": env.sessionmaker, "store": env.store}
        await run_ingest_job(ctx, job_id)
        status = await client.get(f"/v1/ingest/{job_id}")

    assert status.json()["status"] == "failed"
    assert "binary" in status.json()["error"]

    async with env.sessionmaker() as session:
        job = await session.get(IngestJob, uuid.UUID(job_id))
        assert job is not None and job.finished_at is not None
