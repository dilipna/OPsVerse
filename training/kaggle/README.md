# Running the OpsLM train on Kaggle (headless, API-driven)

Kaggle twin of the Colab notebook: same training script, but the whole run is
driven from a terminal via the Kaggle API — push, walk away, poll. Free tier:
~30 GPU-hours/week, 12h max per session (the run needs ~3–4h on a T4).

## One-time setup (web UI, ~5 min)

1. Kaggle account must be **phone-verified** (Settings → Phone verification) —
   otherwise kernels get no GPU and no internet.
2. Settings → API → **Create New Token** → save the downloaded `kaggle.json`
   to `~/.kaggle/kaggle.json` (Windows: `C:\Users\<you>\.kaggle\kaggle.json`).
3. Open any notebook in the Kaggle editor → Add-ons → **Secrets** → add
   `HF_TOKEN` = a HF token with write access. Attach it to the kernel after the
   first push (Secrets are per-notebook; the first push creates the notebook,
   then attach the secret in the editor and push/re-run).

## Driving the run

```bash
pip install kaggle
cd training/kaggle

# 1. Set the kernel id: edit kernel-metadata.json, replace KAGGLE_USERNAME
#    with the Kaggle username from kaggle.json.

# 2. Push = upload + start a headless "Run All":
kaggle kernels push -p .

# 3. Poll (states: running / complete / error):
kaggle kernels status <kaggle-username>/opslm-qlora-train

# 4. Fetch the log when done:
kaggle kernels output <kaggle-username>/opslm-qlora-train -p ./out
```

If the session dies mid-run: set `RESUME = True` in the notebook's first cell
and push again — the script resumes from the last Hub checkpoint (pushed every
50 steps).

## Gotchas

- The **first** push runs before the `HF_TOKEN` secret is attached and will
  fail fast in cell 1 — that's expected. Attach the secret in the web editor
  (Add-ons → Secrets → attach to this notebook), then push again.
- `enable_gpu` in `kernel-metadata.json` requests the default GPU (T4 x2);
  the notebook pins training to one GPU via `CUDA_VISIBLE_DEVICES=0`.
- Output artifacts land on the HF Hub (`<hf-user>/OpsLM-v1`), not in Kaggle's
  output dir — the log is the only thing worth downloading.
