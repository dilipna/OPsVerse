import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["health"])

CHECK_TIMEOUT_S = 2.0


@router.get("/live")
async def live() -> dict[str, str]:
    """Liveness: the process is up. No dependency checks."""
    return {"status": "ok"}


async def _check_postgres(request: Request) -> None:
    async with request.app.state.db_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis(request: Request) -> None:
    await request.app.state.redis.ping()


async def _check_qdrant(request: Request) -> None:
    await request.app.state.qdrant.get_collections()


async def _check_minio(request: Request) -> None:
    endpoint = request.app.state.settings.minio_endpoint
    resp = await request.app.state.http.get(f"{endpoint}/minio/health/live")
    resp.raise_for_status()


CHECKS: dict[str, Callable[[Request], Awaitable[None]]] = {
    "postgres": _check_postgres,
    "redis": _check_redis,
    "qdrant": _check_qdrant,
    "minio": _check_minio,
}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, object]:
    """Readiness: every backing service answers within the timeout."""

    async def run_check(name: str, check: Callable[[Request], Awaitable[None]]):
        start = time.perf_counter()
        try:
            await asyncio.wait_for(check(request), timeout=CHECK_TIMEOUT_S)
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            return name, {"ok": True, "latency_ms": latency_ms}
        except Exception as exc:
            return name, {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    results = dict(await asyncio.gather(*(run_check(n, c) for n, c in CHECKS.items())))
    all_ok = all(r["ok"] for r in results.values())
    response.status_code = 200 if all_ok else 503
    return {"status": "ready" if all_ok else "degraded", "checks": results}
