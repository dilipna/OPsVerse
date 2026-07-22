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
  { role: "system", content: "OpsLM v1 · Qwen3-4B (QLoRA) · loaded" },
  {
    role: "assistant",
    content:
      "Ask me about Kubernetes, Docker, Terraform, or MLflow. Answers are grounded and citation-first — ask a real ops question.",
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
    <div className="wrap">
      <div className="topbar">
        <div className="brand">
          <b>OpsLM</b>
          <span>&gt;_ devops language model</span>
        </div>
        <nav className="navlinks">
          <a href="#chat">chat</a>
          <a href="#how">how it works</a>
          <a href="#specs">specs</a>
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
        <div className="tag">fine-tuned · rag-grounded · eval-gated</div>
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
          number — no vibes.
        </p>
        <div className="metarow">
          <span>
            base <b>Qwen3-4B</b>
          </span>
          <span>
            adapter <b>QLoRA r=16</b>
          </span>
          <span>
            corpus <b>1,243 docs / 7,386 chunks</b>
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
        <div className="kicker">// live console</div>
        <div className="term">
          <div className="bar">
            <span className="dot live" />
            <span className="dot" />
            <span className="dot" />
            <span className="path">opslm@dhf1234 ~ /inference</span>
            <span className={"status" + (online ? " online" : "")}>
              {online === null
                ? "connecting"
                : online
                  ? "● model online"
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
            : "Connected to a served OpsLM endpoint. CPU inference is deliberate and free-tier — expect a short pause per reply."}
        </p>
      </section>

      <section id="how">
        <div className="kicker">// how it works</div>
        <div className="grid">
          <div className="cell">
            <h3>01 · retrieve</h3>
            <p>
              Hybrid dense + sparse retrieval (BGE + BM25, RRF fusion) over the
              ingested corpus, reranked and citation-tagged.
            </p>
          </div>
          <div className="cell">
            <h3>02 · generate</h3>
            <p>
              OpsLM answers from the retrieved context. Fine-tuned on 838
              grounded, decontaminated instruction pairs.
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
              A regression gate of 15 thresholds runs in CI. Retrieval, RAG
              quality, and safety are scored, not assumed.
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
            <p>SFT on 838 pairs → DPO preference round (v2) on the same corpus</p>
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
    </div>
  );
}
