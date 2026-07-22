# OpsLM — demo site

A standalone Next.js site for the OpsLM DevOps model: a hero, a live terminal
chat console, and the spec sheet. Deploys to Vercel; the chat calls a served
OpsLM endpoint when one is configured, and returns clearly-labelled demo
answers otherwise (so the deployed link is always functional).

Terminal/brutalist aesthetic — red on black, monospace, hand-tuned CSS (no UI
framework). Self-contained: only `next` + `react`.

## Local

```bash
cd opslm-demo
npm install
npm run dev        # http://localhost:3000
```

## Deploy to Vercel (~2 min)

1. Push this repo to GitHub (already done).
2. On vercel.com → **Add New… → Project** → import the GitHub repo.
3. Set **Root Directory** to `opslm-demo` (important — the repo root is a Python
   monorepo; Vercel must build this subfolder).
4. Framework preset auto-detects **Next.js**. Deploy. You get a public URL.

### Connecting the live model (optional)

The site works in demo mode with zero config. To make the chat call the real
fine-tuned OpsLM, set these **Environment Variables** in the Vercel project
(Settings → Environment Variables), then redeploy:

| Var | Value |
|---|---|
| `OPSLM_ENDPOINT` | OpenAI-compatible base, e.g. `https://<user>-opslm.hf.space/v1` |
| `OPSLM_MODEL` | model id to request (default `opslm`) |
| `OPSLM_API_KEY` | optional bearer token, if the endpoint requires one |

The endpoint can be a free HF Space serving the GGUF on CPU (see
`../infra/hf-space-opslm/`), a Colab/Kaggle tunnel during a live demo, or any
vLLM/Ollama server. The status pill in the console header shows
`● model online` vs `○ demo mode`.

## Design notes

- No rounded-card SaaS template, no gradients-to-purple, no emoji — deliberately
  a developer-built terminal look (faint CRT grid + scanlines, blinking cursor).
- `app/api/chat/route.ts` is an edge function that proxies to the model and
  falls back to canned, on-topic answers if the backend is unset/unreachable.
