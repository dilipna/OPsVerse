from opsverse_security.output_guard import (
    OutputGuard,
    StreamingOutputGuard,
    hosts_from_sources,
)

guard = OutputGuard({"kubernetes.io"})


def test_markdown_images_are_removed():
    result = guard.sanitize("See ![chart](https://untrusted.test/p.png?d=abc) here.")
    assert "untrusted.test" not in result.text
    assert "[image removed: chart]" in result.text
    assert result.findings == {"image_removed": 1}


def test_allowlisted_images_are_removed_too():
    # No answer needs to load an image, so even trusted hosts are dropped.
    result = guard.sanitize("![x](https://kubernetes.io/logo.png)")
    assert result.text == "[image removed: x]"


def test_html_and_reference_images_are_removed():
    result = guard.sanitize('<img src="https://untrusted.test/a"> and ![alt][ref]')
    assert "<img" not in result.text
    assert result.findings["image_removed"] == 2


def test_links_kept_only_for_allowlisted_hosts():
    text = (
        "[probes](https://kubernetes.io/docs/tasks/) and "
        "[docs](https://sub.kubernetes.io/x) and "
        "[click](https://untrusted.test/?q=secret)"
    )
    result = guard.sanitize(text)
    assert "(https://kubernetes.io/docs/tasks/)" in result.text
    assert "(https://sub.kubernetes.io/x)" in result.text
    assert "untrusted.test" not in result.text
    assert "click [link removed]" in result.text
    assert result.findings == {"link_removed": 1}


def test_lookalike_host_is_not_allowlisted():
    result = guard.sanitize("[k8s](https://kubernetes.io.untrusted.test/)")
    assert "untrusted.test" not in result.text


def test_dangerous_schemes_are_removed():
    result = guard.sanitize("[run](javascript:alert(1)) <data:text/html,hi>")
    assert "javascript:" not in result.text
    assert "data:" not in result.text


def test_reference_definitions_are_checked():
    text = "[a][1]\n\n[1]: https://untrusted.test/x\n[2]: https://kubernetes.io/ok"
    result = guard.sanitize(text)
    assert "untrusted.test" not in result.text
    assert "https://kubernetes.io/ok" in result.text


def test_secrets_in_answers_are_redacted():
    result = guard.sanitize("Your key is AKIAABCDEFGHIJKLMNOP.")
    assert "AKIA" not in result.text
    assert result.findings == {"secret_redacted:aws_access_key_id": 1}


def test_anchor_links_and_plain_prose_untouched():
    text = "Check [the section](#probes). Use `kubectl describe pod`."
    assert guard.sanitize(text).text == text


def test_hosts_from_sources_ignores_non_urls():
    assert hosts_from_sources(
        ["https://Kubernetes.io/docs/a", "github://k8s/website/x.md", "upload.md"]
    ) == {"kubernetes.io"}


def test_streaming_never_leaks_a_construct_split_across_tokens():
    stream = StreamingOutputGuard(guard)
    pieces = [
        "Before ![x](https://untr",
        "usted.test/p?d=",
        "abc) after\n",
        "tail [l](https://",
        "untrusted.test)",
    ]
    out = "".join(stream.feed(p) for p in pieces) + stream.flush()
    assert "untrusted.test" not in out
    assert out.startswith("Before [image removed: x] after\n")
    assert dict(stream.findings) == {"image_removed": 1, "link_removed": 1}


def test_streaming_releases_long_lines():
    stream = StreamingOutputGuard(guard, max_buffer=10)
    assert stream.feed("a" * 12) == "a" * 12
    assert stream.flush() == ""
