"""Fetch user-supplied URLs without letting them reach internal addresses.

Threat model T-07 (SSRF). Three controls, each closing a different bypass:

1. **Every hop is checked.** Redirects are followed by hand; automatic following
   would let a public URL bounce the worker to an internal one.
2. **The checked address is the connected address.** The transport's network
   backend resolves the hostname once, requires every answer to be public, and
   opens the TCP connection to that exact IP. There is no second lookup for a
   rebinding DNS server to answer differently. TLS still verifies the
   certificate against the hostname, because httpcore passes the URL's host
   (not the IP) as the server name.
3. **Bounded response.** The body is streamed and capped.

The client ignores proxy environment variables (`trust_env=False`): a proxy
would make the backend connect to the proxy, not the target, and silently
bypass control 2.
"""

from __future__ import annotations

import ssl
from collections.abc import Iterable
from functools import partial
from typing import cast

import anyio.to_thread
import certifi
import httpcore
import httpx

from opsverse_security.netguard import (
    Resolver,
    UnsafeURLError,
    resolve_public_host,
    resolve_public_url,
)

MAX_URL_BYTES = 20 * 1024 * 1024
MAX_URL_REDIRECTS = 5
FETCH_TIMEOUT_S = 30.0


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve, validate, then connect to the validated address only."""

    def __init__(
        self,
        resolver: Resolver | None = None,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ):
        self._resolve = (
            partial(resolve_public_host, resolver=resolver) if resolver else resolve_public_host
        )
        # httpcore exposes a placeholder AnyIOBackend to type checkers; at
        # runtime it is a real AsyncNetworkBackend subclass.
        self._inner = inner or cast(httpcore.AsyncNetworkBackend, httpcore.AnyIOBackend())
        self.connected: list[tuple[str, str, int]] = []  # (hostname, ip, port), for audit/tests

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = await anyio.to_thread.run_sync(self._resolve, host, port)
        address = addresses[0]
        self.connected.append((host, address, port))
        return await self._inner.connect_tcp(
            address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, *args, **kwargs) -> httpcore.AsyncNetworkStream:
        raise UnsafeURLError("unix sockets are not allowed for URL ingestion")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PinnedTransport(httpx.AsyncHTTPTransport):
    """httpx transport whose every TCP connection goes through the pinned backend."""

    def __init__(self, backend: PinnedNetworkBackend):
        super().__init__(trust_env=False)
        self.backend = backend
        # Replace the default pool with one using our backend; everything else
        # (HTTP/1.1, TLS with hostname verification) is httpcore's own code.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(cafile=certifi.where()),
            network_backend=backend,
        )


async def fetch_public_url(
    uri: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver | None = None,
) -> bytes:
    """GET `uri`, following up to MAX_URL_REDIRECTS public redirects."""
    check = partial(resolve_public_url, resolver=resolver) if resolver else resolve_public_url
    transport = transport or PinnedTransport(PinnedNetworkBackend(resolver))
    url = uri
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_S, follow_redirects=False, transport=transport, trust_env=False
    ) as client:
        for _ in range(MAX_URL_REDIRECTS + 1):
            # Fast, clear rejection before any connection is attempted; the
            # backend's check at connect time is the authoritative one.
            await anyio.to_thread.run_sync(check, url)
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeURLError("redirect without a Location header")
                    url = str(response.url.join(location))
                    continue
                response.raise_for_status()
                body = bytearray()
                async for piece in response.aiter_bytes():
                    body.extend(piece)
                    if len(body) > MAX_URL_BYTES:
                        raise UnsafeURLError(f"response exceeds {MAX_URL_BYTES} bytes")
                return bytes(body)
    raise UnsafeURLError(f"more than {MAX_URL_REDIRECTS} redirects")
