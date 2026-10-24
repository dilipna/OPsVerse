"use client";

import { useEffect, useRef, useState } from "react";

type Msg = { role: "user" | "assistant" | "system"; content: string };

const SUGGESTIONS = [
  "Why is my pod stuck in CrashLoopBackOff?",
  "Difference between a readiness and liveness probe?",
  "Write a Dockerfile HEALTHCHECK for a Flask app on :8000",
  "What does `terraform plan` do vs `apply`?",
];

const BOOT: Msg[] = [
  { role: "system", content: "OpsLM v1 · Qwen3-4B (QLoRA) · sample console" },
  {
    role: "assistant",
    content:
      "Ask me about Kubernetes, Docker, Terraform, or MLflow. This console shows sample responses unless a model endpoint is configured. The endpoint proxy does not perform retrieval.",
  },
];

export default function Page() {
  const [msgs, setMsgs] = useState<Msg[]>(BOOT);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [msgs]);

  useEffect(() => {
    fetch("/api/chat")
      .then((r) => r.json())
      .then((d) => setOnline(Boolean(d?.live)))
      .catch(() => setOnline(false));
  }, []);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const next = [...msgs, { role: "user" as const, content: q }];
    setMsgs(next);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          messages: next.filter((m) => m.role !== "system"),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Request failed");
      setMsgs((m) => [
        ...m,
        { role: "assistant", content: data.reply ?? "…" },
        ...(data.note
          ? [{ role: "system" as const, content: data.note }]
          : []),
      ]);
    } catch {
      setMsgs((m) => [
        ...m,
        { role: "system", content: "! request failed — endpoint unreachable" },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wrap"><p><a href="/">← Incident workspace</a> · Sample model console; not retrieval-grounded</p>
      <div className="topbar">
        <div className="brand">
          <b>OpsLM · sample console</b>
          <span>&gt;_ devops language model</span>
        </div>
        <nav className="navlinks">
          <a href="#chat">chat</a>
          <a href="#how">how it works</a>
          <a href="#specs">specs</a>
          <a href="/dashboard.html" target="_blank" rel="noreferrer">
            benchmarks ↗
          </a>
          <a
            href="https://github.com/dilipna/OPsVerse"
            target="_blank"
            rel="noreferrer"
          >
            code ↗
          </a>
          <a
            href="https://huggingface.co/dhf1234/OpsLM-v1"
            target="_blank"
            rel="noreferrer"
          >
            model ↗
          </a>
        </nav>
      </div>

      <header className="hero">
          <div className="tag">sample replies · optional model proxy · no retrieval in this console</div>
        <h1>
          A DevOps model
          <br />
          that shows its <span className="glow">receipts</span>
          <span className="cursor" />
        </h1>
        <p className="lede">
          OpsLM is Qwen3-4B fine-tuned (QLoRA) on a decontaminated DevOps/MLOps
          corpus, wrapped in a hybrid-retrieval stack and gated by an
          eval-first platform. Every claim behind it traces to a measured
          number in the historical research reports. This console is a separate
          sample experience; a matched SFT quality improvement is not established.
        </p>
        <p className="lede">
          <a href="/dashboard.html" target="_blank" rel="noreferrer">
            <b>→ See the measured inference benchmark</b>
          </a>{" "}
          — vLLM vs Ollama on a real Tesla T4 under a 1→16 concurrency sweep:
          13.4× throughput scaling, a prefix-cache control run, and the raw
          JSON committed next to every chart.
        </p>
        <div className="metarow">
          <span>
            base <b>Qwen3-4B</b>
          </span>
          <span>
            adapter <b>QLoRA r=16</b>
          </span>
          <span>
            corpus <b>historical research snapshot</b>
          </span>
          <span>
            retrieval <b>hybrid + rerank</b>
          </span>
          <span>
            eval gate <b>15 thresholds</b>
          </span>
        </div>
      </header>

      <section id="chat">
        <div className="kicker">// sample model console</div>
        <div className="term">
          <div className="bar">
            <span className="dot live" />
            <span className="dot" />
            <span className="dot" />
            <span className="path">opslm@dhf1234 ~ /inference</span>
            <span className={"status" + (online ? " online" : "")}>
              {online === null
                ? "checking configuration"
                : online
                  ? "● endpoint configured (availability unverified)"
                  : "○ demo mode"}
            </span>
          </div>
          <div className="log" ref={logRef}>
            {msgs.map((m, i) => (
              <p key={i} className={"line " + m.role}>
                {m.role === "system" ? (
                  <span className="body">— {m.content}</span>
                ) : (
                  <>
                    <span className="who">
                      {m.role === "user" ? "you@local:~$ " : "opslm:~$ "}
                    </span>
                    <span className="body">{m.content}</span>
                  </>
                )}
              </p>
            ))}
            {busy && (
              <p className="line assistant">
                <span className="who">opslm:~$ </span>
                <span className="body">
                  thinking<span className="cursor" />
                </span>
              </p>
            )}
          </div>
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <span className="prompt">&gt;</span>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="type an ops question and hit enter…"
              autoComplete="off"
              spellCheck={false}
            />
            <button type="submit" disabled={busy}>
              {busy ? "···" : "run"}
            </button>
          </form>
        </div>
        <div className="chips">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
        <p className="hint">
          {online === false
            ? "Demo mode: the model backend isn't connected, so replies are canned samples. Wire OPSLM_ENDPOINT to a served OpsLM for live answers."
            : "An endpoint is configured; availability has not been checked. This proxy does not attach retrieved context."}
        </p>
      </section>

      <section id="how">
        <div className="kicker">// how it works</div>
        <div className="grid">
          <div className="cell">
            <h3>01 · retrieve</h3>
            <p>
              The optional local stack uses dense + sparse retrieval (BGE + BM25,
              RRF fusion). This sample proxy does not call that stack.
            </p>
          </div>
          <div className="cell">
            <h3>02 · generate</h3>
            <p>
              The local ChatService can attach context to generation. OpsLM SFT
              used 534 training pairs; this does not establish a task-quality gain.
            </p>
          </div>
          <div className="cell">
            <h3>03 · guard</h3>
            <p>
              Prompt-injection quarantine at ingest and secret redaction — a
              poisoned doc contributes zero chunks.
            </p>
          </div>
          <div className="cell">
            <h3>04 · measure</h3>
            <p>
              CI checks 15 committed-report assertions and two live retrieval
              thresholds. It does not rerun the historical model-quality studies.
            </p>
          </div>
        </div>
      </section>

      <section id="specs">
        <div className="kicker">// spec sheet</div>
        <div className="grid">
          <div className="cell">
            <h3>model</h3>
            <p>Qwen3-4B base · QLoRA (4-bit NF4) · merged 16-bit + GGUF Q4_K_M</p>
          </div>
          <div className="cell">
            <h3>alignment</h3>
            <p>SFT on a 593-pair split (534 train). DPO code exists; a completed DPO run and matched SFT quality gain are not established.</p>
          </div>
          <div className="cell">
            <h3>serving</h3>
            <p>OpenAI-compatible endpoint · Ollama / vLLM / llama.cpp</p>
          </div>
          <div className="cell">
            <h3>inference lab</h3>
            <p>speculative decoding · guided JSON · quant frontier · TPOT</p>
          </div>
        </div>
      </section>

      <footer>
        <span>OpsLM — built as a portfolio system. Depth over breadth.</span>
        <span>
          <a
            href="https://huggingface.co/dhf1234/OpsLM-v1"
            target="_blank"
            rel="noreferrer"
          >
            huggingface/dhf1234/OpsLM-v1
          </a>
        </span>
      </footer>
    </main>
  );
}
