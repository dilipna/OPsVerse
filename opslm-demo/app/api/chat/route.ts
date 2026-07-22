// Serverless chat proxy. Calls a served OpsLM endpoint (OpenAI-compatible
// /v1/chat/completions) when OPSLM_ENDPOINT is set; otherwise returns a clearly
// labelled canned reply so the deployed site is always functional.
//
// Env (set in Vercel project settings):
//   OPSLM_ENDPOINT  e.g. https://<user>-opslm.hf.space/v1   (no trailing slash needed)
//   OPSLM_MODEL     model id to request (default "opslm")
//   OPSLM_API_KEY   optional bearer token if the endpoint needs one

export const runtime = "edge";

const SYSTEM =
  "You are OpsLM, a concise DevOps/MLOps assistant. Answer questions about " +
  "Kubernetes, Docker, Terraform, and MLflow accurately and briefly. If unsure, say so.";

const CANNED: Record<string, string> = {
  crashloop:
    "CrashLoopBackOff means the container keeps exiting and the kubelet keeps restarting it with backoff. Check, in order: (1) `kubectl logs <pod> --previous` for the crash reason, (2) `kubectl describe pod <pod>` for OOMKilled / failed probes / image pull errors, (3) the container's command/entrypoint and required env/secrets. Most cases are a bad command, a missing config, or a failing readiness/liveness probe killing a healthy-but-slow start.",
  probe:
    "A readiness probe decides whether a Pod should receive traffic — failing it removes the Pod from Service endpoints but does NOT restart it. A liveness probe decides whether the container is healthy — failing it makes the kubelet restart the container. Use readiness for slow-start or dependency-gated apps; use liveness only to recover from unrecoverable hangs. Misusing liveness for slow starts causes restart loops.",
  healthcheck:
    "For a Flask app on :8000:\n\n    HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \\\n      CMD curl -fsS http://localhost:8000/health || exit 1\n\nExpose a lightweight `/health` route that returns 200 only when the app can serve. Keep it dependency-light so the check reflects the process, not downstream services.",
  terraform:
    "`terraform plan` computes and shows the diff between your configuration and the current state — it changes nothing. `terraform apply` executes that diff to reach the desired state (and by default re-plans first, prompting for approval). Plan is your safe dry-run; apply is the mutation. In CI, run `plan` on PRs and gate `apply` behind review.",
  default:
    "OpsLM here. This deployment is in demo mode (no model backend wired), so I'm returning a sample answer. Connect a served OpsLM endpoint via the OPSLM_ENDPOINT env var for live, corpus-grounded responses. Meanwhile: ask about CrashLoopBackOff, readiness vs liveness probes, Docker HEALTHCHECK, or terraform plan vs apply.",
};

function cannedReply(q: string): string {
  const s = q.toLowerCase();
  if (s.includes("crashloop") || s.includes("crash loop")) return CANNED.crashloop;
  if (s.includes("readiness") || s.includes("liveness") || s.includes("probe"))
    return CANNED.probe;
  if (s.includes("healthcheck") || s.includes("dockerfile") || s.includes("flask"))
    return CANNED.healthcheck;
  if (s.includes("terraform") || s.includes("plan") || s.includes("apply"))
    return CANNED.terraform;
  return CANNED.default;
}

export async function GET() {
  return Response.json({ live: Boolean(process.env.OPSLM_ENDPOINT) });
}

export async function POST(req: Request) {
  const { messages = [] } = await req.json().catch(() => ({ messages: [] }));
  const last = [...messages].reverse().find((m: any) => m.role === "user");
  const question: string = last?.content ?? "";

  const endpoint = process.env.OPSLM_ENDPOINT;
  if (!endpoint) {
    return Response.json({
      reply: cannedReply(question),
      note: "demo mode · no model backend connected",
    });
  }

  try {
    const res = await fetch(`${endpoint.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(process.env.OPSLM_API_KEY
          ? { authorization: `Bearer ${process.env.OPSLM_API_KEY}` }
          : {}),
      },
      body: JSON.stringify({
        model: process.env.OPSLM_MODEL ?? "opslm",
        messages: [{ role: "system", content: SYSTEM }, ...messages],
        temperature: 0.3,
        max_tokens: 512,
      }),
    });
    if (!res.ok) throw new Error(`upstream ${res.status}`);
    const data = await res.json();
    const reply = data?.choices?.[0]?.message?.content?.trim();
    return Response.json({ reply: reply || "(empty response)" });
  } catch (err: any) {
    return Response.json({
      reply: cannedReply(question),
      note: `backend unreachable (${err?.message ?? "error"}) · served a demo answer`,
    });
  }
}
