import type { Metadata } from "next";
import security from "../../public/security.json";

export const metadata: Metadata = {
  title: "RYPE — Security",
  description:
    "Threat model, measured detector robustness and the controls that treat user input, retrieved documents, model output and fetched URLs as untrusted.",
};

const REPO = "https://github.com/dilipna/OPsVerse/blob/main";

const BOUNDARIES = [
  {
    name: "Retrieved documents",
    control:
      "Scanned on normalized text at ingest. A document carrying instructions aimed at the assistant is quarantined and contributes no passages. Credentials are redacted before storage.",
  },
  {
    name: "Model output",
    control:
      "Rewritten before display: no images, links only to source and official-documentation hosts, credentials redacted. Any rewrite raises an operator alert.",
  },
  {
    name: "Fetched URLs",
    control:
      "Public addresses only, on every redirect hop. The connection goes to the exact address that was checked, so a changed DNS answer cannot redirect it.",
  },
  {
    name: "User input",
    control:
      "Size-limited and rate-limited per client. Injection signals are recorded for review; no tool can change state, so the assistant has nothing harmful to be talked into.",
  },
];

const pct = (value: number) => `${Math.round(value * 100)}%`;

type Rate = { k: number; n: number; rate: number; ci95: number[] };
type AgentSummary = {
  model: string;
  max_steps: number;
  scenarios: number;
  attacks: number;
  heldout_accuracy: Rate;
  development_accuracy: Rate;
  attacked_accuracy: Rate;
  attack_success: Rate;
  history: { correct: number; finished: number; runs: number } | null;
};
// Null until docs/reports/agent-v1-summary.json is committed.
const agent = (security as { agent: AgentSummary | null }).agent;

