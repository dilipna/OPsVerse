"use client";

import { useCallback, useEffect, useState } from "react";

type Step = { target: string; title: string; body: string };

const STEPS: Step[] = [
  {
    target: ".hero",
    title: "What this is",
    body: "A RAG assistant and a tool-using agent, built end to end, then attacked on purpose. The live console is not a video: the real security controls are running in your browser.",
  },
  {
    target: ".proof",
    title: "Results, not adjectives",
    body: "Every number here is generated from a committed evaluation report. CI fails the build if the page and the reports ever disagree.",
  },
  {
    target: ".story",
    title: "The integrity signal",
    body: "A perfect internal score collapsed on a public benchmark. It was reported anyway, then improved with a measured fix. Look for the confidence intervals.",
  },
  {
    target: "#break",
    title: "Hands-on security",
    body: "Try to make the agent read a Kubernetes Secret. This is the same policy that sat between the model and the cluster in every evaluation run.",
  },
  {
    target: "#ask",
    title: "RAG, live",
    body: "Ask anything about how the project was built. Answers are quoted from the repository with citations, and the retriever has its own held-out evaluation.",
  },
  {
    target: "#architecture",
    title: "System design",
    body: "Every trust boundary, the control that answers it, the threat it maps to and the test that proves it. Click any box.",
  },
  {
    target: ".skills",
    title: "Skills, each with a receipt",
    body: "Retrieval, evaluation, agents, security, generation and platform work, each linked to the report that backs it.",
  },
  {
    target: ".cta",
    title: "Take it with you",
    body: "The one-page brief is printable and easy to forward to a hiring manager. Everything else is in the repository.",
  },
];
const STEP_MS = 7000;

export default function Tour() {
  const [step, setStep] = useState<number | null>(null);
  const [playing, setPlaying] = useState(true);
  const [tick, setTick] = useState(0);

  const close = useCallback(() => setStep(null), []);
  const go = useCallback((n: number) => {
    setTick((t) => t + 1);
    setStep(n < 0 ? 0 : n >= STEPS.length ? null : n);
  }, []);

  // Start from the hero button or a shared link: /?tour
  useEffect(() => {
    const start = () => {
      setPlaying(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
      go(0);
    };
    window.addEventListener("rype:tour", start);
    if (new URLSearchParams(window.location.search).has("tour")) start();
    return () => window.removeEventListener("rype:tour", start);
  }, [go]);

  // Spotlight the current target.
  useEffect(() => {
    if (step === null) return;
    const el = document.querySelector<HTMLElement>(STEPS[step].target);
    if (!el) return;
    el.classList.add("tour-target");
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    return () => el.classList.remove("tour-target");
  }, [step]);

  // Auto-advance; restarted by `tick` whenever the visitor moves manually.
  useEffect(() => {
    if (step === null || !playing) return;
    const t = window.setTimeout(() => go(step + 1), STEP_MS);
    return () => window.clearTimeout(t);
  }, [step, playing, tick, go]);

  useEffect(() => {
    if (step === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") go(step + 1);
      if (e.key === "ArrowLeft") go(step - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, go, close]);

  if (step === null) return null;
  const s = STEPS[step];
  return (
    <>
      <div className="tour-shade" onClick={close} aria-hidden="true" />
      <div className="tour-card" role="dialog" aria-label="Guided tour" aria-live="polite">
        <div className="tour-progress" aria-hidden="true">
          {STEPS.map((_, i) => (
            <span key={i} className={i < step ? "done" : i === step ? "now" : ""}>
              {i === step && playing && (
                <i key={`${step}-${tick}`} style={{ animationDuration: `${STEP_MS}ms` }} />
              )}
            </span>
          ))}
        </div>
        <small>
          {step + 1} / {STEPS.length} · 60-SECOND TOUR
        </small>
        <h3>{s.title}</h3>
        <p>{s.body}</p>
        <div className="tour-actions">
          <button type="button" onClick={() => go(step - 1)} disabled={step === 0}>
            ← Back
          </button>
          <button type="button" onClick={() => setPlaying((p) => !p)} aria-pressed={!playing}>
            {playing ? "Pause" : "Play"}
          </button>
          <button type="button" className="primary" onClick={() => go(step + 1)}>
            {step === STEPS.length - 1 ? "Finish" : "Next →"}
          </button>
          <button type="button" className="tour-close" onClick={close} aria-label="End the tour">
            ✕
          </button>
        </div>
      </div>
    </>
  );
}

export function TourButton() {
  return (
    <button
      type="button"
      className="btn primary tour-btn"
      onClick={() => window.dispatchEvent(new Event("rype:tour"))}
    >
      ▶ 60-second tour
    </button>
  );
}
