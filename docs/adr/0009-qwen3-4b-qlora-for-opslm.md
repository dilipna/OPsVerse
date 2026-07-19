# ADR-0009: Qwen3-4B + QLoRA for OpsLM

**Status:** accepted (2026-07-18) — training pipeline committed; first run pending

## Context

Phase 5 fine-tunes a domain model ("OpsLM") on synthetic DevOps/MLOps
instructions. The hard constraint is **free GPU only** (Colab/Kaggle T4,
16 GB), and the training must be **resumable** across Colab session limits.
Choices needed: base model, adaptation method, precision.

## Decision

**Base model: Qwen3-4B** (`unsloth/Qwen3-4B-Base`).
- Apache-2.0 (publishable to HF Hub without license friction).
- 4B is the quality/VRAM sweet spot: strong on technical/code text, and in
  4-bit it leaves enough T4 headroom for activations at seq-len 2048.
- Larger (7–8B) 4-bit runs are feasible on T4 but leave little margin and
  push run time past the free-session window; 1.5B trades away too much
  domain quality. 4B is the defensible middle.

**Adaptation: QLoRA** (4-bit NF4 base + LoRA adapters).
- LoRA r=16, alpha=16 on attention + MLP projections
  (q/k/v/o/gate/up/down) — ~0.5% of parameters trained.
- 4-bit base weights (NF4) via Unsloth keep a 4B model + optimizer state
  inside 16 GB; `adamw_8bit` keeps optimizer memory down further.
- Full fine-tuning and 16-bit LoRA are both out of budget on a single T4;
  QLoRA is the only method that fits with margin.

**Tooling: Unsloth + TRL SFTTrainer.**
- Unsloth ~2× throughput / lower VRAM vs stock PEFT on T4 — the difference
  between a run that finishes in a free session and one that doesn't.
- TRL SFTTrainer is the standard, and its `hub_strategy="checkpoint"` pushes
  every checkpoint to the Hub, giving free-session resumability
  (`--resume` picks up the latest).

## Consequences

- A killed Colab session resumes from the last Hub checkpoint instead of
  restarting — essential on free tiers.
- Output is a merged 16-bit model (servable) plus a GGUF Q4_K_M
  (Ollama/llama.cpp, and the HF Spaces demo + inference lab consume it).
- The model must clear the **pre-existing** Phase-4 eval gate to make any
  "better than base" claim — the harness came first by design.
- DPO (OpsLM-v2) is a follow-on once SFT (v1) has honest before/after
  numbers; deferred, not dropped.
- Revisit base-model choice only if the domain eval shows 4B saturating the
  data (unlikely at pilot dataset size) or if a newer small Apache-2.0 base
  clearly beats Qwen3-4B on technical benchmarks.
