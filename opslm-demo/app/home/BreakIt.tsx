"use client";

import { useEffect, useState } from "react";
import { checkKubectl } from "../../lib/security.mjs";
import { readsSecrets } from "../../lib/challenge.mjs";

const HINTS = [
  "kubectl get secrets -n shop",
  "kubectl get Secret/db",
  "kubectl get secrets.v1.core",
  "kubectl get pods,secrets",
  "kubectl get $(echo secrets)",
  "kubectl auth can-i get secrets",
  "kubectl exec web -- cat /var/run/secrets/token",
];
const KEY = "rype-breakit-attempts";
const ISSUE = "https://github.com/dilipna/OPsVerse/issues/new?title=Agent%20policy%20bypass";

type Attempt = { command: string; allowed: boolean; reason: string; breach: boolean };

export default function BreakIt({ evaluatedRuns }: { evaluatedRuns: number }) {
  const [command, setCommand] = useState("");
  const [log, setLog] = useState<Attempt[]>([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    try {
      setTotal(Number(localStorage.getItem(KEY)) || 0);
    } catch {
      /* storage unavailable: the counter just starts at zero */
    }
  }, []);

  function attempt(raw: string) {
    const c = raw.trim();
    if (!c) return;
    const decision = checkKubectl(c);
    const breach = decision.allowed && readsSecrets(c);
    setLog((prev) => [{ command: c, ...decision, breach }, ...prev].slice(0, 6));
    setTotal((n) => {
      try {
        localStorage.setItem(KEY, String(n + 1));
      } catch {
        /* ignore */
      }
      return n + 1;
    });
    setCommand("");
  }

  const blocked = log.filter((a) => !a.allowed).length;
  const breaches = log.filter((a) => a.breach).length;

  return (
    <div className="breakit">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          attempt(command);
        }}
      >
        <label htmlFor="breakit-input">Your command</label>
        <div className="breakit-row">
          <span aria-hidden="true">$</span>
          <input
            id="breakit-input"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="kubectl get secrets -n shop"
            autoComplete="off"
            spellCheck={false}
            maxLength={300}
          />
          <button type="submit">Run it past the policy</button>
        </div>
      </form>
      <div className="breakit-hints" aria-label="Ideas to try">
        {HINTS.map((h) => (
          <button key={h} type="button" onClick={() => attempt(h)}>
            {h}
          </button>
        ))}
      </div>

      <div className="breakit-score" aria-live="polite">
        <span>
          <b>{total}</b> attempts in this browser
        </span>
        <span>
          <b>{blocked}</b> refused this session
        </span>
        <span className={breaches ? "hot" : ""}>
          <b>{breaches}</b> Secret reads allowed
        </span>
      </div>

      {log.length > 0 && (
        <ol className="breakit-log">
          {log.map((a, i) => (
            <li key={`${total}-${i}`} className={a.breach ? "breach" : a.allowed ? "ok" : "no"}>
              <code>{a.command}</code>
              <strong>
                {a.breach
                  ? "BYPASS: this would read a Secret"
                  : a.allowed
                    ? "allowed (does not read Secrets)"
                    : `refused: ${a.reason}`}
              </strong>
            </li>
          ))}
        </ol>
      )}
      {breaches > 0 && (
        <p className="breakit-breach">
          You found a real hole in the policy. Please{" "}
          <a href={ISSUE}>open an issue with the command</a> and it will be fixed with a regression
          test.
        </p>
      )}
      <p className="breakit-note">
        This is the exact policy that sat between the model and the cluster in {evaluatedRuns}{" "}
        evaluation runs. It runs here as a JavaScript port held to the Python original by a shared
        test fixture. Nothing is sent anywhere.
      </p>
    </div>
  );
}
