import type { Metadata } from "next";
import security from "../../public/security.json";

export const metadata: Metadata = {
  title: "OpsVerse — Security",
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

export default function SecurityPage() {
  const { robustness, redteam, threats } = security;
  return (
    <div className="navigator study">
      <a className="skip" href="#robustness">
        Skip to measurements
      </a>
      <header className="site-header">
        <a className="wordmark" href="/">
          OPS<span>VERSE</span>
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
            OpsVerse treats four things as untrusted: what users type, every retrieved document,
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
