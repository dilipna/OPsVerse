# Before/after eval on an AWS Spot T4 — copy-paste runbook

> **Status: prepared 2026-09-01, not executed.** This closes the one gap that has no
> honest workaround: *"is OpsLM-v1 actually better than the base model it was fine-tuned
> from?"* Today the answer is "I don't know."
>
> Supersedes the Colab path in [`opslm-before-after-runbook.md`](opslm-before-after-runbook.md)
> for the *serving* half. The methodology section there still applies and is not repeated
> here — **read its §1 before running this**, especially why the comparison must be
> base-vs-OpsLM and never OpsLM-vs-Gemini.

**Why `g4dn.xlarge`:** it carries the *same Tesla T4* used for
[`inference-benchmark-v1`](reports/inference-benchmark-v1.md). Same accelerator means the
before/after numbers sit alongside the existing benchmark with no "different hardware"
caveat. Spot price is roughly **$0.15–0.20/hr**; the whole run is **2–3 hours ≈ $0.50**.

---

## 0. Abort rules — read before starting

| Trigger | Action |
|---|---|
| Spot instance reclaimed mid-run | Results are written per-stage; resume from the last completed stage |
| vLLM install fails twice | Stop. The known-good recipe is pinned below; if it fights you, the AMI drifted |
| Base model serves but OpsLM won't load (or vice versa) | Stop — half a comparison is worse than none |
| Total spend passes $5 | Stop. Something is wrong; this run costs well under $1 |

**Set a billing alarm before you launch.** Console → Billing → Budgets → $5 monthly.

---

## 1. Launch the instance (AWS Console, ~5 min)

1. **EC2 → Instances → Launch instances**
2. **Name:** `opslm-eval`
3. **AMI:** search `Deep Learning OSS Nvidia Driver AMI GPU PyTorch` → pick the newest **Ubuntu 22.04** version.
   *(This ships CUDA + drivers. A bare Ubuntu AMI means installing drivers yourself — don't.)*
4. **Instance type:** `g4dn.xlarge`
5. **Key pair:** create one, download the `.pem`, remember where it saved
6. **Network settings → Edit:**
   - Auto-assign public IP: **Enable**
   - Security group: allow **SSH (22)** from **My IP** only
   - Do **not** open port 8000 — the eval runs on the box, nothing needs to reach vLLM from outside
7. **Configure storage:** change 8 GiB → **100 GiB** gp3.
   *(Two 4B models plus CUDA wheels will not fit in 8 GiB. This is the most common failure.)*
8. **Advanced details → Purchase option → check `Request Spot Instances`** → leave defaults
9. **Launch instance**

## 2. Connect

```bash
chmod 400 /path/to/your-key.pem
ssh -i /path/to/your-key.pem ubuntu@<PUBLIC_IP>
nvidia-smi          # must print: Tesla T4, 15360MiB. If not, stop - wrong AMI.
```

## 3. Install vLLM (the pinned recipe)

```bash
sudo apt-get update -y && sudo apt-get install -y python3-pip git
pip install --upgrade pip
pip install uv
uv pip install --system vllm --torch-backend=auto
python -c "import vllm; print('vllm', vllm.__version__)"
```

If you hit the `libcudart` error this project has seen before:
```bash
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
python -c "import ctypes; ctypes.CDLL('libcudart.so.12')"
```

## 4. Serve the BASE model first

```bash
export HF_TOKEN=<your-hf-read-token>
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-4B-Base \
  --served-model-name base \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.90 \
  --port 8000 &
# wait for "Application startup complete", then:
curl -s localhost:8000/v1/models | python3 -m json.tool
```

## 5. Point the eval at it — **from your laptop, not the VM**

The eval harness is an HTTP client for your local API on `:8100`. The env vars go on the
**uvicorn process**, not on the eval command — see the methodology runbook, this is the
mistake that was already caught once.

Open an SSH tunnel so your laptop can reach vLLM:
```bash
ssh -i key.pem -L 8000:localhost:8000 ubuntu@<PUBLIC_IP>
```

Then locally, restart the API pointed at the tunnel:
```powershell
$env:OPSVERSE_CHAT_MODEL      = 'openai/base'
$env:OPSVERSE_CHAT_API_BASE   = 'http://localhost:8000/v1'
uv run uvicorn opsverse_api.main:app --port 8100
```

Run the suites — **note the `--out`**, a default run overwrites the Gemini baseline and
turns the regression gate red:
```bash
uv run python -m opsverse_evals.rag_suite --n 20 --out docs/reports/opslm-eval/base
uv run python -m opsverse_evals.structured_eval --n 12 --out docs/reports/opslm-eval/base
```

> **Not `generator_eval`.** That module scores whether *retrieval* supplied enough
> context; its result does not change when you swap the chat model, so running it
> here would produce two identical numbers and a false conclusion. The suites that
> actually depend on the served model are `rag_suite` (faithfulness /
> answer-relevance / citation-use) and `structured_eval` (JSON fidelity - the
> "did SFT break tool-use?" check). `--out` takes a **directory**.

## 6. Repeat for OpsLM-v1

On the VM: `Ctrl-C` the base server, then
```bash
python -m vllm.entrypoints.openai.api_server \
  --model dhf1234/OpsLM-v1 \
  --served-model-name opslm \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.90 \
  --port 8000 &
```
Locally, `OPSVERSE_CHAT_MODEL='openai/opslm'`, restart uvicorn, and re-run both suites with
`--out docs/reports/opslm-eval/opslm...`.

## 7. TERMINATE THE INSTANCE

```
EC2 → Instances → select → Instance state → Terminate
```
**Stopping is not enough — the 100 GiB EBS volume keeps billing.** Terminate, then confirm
under EC2 → Volumes that nothing is left.

---

## 8. What you can then claim

With both runs committed, the honest sentence becomes:

> *"OpsLM-v1 scores X on faithfulness and Y on JSON fidelity; the base model it was
> fine-tuned from scores X′ and Y′ — same eval sets, same harness, same T4, and the gap
> clears a paired permutation test at p = Z."*

Run it through the significance machinery rather than eyeballing the gap — `n=20` on
`rag_suite` is small and a few points will not clear the noise floor:

```bash
uv run python -c "
from opsverse_evals.stats import paired_permutation_test
# per-query scores from the two summary JSONs
print(paired_permutation_test(opslm_scores, base_scores))
"
```

**If the fine-tune turns out NOT to be better, that is still a result worth having** — and
this project has published two of those already (ablation v3, ADR-0019). "I measured it and
it didn't help, here's why I think so" is a stronger interview answer than never measuring.

## 9. Then fill the quantization frontier

Both quality scores now exist, so the Pareto frontier that
[`inference-benchmark-v1`](reports/inference-benchmark-v1.md) deliberately left empty can be
generated:

```bash
python benchmarks/report.py --results benchmarks/results \
  --quality fp16=<opslm_score> --quality q4_k_m=<q4_score> \
  --out docs/reports/inference-benchmark-v1.md
```
