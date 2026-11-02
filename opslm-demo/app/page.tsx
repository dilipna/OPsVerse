import "./home.css";
import home from "../public/home.json";
import security from "../public/security.json";
import Architecture from "./home/Architecture";
import BreakIt from "./home/BreakIt";
import AskProject from "./home/AskProject";
import HeroConsole from "./home/HeroConsole";
import Tour, { TourButton } from "./home/Tour";
import { Counter, RateBars, Reveal } from "./home/motion";

const REPO = "https://github.com/dilipna/OPsVerse";
const BLOB = `${REPO}/blob/main`;
const pct = (x: number) => `${Math.round(x * 100)}%`;

const { agent, injection, retrieval, generation, judge, threats } = home;
const threatTitles = Object.fromEntries(security.threats.map((t) => [t.id, t.threat]));

const SKILLS = [
  {
    skill: "Retrieval engineering",
    proof: `Hybrid BM25 + dense retrieval lifted hit@10 from ${retrieval.dense_hit10.toFixed(2)} to ${retrieval.hybrid_hit10.toFixed(2)} on ${retrieval.questions} questions over ${retrieval.chunks.toLocaleString("en-US")} chunks. The reranker was rejected: no gain at ${(retrieval.rerank_ms / 1000).toFixed(1)} s per query.`,
    href: `${BLOB}/docs/reports/retrieval-ablation-v3.md`,
    link: "Ablation report",
  },
  {
    skill: "Evaluation you can trust",
    proof: `Confidence intervals on every rate, paired significance tests, and an LLM judge audited against human labels (κ ${judge.kappa}, n=${judge.n}). It finds only ${pct(judge.human_tpr)} of what a human calls relevant, and the report says so.`,
    href: `${BLOB}/docs/reports/judge-validation-v2.md`,
    link: "Judge audit",
  },
  {
    skill: "Tool-using agents",
    proof: `A read-only Kubernetes investigator with a code-enforced command policy, a hard budget and checked answers. ${agent.heldout.k}/${agent.heldout.n} on held-out scenarios never used for debugging.`,
    href: `${BLOB}/docs/reports/agent-v1.md`,
    link: "Agent report",
  },
  {
    skill: "LLM application security",
    proof: `${threats.total} threats mapped to the OWASP LLM Top 10, each with a control, a rerunnable test and an honest status, including the ${threats.accepted} I accept and why.`,
    href: `${BLOB}/docs/security/threat-model.md`,
    link: "Threat model",
  },
  {
    skill: "Grounded generation",
    proof: `Retrieved context supports ${pct(generation.contextual_recall)} of ${generation.claims} reference claims. The model abstains when retrieval is weak, and quoted evidence is verified verbatim.`,
    href: `${BLOB}/docs/reports/generator-golden-v1.md`,
    link: "Generation eval",
  },
  {
    skill: "Supply chain & platform",
    proof:
      "SHA-256-pinned model weights, an SBOM, blocking pip-audit, npm audit and Trivy gates, per-client rate limits, and non-root, read-only Kubernetes manifests.",
    href: `${BLOB}/.github/workflows/ci.yml`,
    link: "CI pipeline",
  },
];

const EXPLORE = [
  {
    href: "/lab",
    tag: "INTERACTIVE",
    title: "Security Lab",
    text: "Run the injection scanner, output guard and command policy on your own input.",
  },
  {
    href: "/agent",
    tag: "REPLAYS",
    title: "Watch the agent",
    text: "Step through recorded investigations, including the refused Secrets read and the one it got wrong.",
  },
  {
    href: "/security",
    tag: "EVIDENCE",
    title: "Threat model & results",
    text: "Every control, its threat, its test, and the gaps listed as gaps.",
  },
  {
    href: "/troubleshoot",
    tag: "PRODUCT",
    title: "Incident workspace",
    text: "Paste Pod events; get a cited investigation brief from official Kubernetes docs.",
  },
  {
    href: "/engineering",
    tag: "CASE STUDY",
    title: "How it was built",
    text: "Ingestion, retrieval, failure handling, provenance and evaluation, end to end.",
  },
];

