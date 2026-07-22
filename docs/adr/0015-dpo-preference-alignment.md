# ADR-0015: DPO preference alignment for OpsLM-v2

**Status:** accepted (2026-07-22) — pipeline committed + tested; the DPO run is a Colab session

## Context

OpsLM-v1 is SFT-only: it learned *a* good answer per prompt, but SFT gives no
signal about what to do when a fluent wrong answer is available — and for a
DevOps assistant, a confident-but-wrong `kubectl`/`terraform` incantation is the
expensive failure. The 2026 hiring signal is also explicit: **DPO has displaced
RLHF for alignment in most production settings**, so a post-training story that
stops at SFT is incomplete for an LLM-engineer portfolio.

The instruction dataset was already scaled to 838 pairs partly to feed this.

## Decision

Add a **DPO** stage: `OpsLM-v1 (SFT) → OpsLM-v2 (DPO)`, aligning on a single,
on-theme objective — **prefer the grounded/hedged answer over a confident
hallucination.**

- **Preference pairs** (`opsverse_training.preferences`): for each SFT example,
  `chosen` = the grounded, cited SFT answer; `rejected` = a synthesized
  confident-but-ungrounded answer (invented flags/fields, no hedging). The
  reject generator is the bulk model (`gemini-3.1-flash-lite`), so this costs
  nothing against the 20/day chat quota. `build_preference_pair` refuses empty
  or identical sides (an identical pair gives DPO zero signal).
- **Why DPO, not RLHF/PPO:** DPO needs no separate reward model and no
  on-policy sampling — it optimizes a classification-style loss directly on the
  preference pairs, which is what makes alignment feasible on the same single-T4
  free-tier budget as SFT. (PPO/GRPO would need a reward model and a rollout
  loop the free tier can't sustain.)
- **Training** (`training/scripts/train_opslm_dpo.py`): TRL `DPOTrainer` over the
  4-bit LoRA model via unsloth; `ref_model=None` (the frozen base adapter is the
  reference), `beta=0.1`, 1 epoch, low LR (5e-6). Same T4-safe precision
  selection (`is_bfloat16_supported()` → fp16 on T4) and `processing_class`
  fixes as the SFT script. Resumable; pushes merged 16-bit + GGUF as OpsLM-v2.
- **Format is the tested part:** `PreferencePair.to_trl()` emits TRL's
  conversational `{prompt, chosen, rejected}` shape, and the schema/guards are
  unit-tested — the integration risk (getting the DPO row shape wrong) is
  covered without a GPU, consistent with how SFT's `format_chat` was tested.

## Consequences

- OpsLM gains a real alignment stage, told as a measured before/after: v1 vs v2
  on the existing Phase-4 eval (faithfulness, citation-use) **and** the
  structured-output eval — DPO must not buy groundedness by breaking JSON/tool
  fidelity, and the gate proves it either way.
- The reject-generation and DPO run happen off-machine (Colab), exactly like
  SFT — today's deliverable is the committed, tested pipeline, not the numbers.
  Overclaiming is avoided: until the run happens, OpsLM-v2 does not exist.
- Scope is deliberately narrow (one preference axis, offline pairs). Not built:
  human preference collection, multi-axis rewards, iterative/online DPO, and
  KTO/IPO variants — deferred until the single-axis result justifies them.
