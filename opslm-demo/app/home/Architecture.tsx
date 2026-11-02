"use client";

import { useState } from "react";

const BLOB = "https://github.com/dilipna/OPsVerse/blob/main";

type Node = {
  id: string;
  title: string;
  kind: "untrusted" | "control" | "core";
  threats: string[];
  control: string;
  evidence: { label: string; href: string };
};

// Two paths through the system. Each control names the threats it answers in
// docs/security/threat-model.md and the test or report that backs it.
const LANES: { name: string; nodes: Node[] }[] = [
  {
    name: "Ingest",
    nodes: [
      {
        id: "upload",
        title: "Uploaded files & URLs",
        kind: "untrusted",
        threats: ["T-06", "T-07", "T-13"],
        control:
          "Admin key required (fails closed outside dev). URLs pass an SSRF guard that resolves once and connects to the checked public IP, so DNS rebinding has no second lookup. Filenames reduced to a safe basename.",
        evidence: {
          label: "test_security_controls.py",
          href: `${BLOB}/apps/api/tests/test_security_controls.py`,
        },
      },
      {
        id: "scan",
        title: "Normalize + injection scan",
        kind: "control",
        threats: ["T-01"],
        control:
          "Text is normalized (NFKC, invisible characters, look-alike letters, split lines) before the regex scan. Chunks the regexes pass go to an LLM classifier inside a random boundary; any classifier error fails closed.",
        evidence: {
          label: "security-classifier-v1 report",
          href: `${BLOB}/docs/reports/security-classifier-v1.md`,
        },
      },
      {
        id: "redact",
        title: "Credential redaction",
        kind: "control",
        threats: ["T-04"],
        control:
          "16 credential formats removed before storage and embedding, on model output and on traces. Documentation placeholders like ${PASSWORD} are kept.",
        evidence: {
          label: "test_security.py",
          href: `${BLOB}/libs/security/tests/test_security.py`,
        },
      },
      {
        id: "index",
        title: "Hybrid index",
        kind: "core",
        threats: ["T-09", "T-12"],
        control:
          "BM25 + BGE dense retrieval with rank fusion. Embedding model files are SHA-256 pinned; a changed artifact refuses to load.",
        evidence: {
          label: "model_integrity.py",
          href: `${BLOB}/libs/rag/src/rype_rag/model_integrity.py`,
        },
      },
    ],
  },
  {
    name: "Answer",
    nodes: [
      {
        id: "user",
        title: "User question",
        kind: "untrusted",
        threats: ["T-02", "T-05", "T-10"],
        control:
          "Per-client rate limits shared across replicas through Redis, size limits, and a daily spend kill switch. Direct-injection attempts are flagged and logged; the chat path has no tools to abuse.",
        evidence: { label: "ratelimit.py", href: `${BLOB}/apps/api/src/rype_api/ratelimit.py` },
      },
      {
        id: "model",
        title: "Grounded generation",
        kind: "core",
        threats: ["T-11"],
        control:
          "Abstains when retrieval is empty or weak. Numbered citations, and every quoted claim is verified verbatim against its cited passage.",
        evidence: {
          label: "generator-golden-v1 report",
          href: `${BLOB}/docs/reports/generator-golden-v1.md`,
        },
      },
      {
        id: "guard",
        title: "Streaming output guard",
        kind: "control",
        threats: ["T-03", "T-04"],
        control:
          "Rewrites the token stream: images removed, links only to source and official documentation hosts, non-http schemes dropped, credentials redacted. Every rewrite raises an operator alert.",
        evidence: {
          label: "output_guard.py",
          href: `${BLOB}/libs/security/src/rype_security/output_guard.py`,
        },
      },
    ],
  },
  {
    name: "Agent",
    nodes: [
      {
        id: "logs",
        title: "Pod logs & events",
        kind: "untrusted",
        threats: ["T-01"],
        control:
          "Attacker-writable. Every tool result is fenced in a per-run random boundary the content cannot forge, and a canary in the system prompt measures exfiltration.",
        evidence: { label: "loop.py", href: `${BLOB}/libs/agent/src/rype_agent/loop.py` },
      },
      {
        id: "policy",
        title: "Command policy",
        kind: "control",
        threats: ["T-08"],
        control:
          "Every kubectl call is parsed and checked in code before it runs: read-only verbs, an allowlist of resource kinds and flags, no shell syntax. Secrets, exec and port-forward are refused with a reason.",
        evidence: { label: "policy.py", href: `${BLOB}/libs/agent/src/rype_agent/policy.py` },
      },
      {
        id: "finish",
        title: "Checked diagnosis",
        kind: "core",
        threats: ["T-08", "T-10"],
        control:
          "Hard tool-call budget with a forced finish. The root cause must be a defined label, evidence quotes must exist in tool output, and suggested commands are re-checked and never executed.",
        evidence: { label: "agent-v1 report", href: `${BLOB}/docs/reports/agent-v1.md` },
      },
    ],
  },
];

const ALL = LANES.flatMap((l) => l.nodes);

export default function Architecture({ titles }: { titles: Record<string, string> }) {
  const [active, setActive] = useState("scan");
  const node = ALL.find((n) => n.id === active) ?? ALL[0];
  return (
    <div className="arch">
      <div className="arch-lanes">
        {LANES.map((lane) => (
          <div key={lane.name} className="arch-lane">
            <span className="arch-lane-name">{lane.name}</span>
            <div className="arch-flow">
              {lane.nodes.map((n, i) => (
                <div key={n.id} className="arch-step">
                  {i > 0 && <span className="arch-arrow" aria-hidden="true" />}
                  <button
                    type="button"
                    className={`arch-node ${n.kind}`}
                    aria-pressed={n.id === active}
                    onClick={() => setActive(n.id)}
                    onMouseEnter={() => setActive(n.id)}
                  >
                    <small>
                      {n.kind === "untrusted"
                        ? "UNTRUSTED"
                        : n.kind === "control"
                          ? "CONTROL"
                          : "CORE"}
                    </small>
                    {n.title}
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="arch-detail" aria-live="polite">
        <p className="eyebrow">{node.kind === "untrusted" ? "TRUST BOUNDARY" : "WHAT RUNS HERE"}</p>
        <h3>{node.title}</h3>
        <p>{node.control}</p>
        <ul>
          {node.threats.map((t) => (
            <li key={t}>
              <b>{t}</b> {titles[t] ?? ""}
            </li>
          ))}
        </ul>
        <a href={node.evidence.href}>Evidence: {node.evidence.label} ↗</a>
      </div>
    </div>
  );
}
