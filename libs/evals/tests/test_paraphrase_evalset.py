from opsverse_evals.paraphrase_evalset import acceptable_paraphrase, token_overlap


def test_token_overlap():
    assert token_overlap("how do I scale pods", "how do I scale pods") == 1.0
    assert token_overlap("scale pods", "unrelated words entirely") == 0.0
    # partial overlap: {configure, probes} shared out of 6 unique tokens
    assert 0.0 < token_overlap("configure liveness probes", "configure readiness probes") < 1.0


def test_acceptable_paraphrase():
    original = "How do I configure liveness probes for a Deployment?"
    assert acceptable_paraphrase(
        original, "What's the way to set up liveness checks on a Deployment?"
    )
    # identical modulo case/punctuation is not a paraphrase
    assert not acceptable_paraphrase(original, original.upper() + "!!")
    assert not acceptable_paraphrase(original, "")
    assert not acceptable_paraphrase(original, "too short")
