"""Speculative decoding via prompt-lookup (n-gram) drafting.

Speculative decoding cuts decode latency by proposing several tokens cheaply,
then letting the target model *verify* them in a single forward pass: every
accepted draft token is one fewer sequential target step. The **prompt-lookup**
drafter needs no separate draft model at all — it copies the continuation of an
earlier occurrence of the current suffix (great for the repetitive, quote-heavy
text RAG/tool-use produces: file paths, keys, boilerplate).

Two properties matter and both are unit-tested here (offline, no GPU):

  1. **Losslessness.** The output is *token-identical* to plain greedy decoding
     of the target — speculation changes speed, never the answer. This holds
     because every emitted token equals the target's own greedy token at that
     position (accepted drafts match it by definition; on a mismatch we emit the
     target's correction; the trailing bonus token is the target's greedy pick).
  2. **Amortization.** One target *forward pass* (verification round) emits
     `accepted + 1` tokens, so `tokens / forward_passes` > 1 — the offline proxy
     for speedup. Real wall-clock speedup is measured on the GPU by the harness;
     acceptance rate is the quantity that transfers across both.

The target model is abstracted as a greedy oracle `TargetFn: prefix -> next
token`, so the algorithm is testable against a deterministic toy. On a served
model, the same acceptance-rate math is what the harness reports.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Greedy next-token oracle: given the full prefix, return argmax next token.
TargetFn = Callable[[tuple[int, ...]], int]


def greedy_decode(
    target: TargetFn, prompt: Sequence[int], max_new: int, eos: int | None = None
) -> list[int]:
    """Reference greedy decode — the ground truth speculation must reproduce."""
    seq = list(prompt)
    out: list[int] = []
    while len(out) < max_new:
        tok = target(tuple(seq))
        seq.append(tok)
        out.append(tok)
        if tok == eos:
            break
    return out


def prompt_lookup_draft(seq: Sequence[int], n_gram: int, k: int) -> list[int]:
    """Propose up to `k` tokens by matching the last `n_gram` tokens of `seq` to
    their most recent earlier occurrence and copying what followed it.

    No draft model: the "draft" is lifted from context. Returns [] if the suffix
    has not appeared before (nothing to copy).
    """
    if n_gram <= 0 or k <= 0 or len(seq) < n_gram:
        return []
    suffix = tuple(seq[-n_gram:])
    # Search earlier windows, most recent first (recency = best guess).
    for start in range(len(seq) - n_gram - 1, -1, -1):
        if tuple(seq[start : start + n_gram]) == suffix:
            return list(seq[start + n_gram : start + n_gram + k])
    return []


@dataclass
class SpecStats:
    tokens_generated: int = 0
    target_forward_passes: int = 0  # batched verification rounds — the cost proxy
    draft_tokens_proposed: int = 0
    draft_tokens_accepted: int = 0

    @property
    def acceptance_rate(self) -> float:
        """Fraction of proposed draft tokens accepted — transfers to the GPU."""
        if self.draft_tokens_proposed == 0:
            return 0.0
        return self.draft_tokens_accepted / self.draft_tokens_proposed

    @property
    def speedup_proxy(self) -> float:
        """Tokens emitted per target forward pass. Greedy is 1.0 by definition;
        > 1.0 is the amortization speculation buys (offline proxy for speedup)."""
        if self.target_forward_passes == 0:
            return 0.0
        return self.tokens_generated / self.target_forward_passes


def speculative_decode(
    target: TargetFn,
    prompt: Sequence[int],
    max_new: int,
    *,
    n_gram: int = 2,
    k: int = 4,
    eos: int | None = None,
) -> tuple[list[int], SpecStats]:
    """Prompt-lookup speculative decoding. Returns (tokens, stats).

    Output is guaranteed identical to `greedy_decode(target, prompt, max_new)`.
    Each while-iteration models one batched target forward pass that verifies the
    whole draft block and yields a bonus token — counted as one
    `target_forward_passes`. (The per-position `target(...)` calls below simulate
    what that single batched pass computes for every draft slot at once.)
    """
    seq = list(prompt)
    out: list[int] = []
    stats = SpecStats()

    while len(out) < max_new:
        draft = prompt_lookup_draft(seq, n_gram, k)
        stats.target_forward_passes += 1
        stats.draft_tokens_proposed += len(draft)

        mismatch = False
        for d in draft:
            greedy_tok = target(tuple(seq))
            if greedy_tok == d:
                seq.append(d)
                out.append(d)
                stats.draft_tokens_accepted += 1
                if d == eos or len(out) >= max_new:
                    stats.tokens_generated = len(out)
                    return out, stats
            else:
                # First mismatch: emit the target's correction, drop the rest.
                seq.append(greedy_tok)
                out.append(greedy_tok)
                mismatch = True
                if greedy_tok == eos or len(out) >= max_new:
                    stats.tokens_generated = len(out)
                    return out, stats
                break

        if not mismatch and len(out) < max_new:
            # Whole draft accepted (or empty): the verification pass also gives a
            # bonus token for free — the target's greedy pick at the new prefix.
            bonus = target(tuple(seq))
            seq.append(bonus)
            out.append(bonus)
            if bonus == eos:
                stats.tokens_generated = len(out)
                return out, stats

    stats.tokens_generated = len(out)
    return out, stats
