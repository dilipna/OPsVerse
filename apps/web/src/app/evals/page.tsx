"use client";

import { useEffect, useState } from "react";
import { getJSON } from "@/lib/api";

type AblationResults = Record<string, Record<string, number>>;

type Report = {
  report: string;
  kind: string;
  date: string;
  dataset: string;
  cases: number;
  generator_model: string;
  corpus_stats: Record<string, number>;
  k: number;
  results: AblationResults;
};

const CHUNK_COLS = [
  "chunk:hit@1",
  "chunk:hit@3",
  "chunk:hit@5",
  "chunk:hit@10",
  "chunk:mrr@10",
  "chunk:ndcg@10",
];
const DOC_COLS = ["doc:hit@1", "doc:hit@5", "doc:mrr@10"];

function MetricTable({
  results,
  cols,
}: {
  results: AblationResults;
  cols: string[];
}) {
  const modes = Object.keys(results);
  const best: Record<string, number> = {};
  for (const col of cols) {
    best[col] = Math.max(...modes.map((m) => results[m][col] ?? 0));
  }
  return (
    <table className="w-full text-left text-xs">
      <thead>
        <tr className="border-b border-zinc-700 font-mono text-zinc-500">
          <th className="py-2 pr-3">mode</th>
          {cols.map((c) => (
            <th key={c} className="py-2 pr-3 text-right">
              {c.split(":")[1]}
            </th>
          ))}
          <th className="py-2 text-right">ms/query</th>
        </tr>
      </thead>
      <tbody>
        {modes.map((mode) => (
          <tr key={mode} className="border-b border-zinc-800/60">
            <td className="py-2 pr-3 font-mono text-emerald-400">{mode}</td>
            {cols.map((c) => (
              <td
                key={c}
                className={`py-2 pr-3 text-right font-mono ${
                  results[mode][c] === best[c] ? "font-bold text-emerald-300" : ""
                }`}
              >
                {(results[mode][c] ?? 0).toFixed(3)}
              </td>
            ))}
            <td className="py-2 text-right font-mono text-zinc-500">
              {results[mode]["latency_ms_per_query"] ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function EvalsPage() {
  const [reports, setReports] = useState<Report[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJSON<Report[]>("/v1/evals/reports")
      .then(setReports)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="font-mono text-sm text-red-400">{error}</p>;
  if (!reports) return <p className="text-sm text-zinc-500">loading…</p>;
  if (!reports.length)
    return (
      <p className="text-sm text-zinc-500">
        No eval reports yet — run <code>uv run python -m opsverse_evals.run_ablation</code>.
      </p>
    );

  return (
    <div className="space-y-10">
      {reports.map((r) => (
        <section key={r.report} className="space-y-4">
          <div>
            <h1 className="text-lg font-semibold">{r.report}</h1>
            <p className="mt-1 text-xs text-zinc-500">
              {r.cases} questions over {r.corpus_stats?.documents} docs /{" "}
              {r.corpus_stats?.chunks} chunks · model{" "}
              <span className="font-mono">{r.generator_model}</span> · k={r.k} ·{" "}
              {r.date}
            </p>
          </div>
          {r.kind === "retrieval-ablation" ? (
            <>
              <div>
                <h2 className="mb-2 text-sm font-medium text-zinc-300">
                  Chunk-level (strict gold chunk)
                </h2>
                <MetricTable results={r.results} cols={CHUNK_COLS} />
              </div>
              <div>
                <h2 className="mb-2 text-sm font-medium text-zinc-300">
                  Document-level (any chunk of the gold document)
                </h2>
                <MetricTable results={r.results} cols={DOC_COLS} />
              </div>
            </>
          ) : (
            <MetricTable
              results={r.results}
              cols={[
                ...new Set(
                  Object.values(r.results).flatMap((m) =>
                    Object.keys(m).filter((c) => c !== "latency_ms_per_query"),
                  ),
                ),
              ]}
            />
          )}
        </section>
      ))}
    </div>
  );
}