const WRITING = [
  {
    n: "05",
    title: "My perfect prompt-injection score did not survive a zero-width space",
    href: `${BLOB}/docs/blog/05-my-perfect-injection-score-did-not-survive.md`,
  },
  {
    n: "04",
    title: "Who grades the grader? I audited my LLM judge, and then had to audit the audit",
    href: `${BLOB}/docs/blog/04-who-grades-the-grader.md`,
  },
  {
    n: "02",
    title: "The document is the attack surface: RAG security at ingest, measured like a classifier",
    href: "https://dilipna.hashnode.dev/the-document-is-the-attack-surface-rag-security-at-ingest-measured-like-a-classifier",
  },
  {
    n: "01",
    title:
      "We built the eval harness before the model, and the numbers changed our retrieval design twice",
    href: "https://dilipna.hashnode.dev/evaluation-first-the-rag-harness-that-stopped-me-from-shipping-two-wrong-decisions",
  },
  {
    n: "03",
    title:
      "“Which engine is faster?” is the wrong question: measuring continuous batching on a free T4",
    href: "https://dilipna.hashnode.dev/which-engine-is-faster-is-the-wrong-question-measuring-continuous-batching-on-a-free-t4",
  },
];

export default function Home() {
  const evaluatedRuns = agent.scenarios + agent.attacked_runs;
  return (
    <div className="navigator home">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <a className="wordmark" href="/">
          RY<span>PE</span>
          <small> / Dilip Nallamasa</small>
        </a>
        <nav aria-label="Main navigation">
          <a href="/lab">Lab</a>
          <a href="/agent">Agent</a>
          <a href="/security">Security</a>
          <a href="/troubleshoot">Workspace</a>
          <a href="/engineering">Engineering</a>
          <a href="https://github.com/dilipna/OPsVerse">GitHub ↗</a>
        </nav>
      </header>

      <main id="main">
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">
              <span className="pulse" aria-hidden="true" /> LLM SYSTEMS · AI SECURITY · EVALUATION
            </p>
            <h1>
              I build LLM systems.
              <br />
              <span>Then I attack them.</span>
            </h1>
            <p className="intro-copy">
              RYPE is a retrieval-augmented assistant and a tool-using agent for Kubernetes
              incidents, built end to end and defended like production. Every control maps to a
              threat, has a test, and is measured against attacks I didn&apos;t write.
            </p>
            <div className="hero-actions">
              <TourButton />
              <a className="btn" href="#break">
                Try to break it →
              </a>
              <a className="btn" href="/brief">
                One-page brief
              </a>
              <a className="btn ghost" href={REPO}>
                Source ↗
              </a>
            </div>
            <p className="hero-hint">
              Press <kbd>⌘</kbd> <kbd>K</kbd> anywhere to jump around.
            </p>
          </div>
          <HeroConsole />
        </section>

        <section className="proof" aria-label="Results at a glance">
          <div>
            <strong>
              <Counter value={agent.attack_success} />/{agent.attacked_runs}
            </strong>
            <span>attacked agent runs ended in a leaked canary or an unsafe answer</span>
          </div>
          <div>
            <strong>
              <Counter value={agent.heldout.k} />/{agent.heldout.n}
            </strong>
            <span>held-out incidents diagnosed correctly</span>
          </div>
          <div>
            <strong>
              <Counter value={threats.total} />
            </strong>
            <span>threats modeled against the OWASP LLM Top 10</span>
          </div>
          <div>
            <strong>
              <Counter value={retrieval.chunks} />
            </strong>
            <span>documentation chunks behind hybrid retrieval</span>
          </div>
          <div>
            <strong>
              <Counter value={home.parity_cases} />
            </strong>
            <span>cases holding the browser controls to the Python ones</span>
          </div>
        </section>

        <Reveal className="story">
          <div className="story-copy">
            <p className="eyebrow">THE NUMBER I ALMOST PUBLISHED</p>
            <h2>
              My injection detector scored 100%. Then I tested it on attacks I didn&apos;t write.
            </h2>
            <p>
              A perfect score on my own {injection.internal_attacks} red-team prompts only proved I
              wrote them. On {injection.external_attacks} attacks from a public benchmark, the regex
              layer caught {pct(injection.regex_tpr)}. I put that number on the security page, then
              added an LLM classifier because the measurement said to, and checked it against{" "}
              {injection.external_benign} benign prompts: {pct(injection.layered_fpr)} false
              positives.
            </p>
            <p>
              The same habit found the cheaper bug: one invisible character per word dropped regex
              recall to {pct(injection.zero_width_raw_tpr)}. Normalizing first restored{" "}
              {pct(injection.zero_width_normalized_tpr)}.
            </p>
            <p className="story-links">
              <a href={`${BLOB}/docs/blog/05-my-perfect-injection-score-did-not-survive.md`}>
                Read the write-up ↗
              </a>
              <a href={`${BLOB}/docs/reports/security-classifier-v1.md`}>Benchmark report ↗</a>
            </p>
          </div>
          <div className="story-chart">
            <RateBars
              bars={[
                {
                  label: "My own red-team set",
                  detail: `${injection.internal_attacks} attacks I wrote`,
                  value: injection.internal_tpr,
                  tone: "mid",
                },
                {
                  label: "Public benchmark, regex",
                  detail: `${injection.external_dataset}, ${injection.external_attacks} attacks`,
                  value: injection.regex_tpr,
                  ci: injection.regex_tpr_ci95,
                  tone: "bad",
                },
                {
                  label: "Regex + LLM classifier",
                  detail: `same attacks, ${pct(injection.layered_fpr)} false positives on ${injection.external_benign} benign`,
                  value: injection.layered_tpr,
                  ci: injection.layered_tpr_ci95,
                  tone: "good",
                },
              ]}
            />
            <p className="chart-note">Detection rate · whiskers show the 95% Wilson interval</p>
          </div>
        </Reveal>

        <section id="break" className="challenge">
          <Reveal>
            <p className="eyebrow">CHALLENGE</p>
            <h2>Make the agent read a Kubernetes Secret.</h2>
            <p className="intro-copy">
              The agent can only touch the cluster through one function: a command policy checked in
              code before anything runs. Type any <code>kubectl</code> command. If it reads a
              Secret, you win.
            </p>
            <BreakIt evaluatedRuns={evaluatedRuns} />
          </Reveal>
        </section>

        <Reveal className="section" id="ask">
          <p className="eyebrow">ASK THE PROJECT</p>
          <h2>A RAG system that answers questions about itself.</h2>
          <p className="intro-copy">
            Interviewer questions welcome. Retrieval runs over the repository&apos;s own README,
            design records, threat model, evaluation reports and write-ups, in your browser, with a
            citation for every passage and its own held-out evaluation.
          </p>
          <AskProject />
        </Reveal>

        <Reveal className="section" id="architecture">
          <p className="eyebrow">ARCHITECTURE</p>
          <h2>Where untrusted text enters, and what stops it.</h2>
          <p className="intro-copy">
            Pick any box: the control that runs there, the threats it answers, and the test that
            proves it.
          </p>
          <Architecture titles={threatTitles} />
        </Reveal>

        <Reveal className="section">
          <p className="eyebrow">WHAT THIS DEMONSTRATES</p>
          <h2>Skills, each with its receipt.</h2>
          <div className="skills">
            {SKILLS.map((s) => (
              <a key={s.skill} className="skill" href={s.href}>
                <h3>{s.skill}</h3>
                <p>{s.proof}</p>
                <span>{s.link} ↗</span>
              </a>
            ))}
          </div>
        </Reveal>

        <Reveal className="section">
          <p className="eyebrow">EXPLORE</p>
          <h2>Everything here runs. Go poke it.</h2>
          <div className="explore">
            {EXPLORE.map((e) => (
              <a key={e.href} className="explore-card" href={e.href}>
                <small>{e.tag}</small>
                <h3>{e.title}</h3>
                <p>{e.text}</p>
                <span aria-hidden="true">→</span>
              </a>
            ))}
          </div>
        </Reveal>

        <Reveal className="section">
          <p className="eyebrow">WRITING</p>
          <h2>What I learned, including what went wrong.</h2>
          <ol className="writing">
            {WRITING.map((w) => (
              <li key={w.n}>
                <a href={w.href}>
                  <b>{w.n}</b>
                  <span>{w.title}</span>
                  <i aria-hidden="true">↗</i>
                </a>
              </li>
            ))}
          </ol>
        </Reveal>

        <section className="cta">
          <h2>
            Hiring for LLM engineering
            <br />
            <span>or AI security?</span>
          </h2>
          <p className="intro-copy">
            Every number on this page is generated from a committed report, and CI fails if the site
            drifts from them. Clone the repository and rerun any of it.
          </p>
          <div className="hero-actions">
            <a className="btn primary" href={REPO}>
              View the repository ↗
            </a>
            <a className="btn" href="/brief">
              Get the one-page brief
            </a>
            <a className="btn ghost" href="/engineering">
              Read the case study
            </a>
          </div>
        </section>
      </main>
      <Tour />
      <footer className="home-footer">
        <span>RYPE · built by Dilip Nallamasa</span>
        <span>
          Agent model: {agent.model} · numbers from <code>docs/reports</code> via{" "}
          <a href={`${BLOB}/opslm-demo/scripts/build-home.mjs`}>build-home.mjs</a>
        </span>
      </footer>
    </div>
  );
}
