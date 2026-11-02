"""Preference-pair construction for DPO alignment of OpsLM (ADR-0015).

SFT teaches OpsLM *a* good answer; DPO teaches it to *prefer* the grounded,
hedged answer over a fluent hallucination — the failure mode that actually
hurts a DevOps assistant (a confident wrong `kubectl` incantation is worse than
"I'm not sure"). So each preference pair is:

  prompt   = a real ops question (reused from the SFT set)
  chosen   = the grounded, cited SFT answer
  rejected = a plausible-but-ungrounded answer (confident, invents specifics)

The rejected side is produced by a `reject_fn` (an LLM call in production), which
is *injected* so this module — the schema and the TRL-format conversion that
must be exactly right — is unit-tested without any API. DPO ("displaced RLHF in
most production settings") needs no reward model and no on-policy sampling,
which is what makes it feasible on the free-tier Colab path.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel, Field

# The instruction we give the generator to synthesize a *dispreferred* answer.
# Deliberately asks for confident-but-ungrounded — the exact thing DPO teaches
# OpsLM to rank below the grounded answer.
REJECT_SYSTEM = (
    "You write a DELIBERATELY DISPREFERRED answer for preference training. "
    "Given a DevOps question, produce a fluent, confident answer that is subtly "
    "WRONG or ungrounded: invent specifics (flags, fields, version numbers) not "
    "guaranteed by any source, never hedge, never say you are unsure. One short "
    "paragraph. Do not mention that it is wrong."
)


def build_reject_messages(question: str) -> list[dict[str, str]]:
    """Prompt for the reject generator. Pure, so the wiring is testable."""
    return [
        {"role": "system", "content": REJECT_SYSTEM},
        {"role": "user", "content": question},
    ]


class PreferencePair(BaseModel):
    """One DPO example. `to_trl()` yields TRL DPOTrainer conversational format."""

    id: str  # stable: "<source_id>:dpo"
    prompt: str
    chosen: str
    rejected: str
    source_id: str | None = None
    strategy: str = "ungrounded_llm"  # how `rejected` was produced
    generator_model: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_trl(self) -> dict[str, list[dict[str, str]]]:
        """Conversational DPO format consumed by trl.DPOTrainer."""
        return {
            "prompt": [{"role": "user", "content": self.prompt}],
            "chosen": [{"role": "assistant", "content": self.chosen}],
            "rejected": [{"role": "assistant", "content": self.rejected}],
        }


class PreferenceError(ValueError):
    """A pair that would be useless or harmful to train on."""


def build_preference_pair(
    sft_row: dict,
    reject_fn: Callable[[str], str],
    *,
    generator_model: str = "",
) -> PreferencePair:
    """Turn one SFT `{"messages":[user, assistant]}` row into a preference pair.

    `chosen` is the grounded SFT answer; `rejected = reject_fn(question)`.
    Raises PreferenceError if the sides are empty or identical (an identical
    pair gives DPO no signal and can destabilize the loss).
    """
    messages = sft_row.get("messages", [])
    if len(messages) < 2 or messages[0]["role"] != "user":
        raise PreferenceError("row is not a [user, assistant] SFT example")
    question = messages[0]["content"].strip()
    chosen = messages[1]["content"].strip()
    rejected = reject_fn(question).strip()

    if not question or not chosen or not rejected:
        raise PreferenceError("empty prompt/chosen/rejected")
    if chosen == rejected:
        raise PreferenceError("chosen == rejected (no preference signal)")

    source_id = sft_row.get("id")
    pair_id = f"{source_id}:dpo" if source_id else question[:48]
    return PreferencePair(
        id=pair_id,
        prompt=question,
        chosen=chosen,
        rejected=rejected,
        source_id=source_id,
        generator_model=generator_model,
    )
