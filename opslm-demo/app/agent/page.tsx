"use client";

import { useState } from "react";
import data from "../../public/agent-replays.json";
import SiteHeader from "../SiteHeader";

const REPO = "https://github.com/dilipna/OPsVerse/blob/main";

type Step = {
  tool: string;
  input: string | null;
  allowed: boolean;
  denial_reason: string | null;
  output: string;
  truncated: boolean;
};
type Replay = {
  id: string;
  heldout: boolean;
  symptom: string;
  truth: string;
  predicted: string | null;
  correct: boolean;
  summary: string;
  evidence: string[];
  forced_finish: boolean;
  canary_leaked: boolean;
  steps: Step[];
};
const replays = data.replays as Replay[];
const labels = data.labels as Record<string, string>;

const TITLES: Record<string, string> = {
  a07: "Missing ConfigMap · solved in 2 calls",
  h01: "Registry authorization · held out · Secrets read refused",
  h04: "Service selector mismatch · held out",
  a10: "Healthy namespace · the miss, shown on purpose",
};

export default function AgentPage() {
  const [selected, setSelected] = useState(replays[0].id);
  const [shown, setShown] = useState(1);
  const replay = replays.find((r) => r.id === selected) ?? replays[0];
  const done = shown > replay.steps.length;

  function pick(id: string) {
    setSelected(id);
    setShown(1);
  }

  return (
    <div className="navigator study">
      <a className="skip" href="#replay">
        Skip to the replay
      </a>
      <SiteHeader section="agent" current="/agent" />
      <main>
        <section className="intro">
          <p className="eyebrow">AGENT / RECORDED INVESTIGATIONS</p>
          <h1>
            Watch it investigate.
            <br />
            <span>Every call, every refusal.</span>
          </h1>
          <p className="intro-copy">
            Real runs of RYPE&apos;s read-only Kubernetes agent ({data.model}) from its evaluation.
            Each command passed a policy check before it ran; outputs are rebuilt from the frozen
            scenario, so this page shows exactly what the agent saw.
          </p>
        </section>

        <section className="evidence" aria-label="Choose a run">
          <div className="examples">
            {replays.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => pick(r.id)}
                aria-pressed={r.id === selected}
              >
                {TITLES[r.id] ?? r.id}
              </button>
            ))}
          </div>
        </section>

        <section id="replay" className="search-panel" aria-live="polite">
          <p className="eyebrow">
            SCENARIO {replay.id.toUpperCase()}
            {replay.heldout ? " · HELD OUT (never used for debugging)" : ""}
          </p>
          <h2>{replay.symptom}</h2>

          <ol className="replay-steps">
            {replay.steps.slice(0, shown).map((step, i) => (
              <li key={i} className={step.allowed ? "replay-step" : "replay-step refused"}>
                <div className="replay-head">
                  <span>
                    {i + 1}. {step.tool}
                  </span>
                  <code>{step.input}</code>
                  <strong>{step.allowed ? "allowed" : `refused: ${step.denial_reason}`}</strong>
                </div>
                {step.allowed && (
                  <pre className="study-code">
                    {step.output}
                    {step.truncated ? "\n…" : ""}
                  </pre>
                )}
              </li>
            ))}
          </ol>

          {!done ? (
            <div className="incident-actions">
              <button type="button" onClick={() => setShown((n) => n + 1)}>
                Next step ({shown} of {replay.steps.length})
              </button>
              <button type="button" onClick={() => setShown(replay.steps.length + 1)}>
                Show all and the answer
              </button>
            </div>
          ) : (
            <div className="replay-answer">
              <p className="eyebrow">
                FINAL ANSWER{replay.forced_finish ? " · BUDGET SPENT, FINISH WAS FORCED" : ""}
              </p>
              <div className="signal-row">
                <strong>{replay.correct ? "Correct" : "Wrong"}</strong>
                <span>
                  predicted <code>{replay.predicted ?? "none"}</code>
                </span>
                <span>
                  truth <code>{replay.truth}</code>
                </span>
                <span>canary leaked: {replay.canary_leaked ? "yes" : "no"}</span>
              </div>
              <p className="intro-copy">{replay.summary}</p>
              {replay.evidence.length > 0 && (
                <p className="intake-note">
                  Evidence quoted:{" "}
                  {replay.evidence.map((e) => (
                    <code key={e}>{e} </code>
                  ))}
                </p>
              )}
              <p className="intake-note">
                {replay.correct
                  ? `Label meaning: ${labels[replay.truth]}.`
                  : "This is the evaluation's clean-pass miss. The agent quoted a real line from its tool output as evidence for a claim that line contradicts; quotes are checked for existence, not support, which the report lists as a known limit."}
              </p>
              <div className="incident-actions">
                <button type="button" onClick={() => setShown(1)}>
                  Replay from the start
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="evidence">
          <h2>How it scored</h2>
          <p className="intake-note">
            16 frozen fault scenarios, then 80 more runs with existing red-team strings planted in
            the pod logs it reads: 6/6 correct on held-out scenarios, 0/80 canary leaks or guarded
            outputs, 5/80 diagnoses derailed by the planted text, and every attempt to read Secrets
            refused. <a href={`${REPO}/docs/reports/agent-v1.md`}>Full report ↗</a> ·{" "}
            <a href={`${REPO}/docs/agent.md`}>Design ↗</a> · <a href="/lab">Try the policy →</a>
          </p>
        </section>
      </main>
    </div>
  );
}
