"""Per-client request rate limits (threat model T-10, unbounded consumption).

Each route group (chat, search, ingest) gets a fixed one-minute window per
client. The client is the admin key when one is sent, otherwise the peer
address. Counters live in Redis so every API replica shares them; if Redis is
unreachable the limiter falls back to an in-process window rather than
disabling limits, so an outage degrades accuracy, not protection.

`X-Forwarded-For` is ignored on purpose: it is client-controlled unless a
trusted proxy rewrites it, and trusting it would let a caller pick a fresh
identity per request. Deploy behind a proxy that sets the peer address.
"""

from __future__ import annotations

import hmac
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection

from rype_core.settings import get_settings

logger = logging.getLogger(__name__)

WINDOW_S = 60


class RedisCounter(Protocol):
    async def incr(self, key: str) -> Any: ...
    async def expire(self, key: str, seconds: int) -> Any: ...


class RateLimiter:
    def __init__(self, redis: RedisCounter | None = None, clock: Callable[[], float] = time.time):
        self.redis = redis
        self._clock = clock
        self._local: dict[str, int] = {}
        self._local_window = -1

    def _window(self) -> int:
        return int(self._clock() // WINDOW_S)

    def _local_hit(self, key: str, window: int) -> int:
        if window != self._local_window:  # drop the previous window's counters
            self._local, self._local_window = {}, window
        self._local[key] = self._local.get(key, 0) + 1
        return self._local[key]

    async def hit(self, group: str, client: str) -> tuple[int, int]:
        """Count one request; return (count in this window, seconds until reset)."""
        window = self._window()
        key = f"rype:ratelimit:{group}:{client}:{window}"
        retry_after = max(1, int((window + 1) * WINDOW_S - self._clock()))
        if self.redis is not None:
            try:
                count = int(await self.redis.incr(key))
                if count == 1:
                    await self.redis.expire(key, WINDOW_S * 2)
                return count, retry_after
            except Exception:
                logger.warning("rate limiter: redis unavailable, using local window")
        return self._local_hit(key, window), retry_after


def client_identity(request: HTTPConnection) -> str:
    """The admin when the valid admin key is presented, otherwise the peer address.

    An unverified key must not change identity: chat and search accept
    anonymous callers, so a random key per request would otherwise reset the
    caller's budget every time.
    """
    expected = get_settings().admin_api_key
    auth = request.headers.get("authorization", "")
    key = request.headers.get("x-api-key") or (
        auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    )
    if expected and key and hmac.compare_digest(key.encode(), expected.encode()):
        return "admin"
    return "ip:" + (request.client.host if request.client else "unknown")


async def exceeded(conn: HTTPConnection, group: str) -> tuple[int, int] | None:
    """Count one request; return (limit, retry_after) if it is over budget."""
    limit = getattr(get_settings(), f"rate_limit_{group}_per_minute")
    if limit <= 0:
        return None
    limiter: RateLimiter = conn.app.state.rate_limiter
    count, retry_after = await limiter.hit(group, client_identity(conn))
    return (limit, retry_after) if count > limit else None


def rate_limit(group: str) -> Callable[[Request], Any]:
    """FastAPI dependency: 429 with Retry-After once a client exceeds its budget."""

    async def dependency(request: Request) -> None:
        if over := await exceeded(request, group):
            limit, retry_after = over
            raise HTTPException(
                status_code=429,
                detail=f"rate limit exceeded: {limit} {group} requests per minute",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
