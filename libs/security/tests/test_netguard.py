import pytest

from rype_security.netguard import UnsafeURLError, check_url_shape, resolve_public_url


@pytest.mark.parametrize(
    "url",
    [
        "https://kubernetes.io/docs/",
        "http://example.com/a?b=c",
        "https://93.184.215.14/",
    ],
)
def test_public_shapes_pass(url):
    check_url_shape(url)


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("ftp://example.com/x", "scheme"),
        ("gopher://example.com/", "scheme"),
        ("example.com/no-scheme", "scheme"),
        ("https://a:b@example.com/", "credentials"),
        ("http://10.1.2.3/", "not publicly routable"),
        ("http://192.168.0.1/", "not publicly routable"),
        ("http://100.64.0.1/", "not publicly routable"),
        ("http://[::ffff:127.0.0.1]/", "not publicly routable"),
        ("http://[fd00::1]/", "not publicly routable"),
        ("http://metadata.google.internal/", "internal"),
        ("http://redis.default.svc.cluster.local/", "internal"),
        ("https://example.com:8443/", "port"),
        ("https:///path-only", "no host"),
    ],
)
def test_unsafe_shapes_rejected(url, reason):
    with pytest.raises(UnsafeURLError, match=reason):
        check_url_shape(url)


def test_resolution_must_be_all_public():
    def mixed(host, port):
        return ["93.184.215.14", "10.0.0.7"]

    with pytest.raises(UnsafeURLError, match=r"non-public address 10\.0\.0\.7"):
        resolve_public_url("https://rebind.example.org/", resolver=mixed)


def test_resolution_failure_is_unsafe():
    def broken(host, port):
        raise OSError("nxdomain")

    with pytest.raises(UnsafeURLError, match="cannot resolve"):
        resolve_public_url("https://nope.example.org/", resolver=broken)


def test_public_resolution_returns_addresses():
    assert resolve_public_url(
        "https://ok.example.org/", resolver=lambda h, p: ["93.184.215.14"]
    ) == ["93.184.215.14"]
