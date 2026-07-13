export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export type SourceInfo = {
  index: number;
  id: string;
  source: string;
  section: string | null;
  tool: string | null;
  doc_type: string | null;
  score: number;
  rerank_score: number | null;
  text: string;
};

export type ChatSources = {
  type: "sources";
  sources: SourceInfo[];
  image_description: string | null;
  degraded: string[];
};

export type ChatDone = {
  type: "done";
  model: string;
  cited: number[];
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cost_usd: number | null;
  latency_ms: number;
  first_token_ms: number | null;
  degraded: string[];
};

export type ChatEvent =
  | ChatSources
  | { type: "delta"; text: string }
  | ChatDone
  | { type: "error"; message: string };

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type ChatRequest = {
  query: string;
  history: ChatTurn[];
  k?: number;
  image_base64?: string | null;
  image_mime?: string;
};

/** POST /v1/chat and yield each SSE event as it arrives. */
export async function* streamChat(
  req: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const resp = await fetch(`${API_URL}/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...req, stream: true }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`chat request failed: HTTP ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line
    for (;;) {
      const sep = buffer.indexOf("\n\n");
      if (sep === -1) break;
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = frame
        .split("\n")
        .find((line) => line.startsWith("data: "));
      if (dataLine) {
        yield JSON.parse(dataLine.slice(6)) as ChatEvent;
      }
    }
  }
}

export async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`);
  if (!resp.ok) throw new Error(`GET ${path} failed: HTTP ${resp.status}`);
  return resp.json() as Promise<T>;
}
