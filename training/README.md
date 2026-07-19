# OpsLM Fine-Tuning (Phase 5)

OpsLM is a QLoRA fine-tune of **Qwen3-4B** on an instruction dataset
synthesized from the OpsVerse corpus (Kubernetes, Docker, Terraform, MLflow).
The training runs on **free Colab/Kaggle T4 GPUs — never on the dev machine**
(no local CUDA). This directory holds the reproducible, resumable pipeline;
the trained model is published to the HF Hub.

## Status (honest)

| Stage | State |
|---|---|
| Synthetic instruction generation | ✅ done — `libs/training/generate_instructions.py`, DVC-versioned |
| Decontamination vs frozen eval sets | ✅ enforced — `ContaminationGuard`, per ADR-0007's sibling policy |
| SFT dataset prep (train/val split) | ✅ runnable — `scripts/prepare_sft.py`, verified locally |
| QLoRA training script | ✅ written, pinned, resumable — `scripts/train_opslm_qlora.py` |
| **Actual training run on Colab** | ⏳ **not yet run** — needs a Colab session + HF token |
| Before/after eval (base vs OpsLM) | ⏳ blocked on the training run |
| GGUF export + HF model card | ⏳ blocked on the training run |

Nothing here claims a trained model exists. The eval harness (Phase 4) is the
gate the trained model must pass, and it existed first — that ordering is the
point.

## Pipeline

```
corpus (Postgres/DVC)
   └─ libs/training/generate_instructions.py   # qa / explain / diagnosis, decontaminated
        └─ data/instructions/instructions-v1.jsonl  (+ manifest, DVC-pushed)
             └─ training/scripts/prepare_sft.py      # re-guard, split -> chat/messages JSONL
                  └─ data/sft/{train,val}.jsonl
                       └─ training/scripts/train_opslm_qlora.py   # Colab T4, QLoRA, resumable
                            └─ huggingface.co/<you>/OpsLM-v1  (merged 16-bit + GGUF Q4_K_M)
                                 └─ eval: opsverse_evals.rag_suite / retrieval ablation
                                          base Qwen3-4B vs OpsLM-v1  (before/after report)
```

## Running the training (Colab)

1. Push `data/sft/` to an HF dataset repo (or upload the two JSONL files).
2. New Colab notebook, T4 runtime:
   ```python
   !pip install "unsloth==2025.*" "trl>=0.12,<0.20" "datasets>=3" "huggingface_hub"
   !git clone https://github.com/dilipna/OPsVerse && cd OPsVerse
   !HF_TOKEN=hf_xxx python training/scripts/train_opslm_qlora.py \
       --data-repo <you>/opsverse-sft --push-repo <you>/OpsLM-v1
   ```
3. If the session dies, re-run with `--resume` — checkpoints are pushed to the
   Hub every `--save-steps`.

## Why these choices

- **Qwen3-4B** (Apache-2.0): quality/VRAM sweet spot, strong on technical
  text, fits a T4 in 4-bit. See ADR-0009.
- **QLoRA** (4-bit NF4 base + LoRA r=16 on attn+MLP): ~0.5% of params trained,
  keeps a 4B run under ~3–4h on one T4. See ADR-0009.
- **Dataset is small on purpose right now** (pilot). Scaling to the planned
  ~8–15k pairs is more `generate_instructions --n` batches (flash-lite quota),
  then re-run `prepare_sft`.

## Next (after the first run)

- Before/after report: base Qwen3-4B vs OpsLM-v1 on the domain eval + the
  Phase-4 regression suite (must not regress general behavior).
- Tool-calling fidelity eval — does SFT degrade JSON/function-call output?
- OpsLM-v2 via DPO (chosen = curated, rejected = base/degraded outputs).
- Route ops-domain chat to OpsLM through the gateway (one line in the model
  chain — the gateway already wraps it, ADR-0008).
