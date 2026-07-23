---
title: OpsLM Inference
emoji: "🔴"
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# OpsLM inference Space (llama.cpp)

> **NOTE (2026-07):** Hugging Face now requires a **PRO plan** for Docker *and*
> Gradio Spaces — only Static Spaces are free. So this Space is no longer a
> free path. For an always-on **$0** endpoint, use `../oracle-opslm/` (Oracle
> Cloud Always Free ARM VM). This folder is kept because the `app.py` server is
> reusable on any host with Docker/Python.

---


Serves the committed OpsLM GGUF (`Q4_K_M`) with llama.cpp behind an
OpenAI-compatible `/v1/chat/completions`, so the Vercel demo site can call the
real fine-tune. Free HF Space CPU (2 vCPU / 16 GB) — inference is slow but real
and always-on; the model downloads from `dhf1234/OpsLM-v1` on first request.

## Deploy (~3 min)

1. huggingface.co → **New Space** → **Docker** (blank) → name it e.g. `opslm`.
2. Upload the three files in this folder (`Dockerfile`, `app.py`,
   `requirements.txt`) plus this `README.md` to the Space repo, or push with git:
   ```bash
   git clone https://huggingface.co/spaces/<user>/opslm
   cp infra/hf-space-opslm/* <clone>/ && cd <clone> && git add . && git commit -m init && git push
   ```
3. The Space builds and boots on port 7860. Test:
   ```bash
   curl https://<user>-opslm.hf.space/health
   ```
4. In the Vercel project, set `OPSLM_ENDPOINT=https://<user>-opslm.hf.space/v1`
   and redeploy. The site's console pill flips to `● model online`.

## Notes / knobs (Space → Settings → Variables)

- `OPSLM_REPO` (default `dhf1234/OpsLM-v1`) and `OPSLM_GGUF`
  (default `qwen3-4b-base.Q4_K_M.gguf`) — point at OpsLM-v2 once DPO runs.
- `OPSLM_THREADS` (default 2), `OPSLM_CTX` (default 2048).
- First request is slow (model download + load); subsequent ones are warm.
- The Space sleeps after inactivity on the free tier and wakes on the next
  request (a cold wake adds a few seconds) — fine for a demo, and $0.