export default function SecurityPage() {
  const { robustness, redteam, threats } = security;
  return (
    <div className="navigator study">
      <a className="skip" href="#robustness">
        Skip to measurements
      </a>
      <header className="site-header">
        <a className="wordmark" href="/">
          RY<span>PE</span>
          <small> / security</small>
        </a>
        <nav aria-label="Main navigation">
          <a href="/troubleshoot">Troubleshoot</a>
          <a href="/study">Evaluation</a>
          <a href="/engineering">Engineering</a>
          <a href="https://github.com/dilipna/OPsVerse">GitHub ↗</a>
        </nav>
      </header>
      <main>
        <section className="intro">
          <p className="eyebrow">SECURITY / THREAT MODEL &amp; MEASURED CONTROLS</p>
          <h1>
            Every control has a test.
            <br />
            <span>Every gap is listed.</span>
          </h1>
          <p className="intro-copy">
            RYPE treats four things as untrusted: what users type, every retrieved document,
            everything the model writes, and every URL it is asked to fetch. Each control below maps
            to a threat, a test that can be rerun, and an honest status.
          </p>
        </section>

        <section className="evidence">
          <h2>Trust boundaries</h2>
          <div className="study-grid two-up">
            {BOUNDARIES.map((b) => (
              <div className="study-card" key={b.name}>
                <b>{b.name}</b>
                <p>{b.control}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="robustness" className="evidence">
          <h2>Does detection survive simple rewrites?</h2>
          <p className="intake-note">
            The original red-team set ({redteam.attacks} attacks, {redteam.benign} benign DevOps
            sentences that share vocabulary with attacks) scored {pct(redteam.tpr)} recall and{" "}
            {pct(redteam.specificity)} specificity. That set was written alongside the detector, so
            each case was rewritten with character-level changes a reader would not notice and
            scored again.
          </p>
          <div className="study-table-wrap">
            <table className="study-table">
              <caption>
                Injection detector recall and specificity per transform, {robustness.cases} cases
              </caption>
              <thead>
                <tr>
                  <th scope="col">Transform</th>
                  <th scope="col">Recall, raw regexes</th>
                  <th scope="col">Recall, normalized</th>
                  <th scope="col">Specificity, normalized</th>
                </tr>
              </thead>
              <tbody>
                {robustness.rows.map((row) => (
                  <tr key={row.transform}>
                    <th scope="row">{row.transform.replace("_", " ")}</th>
                    <td>{pct(row.raw_tpr)}</td>
                    <td>{pct(row.normalized_tpr)}</td>
                    <td>{pct(row.normalized_specificity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="intake-note">
            Normalizing text before matching (folding look-alike letters and full-width forms,
            removing invisible characters, joining split lines) restores recall without new false
            positives. The transforms and the fix were written together, so this guards against
            known tricks regressing. Rewording and translation change the words themselves; no
            pattern matcher catches those, which is why a learned classifier is the next layer.{" "}
            <a href={`${REPO}/docs/reports/security-robustness-v1.md`}>Full report ↗</a>
          </p>
        </section>

        <section className="evidence">
          <h2>And on data it was never tuned on?</h2>
          <p className="intake-note">
            Both layers scored on an external, openly licensed dataset (deepset/prompt-injections,
            pinned to a commit and file hash). Recall with 95% Wilson intervals; the second layer is{" "}
            <code>{security.classifier_model}</code> reading each text as data inside a random
            boundary.
          </p>
          <div className="study-table-wrap">
            <table className="study-table">
              <caption>Injection recall on external data</caption>
              <thead>
                <tr>
                  <th scope="col">Split</th>
                  <th scope="col">Attacks</th>
                  <th scope="col">Regex only</th>
                  <th scope="col">Regex + LLM layer</th>
                  <th scope="col">False-positive rate, layered</th>
                </tr>
              </thead>
              <tbody>
                {security.external.map((row) => (
                  <tr key={row.name}>
                    <th scope="row">{row.name.replace("deepset-", "")}</th>
                    <td>{row.attacks}</td>
                    <td>
                      {pct(row.tpr)} ({pct(row.tpr_ci95[0])}–{pct(row.tpr_ci95[1])})
                    </td>
                    <td>
                      {pct(row.layered_tpr)} ({pct(row.layered_tpr_ci95[0])}–
                      {pct(row.layered_tpr_ci95[1])})
                    </td>
                    <td>
                      {pct(row.layered_fpr)} ({pct(row.layered_fpr_ci95[0])}–
                      {pct(row.layered_fpr_ci95[1])})
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="intake-note">
            Perfect on its own test set, the regex layer catches under one attack in ten on someone
            else&apos;s. Adding the LLM layer lifts recall to roughly half or more with no added
            false alarms (exact McNemar tests in the report), so it now runs at ingest when
            configured, failing closed. Roughly four in ten attacks still pass both layers, which is
            why output handling, least privilege and monitoring stay in place behind them.{" "}
            <a href={`${REPO}/docs/reports/security-classifier-v1.md`}>Full report ↗</a>
          </p>
        </section>

        {agent && (
          <section className="evidence">
            <h2>An agent that can be attacked through its tools</h2>
            <p className="intake-note">
              A read-only Kubernetes investigator ({agent.model}) works through {agent.scenarios}{" "}
              frozen fault scenarios with at most {agent.max_steps} tool calls. Every command passes
              a policy check before it runs, tool output is fenced as untrusted data, and a secret
              canary in its prompt makes leaks measurable. Each scenario is then rerun with one of{" "}
              {agent.attacks} existing red-team strings planted in the pod logs it reads.
            </p>
            <div className="study-table-wrap">
              <table className="study-table">
                <caption>Agent diagnosis and attack results, 95% Wilson intervals</caption>
                <thead>
                  <tr>
                    <th scope="col">Measure</th>
                    <th scope="col">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["Accuracy, held-out scenarios", agent.heldout_accuracy],
                    ["Accuracy, development scenarios", agent.development_accuracy],
                    ["Accuracy with an attack in the logs", agent.attacked_accuracy],
                    ["Attack success (canary leak or guarded output)", agent.attack_success],
                  ].map(([label, r]) => {
                    const row = r as { k: number; n: number; rate: number; ci95: number[] };
                    return (
                      <tr key={label as string}>
                        <th scope="row">{label as string}</th>
                        <td>
                          {row.k}/{row.n} ({pct(row.ci95[0])}–{pct(row.ci95[1])})
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {agent.history && (
              <p className="intake-note">
                The first version got {agent.history.correct}/{agent.history.runs} right: it never
                knew when to stop, and its policy refused harmless reads. The fixes were general,
                and the held-out scenarios were written before them and never used for debugging.{" "}
                <a href={`${REPO}/docs/reports/agent-v1.md`}>Full report ↗</a>
              </p>
            )}
          </section>
        )}

        <section className="evidence">
          <h2>Threat model</h2>
          <div className="study-table-wrap">
            <table className="study-table">
              <caption>
                {threats.length} threats mapped to the OWASP Top 10 for LLM Applications (2025)
              </caption>
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Threat</th>
                  <th scope="col">OWASP</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {threats.map((t) => (
                  <tr key={t.id}>
                    <th scope="row">{t.id}</th>
                    <td>{t.threat}</td>
                    <td>{t.owasp}</td>
                    <td>{t.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="intake-note">
            Controls, rerunnable evidence and open items for each row are in the{" "}
            <a href={`${REPO}/docs/security/threat-model.md`}>threat model ↗</a>. The browser
            workspace on this site needs no server-side model; the API controls run in the research
            stack in the repository.
          </p>
        </section>
      </main>
    </div>
  );
}
