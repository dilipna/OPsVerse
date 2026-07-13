"use client";

import { useEffect, useState } from "react";
import { getJSON } from "@/lib/api";

type ModelCosts = {
  model: string | null;
  route: string;
  requests: number;
  errors: number;
  degraded: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  avg_latency_ms: number | null;
  avg_first_token_ms: number | null;
};

type CostSummary = {
  since: string;
  totals: ModelCosts;
  by_model: ModelCosts[];
};

const WINDOWS = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
];

function Card({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-800/40 p-4">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 font-mono text-2xl text-zinc-100">{value}</p>
      {hint && <p className="mt-1 text-[10px] text-zinc-500">{hint}</p>}
    </div>
  );
}

export default function CostsPage() {
  const [hours, setHours] = useState(168);
  const [data, setData] = useState<CostSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJSON<CostSummary>(`/v1/costs/summary?hours=${hours}`)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [hours]);

  if (error)
    return <p className="font-mono text-sm text-red-400">{error}</p>;
  if (!data) return <p className="text-sm text-zinc-500">loading…</p>;

  const t = data.totals;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Cost & latency — request ledger</h1>
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              onClick={() => setHours(w.hours)}
              className={`rounded px-2 py-1 font-mono text-xs ${
                hours === w.hours
                  ? "bg-emerald-700 text-white"
                  : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card label="requests" value={String(t.requests)} hint={`${t.errors} errors · ${t.degraded} degraded`} />
        <Card
          label="cost (free tier: $0 charged)"
          value={`$${t.cost_usd.toFixed(4)}`}
          hint="list-price equivalent via litellm"
        />
        <Card
          label="tokens in → out"
          value={`${t.prompt_tokens} → ${t.completion_tokens}`}
        />
        <Card
          label="avg latency"
          value={t.avg_latency_ms != null ? `${(t.avg_latency_ms / 1000).toFixed(1)}s` : "—"}
          hint={
            t.avg_first_token_ms != null
              ? `first token ${(t.avg_first_token_ms / 1000).toFixed(1)}s avg`
              : undefined
          }
        />
      </div>

      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-zinc-700 font-mono text-zinc-500">
            <th className="py-2 pr-3">model</th>
            <th className="py-2 pr-3">route</th>
            <th className="py-2 pr-3 text-right">req</th>
            <th className="py-2 pr-3 text-right">err</th>
            <th className="py-2 pr-3 text-right">tok in→out</th>
            <th className="py-2 pr-3 text-right">cost</th>
            <th className="py-2 text-right">avg latency</th>
          </tr>
        </thead>
        <tbody>
          {data.by_model.map((m, i) => (
            <tr key={i} className="border-b border-zinc-800/60">
              <td className="py-2 pr-3 font-mono text-emerald-400">
                {m.model ?? "(failed before model)"}
              </td>
              <td className="py-2 pr-3 font-mono">{m.route}</td>
              <td className="py-2 pr-3 text-right">{m.requests}</td>
              <td className="py-2 pr-3 text-right">{m.errors}</td>
              <td className="py-2 pr-3 text-right font-mono">
                {m.prompt_tokens}→{m.completion_tokens}
              </td>
              <td className="py-2 pr-3 text-right font-mono">${m.cost_usd.toFixed(5)}</td>
              <td className="py-2 text-right font-mono">
                {m.avg_latency_ms != null ? `${(m.avg_latency_ms / 1000).toFixed(1)}s` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
