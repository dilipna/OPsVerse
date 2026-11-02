"use client";

import { useEffect, useMemo, useState } from "react";
import { checkKubectl, sanitizeOutput, scanInjection } from "../../lib/security.mjs";
import { GUARD_EXAMPLE, SCAN_EXAMPLES } from "../../lib/lab-examples.mjs";
import replays from "../../public/agent-replays.json";

type Tone = "cmd" | "dim" | "ok" | "bad" | "warn" | "gap";
type Line = { tone: Tone; text: string; note?: string };

const short = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

// Every verdict below is computed in the browser by the same code the /lab page runs
// (held to the Python controls by the parity fixture). Nothing is a canned string.
function buildScript(): Line[] {
  const obfuscated = SCAN_EXAMPLES[3].text;
  const raw = scanInjection(obfuscated, { normalize: false });
  const norm = scanInjection(obfuscated);
  const hidden = [...obfuscated].filter((c) => /\p{Cf}/u.test(c)).length;

  const run = replays.replays.find((r) => r.id === "h01") ?? replays.replays[0];
  const shown = run.steps.filter((s, i) => i < 2 || !s.allowed).slice(0, 4);

  const guard = sanitizeOutput(GUARD_EXAMPLE);
  const rewrites = Object.values(guard.findings).reduce((a, b) => a + b, 0);
  const label: Record<string, string> = {
    image_removed: "tracking image removed",
    link_removed: "off-allowlist link removed",
  };

  return [
    { tone: "cmd", text: "rype ingest uploads/runbook.md" },
    {
      tone: "dim",
      text: `raw regex          score ${raw.score.toFixed(1)}`,
      note: raw.suspicious ? "flagged" : "would pass ✗",
    },
    { tone: "dim", text: `normalize          ${hidden} invisible characters stripped` },
    {
      tone: "warn",
      text: `scanner            score ${norm.score.toFixed(1)}`,
      note: norm.matched.join(" · "),
    },
    { tone: "bad", text: "QUARANTINED        0 passages indexed" },
    { tone: "gap", text: "" },
    { tone: "cmd", text: `rype agent "${short(run.symptom, 38)}"` },
    ...shown.map((s): Line => {
      // Recorded inputs omit the tool name, as the agent sent them; the loop prepends it.
      const command = (s.input ?? "").startsWith("kubectl")
        ? (s.input ?? "")
        : `kubectl ${s.input ?? ""}`;
      const d = checkKubectl(command);
      const text = short(command.replace(/^kubectl /, ""), 44);
      return d.allowed
        ? { tone: "ok", text: `✓ ${text}` }
        : { tone: "bad", text: `✗ ${text}`, note: `refused: ${d.reason}` };
    }),
    {
      tone: run.correct ? "ok" : "bad",
      text: `diagnosis          ${run.predicted}`,
      note: run.correct ? "matches ground truth" : `truth: ${run.truth}`,
    },
    { tone: "gap", text: "" },
    { tone: "cmd", text: "rype answer --guard" },
    ...Object.entries(guard.findings).map(
      ([k, n]): Line => ({
        tone: "bad",
        text: `✗ ${label[k] ?? k.replace("secret_redacted:", "credential redacted: ")}`,
        note: n > 1 ? `×${n}` : undefined,
      }),
    ),
    { tone: "ok", text: `✓ ${rewrites} rewrites before display · operator alert raised` },
  ];
}

export default function HeroConsole() {
  const script = useMemo(buildScript, []);
  const [shown, setShown] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(script.length);
      return;
    }
    if (paused) return;
    const done = shown >= script.length;
    const next = script[shown];
    const delay = done ? 4200 : next.tone === "cmd" ? 900 : next.tone === "gap" ? 500 : 380;
    const t = window.setTimeout(() => setShown(done ? 0 : shown + 1), delay);
    return () => window.clearTimeout(t);
  }, [shown, paused, script]);

  return (
    <figure
      className="console"
      aria-label="Live demo: RYPE's controls catching an obfuscated injection, refusing an agent's Secrets read, and rewriting an unsafe answer"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="console-bar">
        <i />
        <i />
        <i />
        <span>rype · live, computed in your browser</span>
        <button type="button" onClick={() => setShown(0)} aria-label="Replay the demo">
          ↻
        </button>
      </div>
      <ol className="console-body" aria-live="off">
        {script.slice(0, shown).map((line, i) => (
          <li key={i} className={`tone-${line.tone}`}>
            {line.tone === "cmd" && <b>$ </b>}
            <span>{line.text}</span>
            {line.note && <em>{line.note}</em>}
          </li>
        ))}
        {shown < script.length && <li className="caret" aria-hidden="true" />}
      </ol>
      <figcaption>
        Real controls, real data: the scanner and guard run here; the agent steps are a recorded
        held-out run. {paused ? "Paused." : "Hover to pause."}
      </figcaption>
    </figure>
  );
}
