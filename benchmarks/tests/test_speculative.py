"""Prompt-lookup speculative decoding: losslessness + amortization.

Loaded by path (benchmarks is not an installed package), matching test_harness.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "spec_decode", REPO / "benchmarks" / "techniques" / "speculative.py"
)
assert SPEC and SPEC.loader
spec_decode = importlib.util.module_from_spec(SPEC)
sys.modules["spec_decode"] = spec_decode
SPEC.loader.exec_module(spec_decode)

greedy_decode = spec_decode.greedy_decode
prompt_lookup_draft = spec_decode.prompt_lookup_draft
speculative_decode = spec_decode.speculative_decode

EOS = -1


def oracle_from(full: list[int]):
    """Deterministic greedy target: token i of the run is full[len(prompt)+i]."""

    def target(prefix: tuple[int, ...]) -> int:
        return full[len(prefix)] if len(prefix) < len(full) else EOS

    return target


def test_prompt_lookup_finds_and_copies_continuation():
    # suffix (7,8) last appeared at index 0 -> copy up to k tokens after it
    assert prompt_lookup_draft([7, 8, 9, 7, 8], n_gram=2, k=3) == [9, 7, 8]
    assert prompt_lookup_draft([7, 8, 9, 7, 8], n_gram=2, k=1) == [9]
    # no earlier occurrence of the suffix -> nothing to draft
    assert prompt_lookup_draft([1, 2, 3], n_gram=2, k=3) == []
    # guards
    assert prompt_lookup_draft([1], n_gram=2, k=3) == []
    assert prompt_lookup_draft([1, 2, 3], n_gram=2, k=0) == []


def test_speculative_output_is_identical_to_greedy():
    prompt = [0, 1, 2]
    # a repetitive tail is exactly where prompt-lookup shines
    full = prompt + [7, 8, 9] * 5
    target = oracle_from(full)

    reference = greedy_decode(target, prompt, max_new=15, eos=EOS)
    out, _ = speculative_decode(target, prompt, max_new=15, n_gram=2, k=4, eos=EOS)

    assert out == reference  # losslessness: speculation never changes the answer
    assert out == full[len(prompt) :]


def test_speculative_amortizes_target_passes():
    prompt = [0, 1, 2]
    full = prompt + [7, 8, 9] * 8
    target = oracle_from(full)

    out, stats = speculative_decode(target, prompt, max_new=24, n_gram=2, k=4, eos=EOS)

    assert stats.tokens_generated == len(out) == 24
    # fewer target forward passes than tokens => real amortization
    assert stats.target_forward_passes < stats.tokens_generated
    assert stats.speedup_proxy > 1.0
    # the repetition is highly predictable, so most drafts get accepted
    assert stats.acceptance_rate > 0.5


def test_non_repetitive_text_degrades_gracefully_to_greedy():
    # strictly increasing = no repeated n-grams => no useful draft, but still
    # correct and never worse than one token per pass.
    prompt = [0]
    full = list(range(0, 12))
    target = oracle_from(full)

    out, stats = speculative_decode(target, prompt, max_new=11, n_gram=2, k=4, eos=EOS)

    assert out == greedy_decode(target, prompt, max_new=11, eos=EOS)
    assert stats.speedup_proxy >= 1.0  # bonus token per pass keeps it at >= greedy
