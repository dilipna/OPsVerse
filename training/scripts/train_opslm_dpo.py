"""DPO preference-alignment of OpsLM -> OpsLM-v2 (ADR-0015).

Runs OFF this machine (Colab/Kaggle free T4). Starts from the SFT model
(dhf1234/OpsLM-v1), applies Direct Preference Optimization over grounded-vs-
ungrounded pairs, and pushes the merged result as OpsLM-v2. DPO needs no reward
model and no on-policy sampling, so it fits the same single-T4 budget as SFT.

Data: a JSONL of TRL conversational DPO rows, i.e. each line has
`prompt` / `chosen` / `rejected` as message lists (produced by
opsverse_training.preferences.PreferencePair.to_trl). See training/README.md.

Colab quickstart:
    !pip install "unsloth==2025.*" "trl>=0.12,<0.20" "datasets>=3"
    !python train_opslm_dpo.py --base-model dhf1234/OpsLM-v1 \
        --data-repo data/dpo --push-repo dhf1234/OpsLM-v2 --hf-token $HF_TOKEN
"""

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", default="dhf1234/OpsLM-v1")
    parser.add_argument(
        "--data-repo", required=True, help="HF dataset repo or local dir with train/val.jsonl"
    )
    parser.add_argument("--push-repo", required=True, help="HF repo, e.g. you/OpsLM-v2")
    parser.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"))
    parser.add_argument("--max-seq-len", type=int, default=2048)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--epochs", type=float, default=1.0)  # DPO needs far fewer than SFT
    parser.add_argument("--lr", type=float, default=5e-6)  # DPO is sensitive; keep LR low
    parser.add_argument("--beta", type=float, default=0.1)  # KL strength vs the reference
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--output-dir", default="opslm-dpo-ckpt")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    # unsloth before trl/transformers so its patches apply (see SFT script).
    from unsloth import FastLanguageModel, is_bfloat16_supported  # noqa: I001
    from datasets import load_dataset
    from trl import DPOConfig, DPOTrainer

    use_bf16 = is_bfloat16_supported()  # T4 -> fp16; Ampere+ -> bf16

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_len,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
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

    def load_split(split: str):
        if os.path.isdir(args.data_repo):
            files = os.path.join(args.data_repo, f"{split}.jsonl")
            return load_dataset("json", data_files=files)["train"]
        return load_dataset(args.data_repo, split=split)

    train = load_split("train")
    val = load_split("val")

    trainer = DPOTrainer(
        model=model,
        ref_model=None,  # unsloth/PEFT: the frozen base LoRA acts as the reference
        processing_class=tokenizer,  # TRL >=0.13 renamed tokenizer -> processing_class
        train_dataset=train,
        eval_dataset=val,
        args=DPOConfig(
            beta=args.beta,
            max_length=args.max_seq_len,
            max_prompt_length=args.max_seq_len // 2,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            warmup_ratio=0.1,
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
            hub_strategy="checkpoint",
            optim="adamw_8bit",
            seed=3407,
        ),
    )
    trainer.train(resume_from_checkpoint=args.resume)

    model.push_to_hub_merged(
        args.push_repo, tokenizer, save_method="merged_16bit", token=args.hf_token
    )
    model.push_to_hub_gguf(
        args.push_repo, tokenizer, quantization_method="q4_k_m", token=args.hf_token
    )
    print(f"OpsLM-v2 (DPO) pushed to https://huggingface.co/{args.push_repo}")


if __name__ == "__main__":
    main()
