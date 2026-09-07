# OpsVerse AI — STATUS (last updated 2026-09-07, HEAD `21da208`+)

> **This file is a status record, not a task list.** Persistent memory:
> `~/.claude/projects/c--Users-Dilip-OneDrive-Pictures-ftrag/memory/`

## Current state

**Everything is pushed, CI is green, working tree is clean.** `origin/main` == local
`HEAD` at `f2945a9`. **280 tests · 22 ADRs · 14 reports · ruff + format + pyright clean.**

**The user has (or just had) a major conference demo they consider career-critical** —
treat any mention of "the demo" as high-stakes. If a new session starts and the demo
date is unclear, ask rather than assume it already happened or hasn't.

Live: [ops-verse.vercel.app](https://ops-verse.vercel.app) (verified 200) — serves the
[measured benchmark dashboard](https://ops-verse.vercel.app/dashboard.html) (verified
200) and links to the GitHub repo. Chat is in **labelled demo mode**, not calling the
fine-tune. Model published at `dhf1234/OpsLM-v1` on HF.

## What shipped 2026-09-01→03 (the RAG-testing depth pass)

The throughline, worth repeating to the user verbatim if they ask "what's the story":
**four separate pieces of work each overturned an assumption — a prior conclusion, a
shipped default, an intuitive fix, a decision never questioned — and published the
overturn with a significance test rather than an eyeballed number.**

1. **Metric-independence audit** (ADR-0018) — implemented `precision@k`/`recall@k`/
   contextual-precision, then proved three are algebraic restatements of `hit@k`/`mrr@k`
   on the existing single-gold-label eval sets (1e-12 across 300 cases). Declined to
   report them until the labels earned it. → `docs/reports/retrieval-metrics-audit-v1.md`
2. **Golden set v1** (ADR-0019) — pooled TREC-style relevance, graded 0–3,
   position-randomised, 1,914 judgements, 100% seed recovery. Added bootstrap CIs +
   paired permutation significance testing project-wide. Found `hit@10` **saturated**
   (0.97–0.99, no discriminating power) and **downgraded two of the project's own
   earlier claims to statistical ties** (sparse vs hybrid; reranker vs no-rerank).
   → `docs/reports/retrieval-golden-v1.md`
3. **Contextual recall** (generator-side) — 412 independently-written atomic claims,
   scored per retrieval mode. **Reproduced the retrieval-side "dense is worse" finding
   from a completely different measurement** (p=0.048). → `docs/reports/generator-golden-v1.md`
4. **Chunking ablation** (ADR-0020) — re-parsed real source docs (GitHub tarballs in
   MinIO, matched by SHA-256) under 3 chunk-size configs, scored at document granularity.
   **The shipped default (350 tok) is not the best-measured option** — smaller chunks
   (150 tok) win on nDCG (+0.044, p=0.0002). Scope: 100/594 candidate docs (time-boxed).
   → `docs/reports/chunking-ablation-v1.md`
5. **Multi-turn eval** (ADR-0020) — the first conversational eval set. Found production
   retrieval ignores conversation history, then floor-tested the obvious fix
   (concatenation) and **found it doesn't help** (trends worse, not significant) —
   published the null result with the test, didn't just assume the fix works.
   → `docs/reports/multiturn-v1.md`
6. **Embedding-model ablation** (ADR-0021) — an 18× size ladder (384→1024-dim).
   **No significant difference** between the incumbent and a model 3.1× smaller
   (p=0.94 nDCG). The incumbent's size isn't earning its cost on this corpus.
   `bge-large` dropped from the run (too slow given the day's time budget) — a
   documented next step, not silently omitted. → `docs/reports/embedding-ablation-v1.md`

**Resume bullets already drafted**: `docs/resume-bullets.md` — three role variants
(LLM/AI Engineer, LLM-Eval/Applied ML, MLOps), grounded only in committed numbers, with
an explicit "what NOT to claim yet" section. Read this before writing any resume/LinkedIn
copy — don't re-derive from scratch.

## What shipped 2026-09-04 (judge validation — the eval-rigor gap)

Driven by a research pass on what top-tier AI labs screen for (plan:
`~/.claude/plans/read-continue-session-md-at-the-glowing-gosling.md`; see the
`opsverse-job-application-goal` memory). Of four recurring hiring signals, three were
already covered with real evidence; the gaps were **judge validation**, **error
analysis / failure taxonomy**, and **an agent tool-use harness**. Item 1 is now done.

7. **Judge validation** (ADR-0022) — the golden set's labels audited against a blinded
   second rater on a stratified sample (192 drawn, 190 scored). **Found the judge is
   systematically strict**: signed error **+0.327 [+0.226, +0.430]**, precision 0.968
   against **TPR 0.571**, quadratic κ 0.717. So absolute `recall@k`/`nDCG_graded@k` on
   the golden set read *low* — but the bias is equal across all four modes
   (+0.317–+0.412, overlapping CIs), so **the ADR-0019/0020/0021 comparisons stand**.
   The levels move; the deltas don't. → `docs/reports/judge-validation-v1.md`

   **⚠️ The reference rater was `claude-opus-5`, NOT a human.** The user asked for this
   explicitly (no time before a demo) and the report says so in its title, a warning
   block, and its limits; `--rater-kind model` switches that language on. Model-model
   agreement is biased *upward*. **Never describe this as human validation** in a
   resume, README, or interview — say "second-model cross-check; human labels are the
   open item." A ~40-item human subset is the agreed follow-up (option C).

   New: `libs/evals/.../judge_validation.py` (`sample` / `score` subcommands, offline —
   no Qdrant, no API), `stats.bootstrap_statistic_ci` (stratified bootstrap for table
   ratios like κ/TPR, which are not means of per-item scores). The generated labeling
   page is gitignored; tasks + key + labels are committed. 2 tasks (`t0001`, `t0002`)
   excluded for broken blinding and named in the report.

## What shipped 2026-09-06/07 (human labels + error analysis)

8. **Human judge labels** (ADR-0022 addendum, `judge-validation-v2.md`) — the user
   labelled **40** tasks themselves, a stratified subset of the v1 sample reusing the
   same task ids so all three pairwise agreements fall out of one session.
   **The direction replicated, the magnitude did not.** TPR 0.556 (human) vs 0.472
   (model) on the same tasks — the judge misses about half the relevant material under
   either rater. But the human's calibration offset is **+0.226 [−0.076, +0.571]**,
   spanning zero, against the model's +0.505 on those same tasks. Head to head the human
   grades **0.279 [−0.539, −0.018] lower** than the model: **the model rater was the
   lenient one**, and its leniency inflated v1's +0.327. The intervals overlap, so v1 is
   *un-confirmed*, not refuted. Quote the offset as a direction with an open magnitude.
9. **Failure taxonomy** (`failure-taxonomy-v1.md`) — the error-analysis gap, closed.
   An over-inclusive signal flagged 28/100 queries; reading all 28, **23 are not defects
   (82%)** and only 5 are (5% of queries). Largest category: queries answered at rank 1–3
   that `recall@10` marks down anyway, because the corpus offers many acceptable answers.
   **This is the concrete mechanism behind the low absolute recall** — separate from, and
   additional to, judge strictness. Changed the fix list: nothing on it targets `recall@10`.
   **Coded by claude-opus-5, a language model, not the user** — stated in the report, its
   limits and the ledger row. Re-coding ~10 cases by hand is the cheapest way to test it.
10. **Claim ledger** (`docs/evidence.md` + `docs/overturns.html`, generated by
    `opsverse_evals.overturns`) — the falsification record on one screen, now **8 claims**.
    Every number plucked from committed `*-summary.json`; a test perturbs sources and
    asserts the prose moves, so it cannot go stale. `overturns.html` is also copied to
    `opslm-demo/public/` and will serve at `/overturns.html` once pushed.
11. **Demo runbook re-weighted** — step 3 went from 90s of July-era material to 3.5 min
    carrying the overturn arc, with three tellable stories and a scripted answer to
    "isn't finding eight mistakes bad?". Added a 6-minute cut (steps 1–3, all `[no stack]`).
12. **Resume bullets** brought to HEAD, with an explicit ban on writing "validated against
    human labels" for the model cross-check.

## Project state: COMPLETE as a portfolio artifact (2026-09-07)

**Everything from the researched job-application plan is done except the agent/tool-use
harness, which was deliberately NOT built.** The reasoning, so a future session does not
silently reverse it: it is multi-day and Gemini-quota-constrained (a *daily* budget, not
compressible), and a rushed version would be a second `infra/oracle-oplsm/` — scaffolded,
never run, sitting in the honest-gaps list. That would subtract from a project whose
distinguishing feature is that it does not publish unmeasured claims. **Do not build it in
a hurry to "finish" something. It is either a properly paced multi-day piece or nothing.**

The user was advised, and agreed, that the binding constraint has moved from the repo to
(a) actually applying and (b) interview-loop rehearsal. Weigh any future "let's add X"
against that before starting.

**Public surface, all live:**
- Repo: https://github.com/dilipna/OPsVerse
- Claim ledger: https://ops-verse.vercel.app/overturns.html (8 claims, verified serving)
- Benchmark dashboard: https://ops-verse.vercel.app/dashboard.html
- Three published posts on https://dilipna.hashnode.dev (linked from the README)
- A fourth post is **drafted but unpublished**: `docs/blog/04-who-grades-the-grader.md`
  (judge validation + human labels + error analysis). Every number in it was verified
  against the committed summaries. Publishing it is the user's call.

## What is genuinely left (all optional; none blocks anything)

1. **Before/after eval (base Qwen3-4B vs OpsLM-v1)** — the one real content gap.
   **User explicitly deprioritized this** (2026-09-02: "let's skip the cloud part") after
   repeated pushback in earlier sessions. Do not re-suggest it unless the user brings it
   up first. If they do: `docs/opslm-before-after-aws-runbook.md` is a corrected,
   copy-paste-ready procedure for an EC2 Spot `g4dn.xlarge` (same T4 as the benchmark,
   ~$0.50 total, ~2–3h). The older `docs/opslm-before-after-runbook.md` (Colab path) is
   superseded by it for the serving half but still holds for methodology (§1: why the
   comparison must be base-vs-OpsLM, never OpsLM-vs-Gemini).
2. **`bge-large` in the embedding ablation** — dropped for time (see ADR-0021). Rerun
   with `uv run python -m opsverse_evals.embedding_ablation --models "BAAI/bge-large-en-v1.5" --subset 1500`
   — it will read the cached small/base results and only compute the new model.
3. **Chunking ablation at full scope** — currently 100/594 candidate documents
   (time-boxed). Rerun with `--subset 594` (or higher) for the full pool; expect ~4–6×
   the wall-clock time of today's run.
4. **Quantization→quality frontier** — deliberately empty, blocked on (1).
5. **Live demo chat** — `infra/oracle-opslm/` scaffolded, Oracle ARM VM not provisioned.
   Oracle free A1 often returns "Out of host capacity". `setup.sh` ships the bearer token
   over plain HTTP; a Cloudflare Tunnel would fix that for free. **Low priority** — the
   dashboard link is the stronger demo artifact and needs no serving infrastructure.
6. **DPO → OpsLM-v2** — pipeline ready (ADR-0015), run pending.
7. **More human judge labels.** 40 done (see above) — enough for a direction, not a
   magnitude. Another ~60 would likely settle whether the offset is real. Redraw with
   `judge_validation subset --n 60 --seed <new>` and score with `--rater-kind human`.
   A *second independent* human would upgrade this from judge-vs-rater agreement to real
   inter-annotator agreement, which is the stronger artifact.
8. **Second coder for the failure taxonomy.** The codes are one language model's reading.
   Re-coding even 10 of the 28 by hand tests the headline claim (82% not defects) far
   more cheaply than re-running retrieval.
9. **Agent / tool-use harness + trajectory eval** — item 3 of the plan, THE LAST MAJOR
   GAP, not started. Multi-day and quota-constrained, so start it early and pace it
   across days. Reuses the 5 existing MCP tools; NOT a framework adoption.

## Lessons from 2026-09-02/03 (read before running long background jobs)

- **This session's background bash processes died to session restarts repeatedly**
  (4+ times) during long CPU-bound embedding/chunking sweeps. Fix applied:
  `embedding_ablation.py` and `chunking_ablation.py` now checkpoint each model/config
  result to `docs/reports/.embedding-ablation-cache/` and `.chunking-ablation-cache/`
  (gitignored) and skip completed work on resume. **Always re-run the same command after
  a crash** rather than starting over — it picks up where it left off.
- **Do not delete/touch Qdrant collections based on empty or stale-looking background
  task output alone.** Twice this session, a job assumed dead (0-byte output file, no
  recent log lines) was actually alive and slow — deleting its collection out from under
  it caused the exact crash being investigated. Empty output is very often just the
  `grep`/pipe buffering issue (grep block-buffers when piped to a file, not a terminal),
  **not** proof of death. Check real process activity first: `Get-Process python |
  Select Id,CPU,StartTime` (PowerShell) — if CPU time is climbing across two checks a
  few minutes apart, it's alive. Only touch shared state (Qdrant collections, etc.) once
  you've confirmed nothing is using it.
- **Running two CPU-heavy embedding jobs concurrently roughly triples wall-clock time**
  via contention (verified: a config that should take ~10 min took ~38 min running
  alongside another fastembed process). Prefer running heavy CPU ablations sequentially,
  not in parallel, even though it's tempting to background both.
- Docker Desktop shut down between turns multiple times this session too — same as
  every prior session's gotcha #1 below. Always verify `docker info` before assuming the
  stack is up.

## Hard constraints (user-confirmed, do not revisit)

| Thing | Decision |
|---|---|
| GPU | Free tiers only — training happens OFF this machine (Colab T4; Kaggle blocked, see below) |
| LLM APIs | Free tiers only (Gemini; Groq key never provided) |
| Base model | Qwen3-4B → "OpsLM" — **TRAINED + published at `dhf1234/OpsLM-v1`** |
| Deployment | Docker Compose local; K8s manifests as docs; **demo site live on Vercel**; always-on model serving = Oracle Cloud Free Tier (HF Spaces now PRO-only) |
| Order | Evaluation platform BEFORE fine-tuning (done — this ordering is a talking point) |
| Cloud/GPU spend | User has repeatedly deprioritized GPU-dependent work (Colab sessions burned 2026-07-24/25; AWS before/after skipped 2026-09-02). Don't push it — offer once, respect "skip" |

## User working rules

- Everything stays inside this folder. **Ask before**: starting/stopping apps (incl.
  Docker Desktop), deleting non-generated things, acting outside this folder.
- Local commits at each milestone WITHOUT asking; quick "pushing now" heads-up before
  each `git push`.
- The user wants simple, numbered, non-technical steps for anything they must do
  themselves (AWS/Vercel/cloud consoles). Give screen-by-screen when they're in an
  unfamiliar UI.
- **Push back once, clearly, on scope creep** ("every new technology", padding the eval
  suite with degenerate metrics) — the project's actual strength is depth + honesty on
  one coherent RAG-eval story, not breadth. State the concern in a sentence, then do
  what's actually asked if they restate it.
- The permission classifier may block destructive-looking DB scripts even on
  regenerable data — use AskUserQuestion when that happens.

## Environment gotchas (WILL bite you)

1. **Docker Desktop shuts down between sessions.** ASK the user first, then poll
   `docker info` in a loop until it responds, then `docker compose -f
   infra/compose/docker-compose.yml --profile full up -d --wait`.
2. **Ports**: API **8100** (8000 taken by another local app), web 3000, Langfuse **3002**.
3. **Gemini quotas**: `gemini-3.5-flash` = **20 req/DAY** (chat only). ALL bulk/eval jobs
   use `gemini-3.1-flash-lite` — never point bulk work at 3.5. Bulk quota is shared
   across ALL eval-generation scripts (golden_set, golden_answers, generator_eval,
   multiturn_evalset, metrics_audit) — running several back-to-back same-day can hit
   rate limits; back off 40s+ on 429s (already built into every generator script).
4. **Pins**: `litellm >=1.60,<1.92`; `langfuse >=2.50,<3.0`. fastembed cache:
   `FASTEMBED_CACHE_PATH`.
5. **PowerShell**: no heredocs; write commit messages to a scratchpad file +
   `git commit -F`, or use the Bash tool with `git commit -m` heredoc.
   `$env:PYTHONUTF8='1'` for any Python printing LLM output. cwd persists between tool
   calls in each tool, but background-job cwd changes don't propagate back.
6. `git push` prints its banner to stderr — PowerShell shows red "NativeCommandError"
   but `old..new main -> main` = success.
7. **CI runs BOTH `ruff check` AND `ruff format --check`.** Always run
   `uv run ruff format --check .` before committing — lint-clean is not format-clean.
8. **fastembed dense-embedding throughput is the bottleneck**, not sparse (measured:
   `bge-small` ~8 chunks/s uncontended, `bge-base` ~2.6/s, `bge-large` ~0.7/s — an
   18× model-size range maps to roughly the same ratio in throughput). Size any new
   embedding-heavy script's scope around `bge-base`'s rate, and expect `bge-large` to
   need a genuinely long window (hours for the full 7,383-chunk corpus).
9. **`uv run python -c "..."` uses the project's pinned 3.12; bare `python -c` on this
   machine hits a system 3.10** that's missing `datetime.UTC` and other newer stdlib —
   always use `uv run python`, never bare `python`, for anything importing project code.
10. Long background jobs are resumable by design; on session start check
    `*.partial.jsonl` and `docs/reports/.{embedding,chunking}-ablation-cache/` before
    assuming lost work. `uv run pytest` is safe for the live DB. pyright scope excludes
    training/+notebooks.
11. **Vercel:** repo root is a Python monorepo — a Vercel project MUST set Root
    Directory = `opslm-demo` or it tries to build Python and fails.

## How to bring the local stack up

```bash
docker compose -f infra/compose/docker-compose.yml --profile full up -d --wait   # ASK before Docker Desktop; `full` = +Langfuse
uv sync --all-packages
(cd apps/api && uv run alembic upgrade head)              # no-op if already at head
$env:OPSVERSE_LANGFUSE_HOST='http://localhost:3002'; uv run uvicorn opsverse_api.main:app --port 8100   # background
uv run arq opsverse_api.worker.WorkerSettings             # background
(cd apps/web && npm run dev)                              # :3000 (cwd persists — cd back!)
curl.exe -s http://localhost:8100/health/ready            # expect 4x ok (curl.exe, not bare curl, in PowerShell)
uv run python -m opsverse_evals.regression                # expect 15/15 PASS
```

## Repo map (quick)

```
apps/api          FastAPI: routers/{health,ingest,search,chat,costs,evals}, worker, stream_ingest, alembic
apps/web          Next.js internal UI: / (chat), /evals, /costs   (localhost only)
apps/mcp-server   MCP stdio server, 5 tools + Claude Desktop/Cursor README
libs/core         settings, llm.py, gateway.py (cache/budget), tracing.py, streaming.py, object_store
libs/ingestion    parsers, chunking.py (TARGET/MAX/OVERLAP_TOKENS module constants), quality.py, pipeline (ingest_bytes)
libs/rag          embeddings, store, rerank, retriever, chat.py (stream_chat: retrieval_query = query, no history)
libs/evals        metrics(+graded/stats), golden_set/golden_answers/golden_eval, generator_eval,
                  chunking_ablation, embedding_ablation, multiturn_evalset/multiturn_eval,
                  metrics_audit, rag_suite, regression, structured_eval, judge, stats.py (bootstrap/permutation)
libs/security     injection.py, redact.py, evaluate.py
libs/training     schemas, quality, generate_instructions, preferences.py (DPO), generate_preferences.py
training/         scripts/{prepare_sft,train_opslm_qlora,train_opslm_dpo}.py, notebooks/, kaggle/ (unusable)
benchmarks/       harness.py + techniques/{speculative,constrained,frontier}.py + tests
opslm-demo/       Next.js Vercel demo site (LIVE: ops-verse.vercel.app + /dashboard.html); app/api/chat = edge proxy
infra/oracle-opslm    always-on free serving: setup.sh + Caddy + README (not provisioned)
infra/compose     core + `full` profile (langfuse)   infra/k8s   documented manifests
docs/adr          0001..0021        docs/reports   11 live reports        docs/blog  3 posts
docs/resume-bullets.md               3 role-targeted variants, grounded in committed numbers
docs/opslm-before-after-aws-runbook.md   corrected AWS Spot T4 procedure (prepared, not executed, deprioritized)
data/             corpus.dvc + instructions.dvc (content in MinIO); data/sft/{train,val}.jsonl committed to git
evalsets/         retrieval-v1/v2/v3, retrieval-golden-v1, golden-answers-v1, multiturn-v1, structured-output-v1, security-redteam-v1
```

## Session-start checklist

1. **Read this file's top block.** Check whether the conference demo has already
   happened — ask if unclear rather than assuming.
2. `git status` / `git log -1` — should be clean at `f2945a9` or later. If behind
   `origin/main`, something diverged; investigate before assuming continuity.
3. If touching local eval/RAG code: bring the stack up (ask before Docker), verify
   `/health/ready` (4× ok) + `regression` 15/15.
4. `uv run ruff check .` **and** `uv run ruff format --check .` **and**
   `uv run pyright` before every commit. `uv run pytest -q` should show 215+ passed.
5. Commit per milestone without asking; quick "pushing now" heads-up before each push.
6. Before running a long CPU-bound eval script, check the "Lessons from 2026-09-02/03"
   section above — don't repeat the crash-and-delete-collections mistake.
