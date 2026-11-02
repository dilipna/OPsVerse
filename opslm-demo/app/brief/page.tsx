import type { Metadata } from "next";
import "./brief.css";
import ask from "../../public/ask.json";
import home from "../../public/home.json";
import PrintButton from "./PrintButton";

export const metadata: Metadata = {
  title: "RYPE · One-page project brief",
  description:
    "A printable one-page summary of RYPE for hiring managers: what was built, measured results with intervals, and where the evidence lives.",
};

const SITE = "https://ops-verse.vercel.app";
const REPO = "https://github.com/dilipna/OPsVerse";
const pct = (x: number) => `${Math.round(x * 100)}%`;
const ci = (c: number[]) => `[${pct(c[0])}, ${pct(c[1])}]`;

export default function Brief() {
  const { agent, injection, retrieval, generation, judge, threats } = home;
  const askEval = ask.evaluation;
  const RESULTS = [
    [
      "Agent under attack",
      `${agent.attack_success}/${agent.attacked_runs} runs leaked the canary or produced an unsafe answer`,
      `95% upper bound ${pct(agent.attack_success_ci_hi)}`,
      "agent-v1",
    ],
    [
      "Agent accuracy",
      `${agent.heldout.k}/${agent.heldout.n} held-out incidents diagnosed; ${agent.attacked_accuracy.k}/${agent.attacked_accuracy.n} with planted attacks`,
      `${agent.derailed} attacked runs derailed (reported)`,
      "agent-v1",
    ],
    [
      "Injection detection",
      `Public benchmark recall ${pct(injection.regex_tpr)} (regex) → ${pct(injection.layered_tpr)} (regex + LLM)`,
      `${ci(injection.layered_tpr_ci95)}; FPR ${pct(injection.layered_fpr)} on ${injection.external_benign} benign`,
      "security-classifier-v1",
    ],
    [
      "Obfuscation robustness",
      `Zero-width attack recall ${pct(injection.zero_width_raw_tpr)} → ${pct(injection.zero_width_normalized_tpr)} after normalization`,
      `${injection.internal_attacks} attacks × 6 transforms`,
      "security-robustness-v1",
    ],
    [
      "Retrieval",
      `hit@10 ${retrieval.dense_hit10.toFixed(2)} dense → ${retrieval.hybrid_hit10.toFixed(2)} hybrid`,
      `${retrieval.questions} questions, ${retrieval.chunks.toLocaleString("en-US")} chunks; reranker rejected`,
      "retrieval-ablation-v3",
    ],
    [
      "Grounding",
      `Retrieved context supports ${pct(generation.contextual_recall)} of reference claims`,
      `${generation.claims} atomic claims`,
      "generator-golden-v1",
    ],
    [
      "LLM-as-judge audit",
      `Judge vs human κ = ${judge.kappa}; judge finds ${pct(judge.human_tpr)} of what humans mark relevant`,
      `n = ${judge.n}`,
      "judge-validation-v2",
    ],
    [
      "Self-RAG on the docs",
      `Held-out hit@3 ${askEval.heldout.hit3}/${askEval.heldout.n}, dev ${askEval.dev.hit3}/${askEval.dev.n}`,
      `${ask.chunks.length} passages from ${ask.files} files`,
      "evalsets/ask-v1",
    ],
  ];

  return (
    <div className="brief-page">
      <div className="brief-tools">
        <a href="/">← Back to the site</a>
        <PrintButton />
      </div>
      <article className="brief">
        <header>
          <div>
            <h1>Dilip Nallamasa</h1>
            <p>LLM engineering · AI security · evaluation</p>
          </div>
          <div className="brief-links">
            <span>{SITE.replace("https://", "")}</span>
            <span>{REPO.replace("https://", "")}</span>
            <span>dilipna.hashnode.dev</span>
          </div>
        </header>

        <section>
          <h2>RYPE, in one paragraph</h2>
          <p>
            An end-to-end LLM system for Kubernetes incidents: ingestion with injection screening,
            hybrid retrieval over official documentation, grounded and cited generation, and a
            read-only tool-using agent. Then it was attacked on purpose. {threats.total} threats are
            mapped to the OWASP LLM Top 10, each with a control, a rerunnable test and an honest
            status, and every published number is regenerated from committed reports and checked in
            CI.
          </p>
        </section>

        <section className="brief-cols">
          <div>
            <h2>What I built</h2>
            <ul>
              <li>
                <b>RAG pipeline</b>: streaming ingestion, BM25 + BGE hybrid retrieval in Qdrant,
                abstention, verbatim citation checks.
              </li>
              <li>
                <b>Tool-using agent</b>: read-only kubectl behind a code-enforced policy, fenced
                tool output, canary, budget and checked answers.
              </li>
              <li>
                <b>Security layer</b>: normalization + regex + LLM classifier at ingest, streaming
                output guard, 16-format redaction, SSRF guard with IP pinning, rate limits.
              </li>
              <li>
                <b>Evaluation</b>: Wilson and bootstrap intervals, paired tests, human-validated LLM
                judge, held-out sets, external benchmarks.
              </li>
              <li>
                <b>Platform</b>: FastAPI, Redis Streams, LiteLLM, Langfuse, hash-pinned models,
                SBOM, blocking pip-audit / npm audit / Trivy, hardened Kubernetes manifests.
              </li>
              <li>
                <b>Model work</b>: Qwen3-4B QLoRA fine-tune published as OpsLM-v1 under a
                contamination policy; DPO pipeline built; vLLM vs Ollama measured under an SLO.
              </li>
            </ul>
          </div>
          <div>
            <h2>How I work</h2>
            <ul>
              <li>
                <b>Evaluation first.</b> The harness existed before the model, and it changed the
                retrieval design twice.
              </li>
              <li>
                <b>Test against data I did not write.</b> A perfect internal injection score fell to{" "}
                {pct(injection.regex_tpr)} on a public benchmark; I reported it, then fixed it with
                measured evidence.
              </li>
              <li>
                <b>Publish what was wrong.</b> {home.withdrawn_claims} claims this project believed
                were tested and withdrawn, each with the statistic that overturned it.
              </li>
              <li>
                <b>Hold out data.</b> Agent and retrieval results are reported on scenarios never
                used for debugging.
              </li>
            </ul>
          </div>
        </section>

        <section>
          <h2>Measured results</h2>
          <table>
            <thead>
              <tr>
                <th>Area</th>
                <th>Result</th>
                <th>Context</th>
                <th>Report</th>
              </tr>
            </thead>
            <tbody>
              {RESULTS.map(([area, result, context, report]) => (
                <tr key={area}>
                  <td>{area}</td>
                  <td>{result}</td>
                  <td>{context}</td>
                  <td>
                    <code>{report}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <footer>
          <span>
            Try it: {SITE.replace("https://", "")} (live controls, agent replays, Ask the project)
          </span>
          <span>
            Every number above is generated from committed reports · {agent.model} for agent runs
          </span>
        </footer>
      </article>
    </div>
  );
}
