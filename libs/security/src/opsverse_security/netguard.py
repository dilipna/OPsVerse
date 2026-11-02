"""Server-side request forgery (SSRF) guard for URL ingestion.

`POST /v1/ingest` accepts a URL that the worker later fetches. Without a guard,
anyone who can reach the API can make the worker request internal services
(Postgres, Redis, Qdrant, MinIO on the compose network) or a cloud metadata
endpoint, then read the response back through retrieval.

Two checks, used at two points:

- `check_url_shape` — cheap, no network. Run in the API handler so obviously
  unsafe URLs are rejected with a 422 before a job is queued.
- `resolve_public_url` — resolves the hostname and requires every address to
  be publicly routable. Run in the worker immediately before each fetch,
  including every redirect hop.

Residual risk, stated rather than hidden: a hostile DNS server can return a
public address to the check and a private one to the HTTP client moments later
(DNS rebinding). Pinning the connection to the checked address closes that gap
and is listed in docs/security/threat-model.md.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443})
_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "metadata.google.internal"})
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".svc", ".cluster.local")

Resolver = Callable[[str, int], list[str]]


class UnsafeURLError(ValueError):
    """The URL must not be fetched by the server."""


def _default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url_shape(url: str) -> tuple[str, int]:
    """Reject URLs that are unsafe without needing DNS. Returns (host, port)."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError(f"malformed URL: {exc}") from exc
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme {scheme or '(none)'!r} is not allowed; use http or https")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURLError("credentials in URLs are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURLError("URL has no host")
    port = port or (443 if scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"port {port} is not allowed")
    if host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeURLError(f"host {host!r} is internal")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not _is_public(host):
        raise UnsafeURLError(f"address {host} is not publicly routable")
    return host, port


def resolve_public_url(url: str, resolver: Resolver = _default_resolver) -> list[str]:
    """Require every resolved address of the URL's host to be public."""
    host, port = check_url_shape(url)
    try:
        addresses = resolver(host, port)
    except OSError as exc:
        raise UnsafeURLError(f"cannot resolve {host!r}") from exc
    if not addresses:
        raise UnsafeURLError(f"{host!r} resolved to no addresses")
    private = [a for a in addresses if not _is_public(a)]
    if private:
        raise UnsafeURLError(f"{host!r} resolves to non-public address {private[0]}")
    return addresses
