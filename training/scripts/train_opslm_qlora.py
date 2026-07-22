"""OpsLM QLoRA fine-tune of Qwen3-4B on the OpsVerse SFT dataset (Colab T4).

This runs OFF this machine — Colab/Kaggle free GPU, never locally (no CUDA
here). It is committed as the reproducible training artifact: pinned, single
entry point, resumable, checkpointing to the HF Hub so a killed Colab session
resumes instead of restarting.

Colab quickstart (see training/README.md for the full walkthrough):
    !pip install "unsloth==2025.*" "trl>=0.12,<0.20" "datasets>=3"
    !python train_opslm_qlora.py --data-repo you/opsverse-sft \
        --push-repo you/OpsLM-v1 --hf-token $HF_TOKEN

Design choices (see docs/adr — ADR for LoRA/QLoRA is written alongside P5):
- Qwen3-4B base: Apache-2.0, strong technical-domain quality, fits T4 in 4-bit.
- QLoRA (4-bit NF4) + LoRA r=16 on attention+MLP proj: ~0.5% params trained,
  keeps a 4B run under ~3-4h on a single T4.
- Resumable: checkpoints every `--save-steps` to output_dir AND push to Hub;
  `--resume` picks up the latest Hub checkpoint.
"""

import argparse
import os
from typing import Any


def format_chat(tokenizer: Any, batch: dict[str, list]) -> dict[str, list[str]]:
    """Render each example's chat `messages` to a single training string.

    Module-level (not a closure) so it is unit-testable without a GPU: the
    only integration risk in this script is that the SFT `messages` shape
    feeds `apply_chat_template` correctly, and that is exactly what this does.
    """
    return {
        "text": [
            tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            for messages in batch["messages"]
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", default="unsloth/Qwen3-4B-Base")
    parser.add_argument(
        "--data-repo", required=True, help="HF dataset repo or local dir with train/val.jsonl"
    )
    parser.add_argument(
        "--push-repo", required=True, help="HF model repo for OpsLM, e.g. you/OpsLM-v1"
    )
    parser.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"))
    parser.add_argument("--max-seq-len", type=int, default=2048)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--output-dir", default="opslm-qlora-ckpt")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    # Imports are inside main so `--help` works on a machine without CUDA/unsloth.
    # unsloth must be imported before trl/transformers/peft so its optimizations
    # patch those libraries (it warns and can OOM otherwise) — hence the
    # non-alphabetical, isort-suppressed order.
    from unsloth import FastLanguageModel, is_bfloat16_supported  # noqa: I001
    from unsloth.chat_templates import get_chat_template
    from datasets import load_dataset
    from trl import SFTConfig, SFTTrainer

    # T4 (Turing) has no bf16; only Ampere+ does. Pick precision from the GPU so
    # the same script trains on a free T4 (fp16) and an A100 (bf16) unchanged.
    use_bf16 = is_bfloat16_supported()

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_len,
        load_in_4bit=True,  # QLoRA: 4-bit NF4 base
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.0,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
    tokenizer = get_chat_template(tokenizer, chat_template="qwen-3")

    def load_split(split: str):
        if os.path.isdir(args.data_repo):
            files = os.path.join(args.data_repo, f"{split}.jsonl")
            return load_dataset("json", data_files=files)["train"]
        return load_dataset(args.data_repo, split=split)

    def _fmt(batch: dict[str, list]) -> dict[str, list[str]]:
        return format_chat(tokenizer, batch)

    train = load_split("train").map(_fmt, batched=True)
    val = load_split("val").map(_fmt, batched=True)

    trainer = SFTTrainer(
        model=model,
        # TRL >=0.13 renamed `tokenizer` -> `processing_class` (transformers 4.46+).
        processing_class=tokenizer,
        train_dataset=train,
        eval_dataset=val,
        args=SFTConfig(
            dataset_text_field="text",
            max_seq_length=args.max_seq_len,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            warmup_ratio=0.05,
            lr_scheduler_type="cosine",
            logging_steps=10,
            eval_strategy="steps",
            eval_steps=args.save_steps,
            save_steps=args.save_steps,
            output_dir=args.output_dir,
            bf16=use_bf16,
            fp16=not use_bf16,
            push_to_hub=True,
            hub_model_id=args.push_repo,
            hub_token=args.hf_token,
            hub_strategy="checkpoint",  # push every checkpoint -> resumable
            optim="adamw_8bit",
            seed=3407,
        ),
    )
    trainer.train(resume_from_checkpoint=args.resume)

    # Merge LoRA into 16-bit and push the servable model + a GGUF Q4_K_M for
    # Ollama/llama.cpp users (the inference-lab and HF Spaces demo consume it).
    model.push_to_hub_merged(
        args.push_repo, tokenizer, save_method="merged_16bit", token=args.hf_token
    )
    model.push_to_hub_gguf(
        args.push_repo, tokenizer, quantization_method="q4_k_m", token=args.hf_token
    )
    print(f"OpsLM pushed to https://huggingface.co/{args.push_repo}")


if __name__ == "__main__":
    main()
