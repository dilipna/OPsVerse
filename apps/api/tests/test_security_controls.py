"""API-level security controls: ingest authentication, SSRF guard, upload names."""

import httpcore
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from rype_api.routers.ingest import safe_filename
from rype_api.safe_fetch import PinnedNetworkBackend, PinnedTransport, fetch_public_url
from rype_core.settings import get_settings
from rype_security.netguard import UnsafeURLError

DOC_URL = {"source_type": "url", "uri": "https://kubernetes.io/docs/concepts/"}


def client_for(env) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test")


@pytest.fixture
def settings_env(monkeypatch):
    """Set RYPE_* variables for one test and rebuild the cached settings."""

    def apply(**values: str) -> None:
        for key, value in values.items():
            monkeypatch.setenv(f"RYPE_{key.upper()}", value)
        get_settings.cache_clear()

    yield apply
    get_settings.cache_clear()


async def test_ingest_requires_key_when_configured(env, settings_env):
    settings_env(admin_api_key="s3cret-admin-key")
    async with client_for(env) as client:
        missing = await client.post("/v1/ingest", json=DOC_URL)
        wrong = await client.post("/v1/ingest", json=DOC_URL, headers={"X-API-Key": "nope"})
        bearer = await client.post(
            "/v1/ingest", json=DOC_URL, headers={"Authorization": "Bearer s3cret-admin-key"}
        )
        header = await client.post(
            "/v1/ingest", json=DOC_URL, headers={"X-API-Key": "s3cret-admin-key"}
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert bearer.status_code == 202
    assert header.status_code == 202
    assert len(env.queue.jobs) == 2  # rejected requests queued nothing


async def test_ingest_fails_closed_outside_dev_without_key(env, settings_env):
    settings_env(environment="prod")
    async with client_for(env) as client:
        resp = await client.post("/v1/ingest", json=DOC_URL)
    assert resp.status_code == 503
    assert env.queue.jobs == []


@pytest.mark.parametrize(
    "uri",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/admin",
        "http://localhost/",
        "http://qdrant.svc/collections",
        "http://[::1]/",
        "file:///etc/passwd",
        "https://user:pw@example.com/",
        "https://example.com:6379/",
    ],
)
async def test_ingest_rejects_internal_or_unsafe_urls(env, uri):
    async with client_for(env) as client:
        resp = await client.post("/v1/ingest", json={"source_type": "url", "uri": uri})
    assert resp.status_code == 422, resp.text
    assert env.queue.jobs == []


def public_resolver(host: str, port: int) -> list[str]:
    return {"docs.example.org": ["93.184.215.14"], "evil.example.org": ["93.184.215.15"]}.get(
        host, ["10.0.0.5"]
    )


async def test_fetch_rechecks_every_redirect_hop():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "evil.example.org":
            return httpx.Response(302, headers={"location": "http://internal.example.org/secret"})
        return httpx.Response(200, content=b"never reached")

    transport = httpx.MockTransport(handler)
    with pytest.raises(UnsafeURLError, match="non-public"):
        await fetch_public_url(
            "https://evil.example.org/start", transport=transport, resolver=public_resolver
        )


async def test_fetch_follows_public_redirects_and_returns_body():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, content=b"# Pods\n")

    body = await fetch_public_url(
        "https://docs.example.org/old",
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )
    assert body == b"# Pods\n"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\boot.ini", "boot.ini"),
        ("notes on pods.md", "notes_on_pods.md"),
        ("", "upload.txt"),
        (None, "upload.txt"),
        ("....", "upload.txt"),
    ],
)
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected


async def test_chat_and_search_reject_oversized_input(env):
    from rype_api import deps

    # Validation must reject before any service is used; these are never called.
    env.app.dependency_overrides[deps.get_chat_service] = lambda: None
    env.app.dependency_overrides[deps.get_retriever] = lambda: None
    async with client_for(env) as client:
        chat = await client.post("/v1/chat", json={"query": "x" * 4_001, "stream": False})
        search = await client.post("/v1/search", json={"query": "x" * 4_001})
        history = await client.post(
            "/v1/chat",
            json={
                "query": "ok",
                "stream": False,
                "history": [{"role": "user", "content": "hi"}] * 33,
            },
        )
    assert chat.status_code == 422
    assert search.status_code == 422
    assert history.status_code == 422


class RecordingBackend(httpcore.AsyncMockBackend):
    """Mock network that records which address a connection was opened to."""

    def __init__(self, response: bytes):
        super().__init__([response])
        self.hosts: list[str] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.hosts.append(host)
        return await super().connect_tcp(host, port, timeout, local_address, socket_options)


OK_RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\n\r\n# Pods\n"


async def test_connection_goes_to_the_checked_address_not_a_new_lookup():
    inner = RecordingBackend(OK_RESPONSE)
    backend = PinnedNetworkBackend(resolver=public_resolver, inner=inner)
    body = await fetch_public_url(
        "http://docs.example.org/pods",
        transport=PinnedTransport(backend),
        resolver=public_resolver,
    )
    assert body == b"# Pods\n"
    # The socket was opened to the validated IP, never to the hostname, so no
    # second DNS lookup happened between check and connect.
    assert inner.hosts == ["93.184.215.14"]
    assert backend.connected == [("docs.example.org", "93.184.215.14", 80)]


async def test_dns_rebinding_between_check_and_connect_is_refused():
    answers = iter([["93.184.215.14"], ["169.254.169.254"]])

    def rebinding(host: str, port: int) -> list[str]:
        return next(answers)  # public for the pre-check, metadata IP at connect

    inner = RecordingBackend(OK_RESPONSE)
    with pytest.raises(UnsafeURLError, match="non-public"):
        await fetch_public_url(
            "http://rebind.example.org/",
            transport=PinnedTransport(PinnedNetworkBackend(resolver=rebinding, inner=inner)),
            resolver=rebinding,
        )
    assert inner.hosts == []  # no connection was ever opened


async def test_pinned_transport_ignores_proxy_environment(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://10.0.0.1:3128")
    inner = RecordingBackend(OK_RESPONSE)
    backend = PinnedNetworkBackend(resolver=public_resolver, inner=inner)
    await fetch_public_url(
        "http://docs.example.org/", transport=PinnedTransport(backend), resolver=public_resolver
    )
    assert inner.hosts == ["93.184.215.14"]  # target, not the proxy
