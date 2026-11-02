import { ImageResponse } from "next/og";
import home from "../public/home.json";

// The card LinkedIn, Slack and X show when the site link is shared.
export const alt = "RYPE: LLM systems, built to be attacked";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const pct = (x: number) => `${Math.round(x * 100)}%`;

export default function OpenGraphImage() {
  const { agent, injection, threats } = home;
  const stats = [
    [`${agent.attack_success}/${agent.attacked_runs}`, "attacked agent runs leaked"],
    [`${agent.heldout.k}/${agent.heldout.n}`, "held-out incidents solved"],
    [`${threats.total}`, "threats modeled (OWASP LLM)"],
    [`${pct(injection.regex_tpr)} → ${pct(injection.layered_tpr)}`, "external injection recall"],
  ];
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "64px 72px",
          background: "radial-gradient(circle at 85% 10%, #173325 0%, #0b0e11 55%)",
          color: "#e9edef",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", fontSize: 30, fontWeight: 700 }}>
          <span>RY</span>
          <span style={{ color: "#9ce5b8" }}>PE</span>
          <span style={{ marginLeft: 18, fontSize: 22, color: "#8fa59a", fontWeight: 400 }}>
            by Dilip Nallamasa · LLM systems & AI security
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 78, fontWeight: 700, letterSpacing: -3, lineHeight: 1.05 }}>
            I build LLM systems.
          </div>
          <div
            style={{
              fontSize: 78,
              fontWeight: 700,
              letterSpacing: -3,
              lineHeight: 1.05,
              color: "#9ce5b8",
            }}
          >
            Then I attack them.
          </div>
        </div>
        <div style={{ display: "flex", gap: 20 }}>
          {stats.map(([value, label]) => (
            <div
              key={label}
              style={{
                display: "flex",
                flexDirection: "column",
                flex: 1,
                padding: "18px 20px",
                border: "1px solid #2f4a3a",
                borderRadius: 12,
                background: "rgba(15, 21, 18, 0.85)",
              }}
            >
              <span style={{ fontSize: 36, fontWeight: 700, color: "#9ce5b8" }}>{value}</span>
              <span style={{ fontSize: 19, color: "#a7b6ad", marginTop: 6 }}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
