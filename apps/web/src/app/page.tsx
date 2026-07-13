"use client";

import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  type ChatDone,
  type ChatSources,
  type ChatTurn,
  streamChat,
} from "@/lib/api";

type AssistantMessage = {
  role: "assistant";
  content: string;
  sources?: ChatSources;
  done?: ChatDone;
  error?: string;
};
type Message = { role: "user"; content: string; hasImage?: boolean } | AssistantMessage;

function DegradedBadges({ degraded }: { degraded: string[] }) {
  if (!degraded.length) return null;
  return (
    <span className="flex gap-1">
      {degraded.map((d) => (
        <span
          key={d}
          className="rounded bg-amber-900/60 px-1.5 py-0.5 font-mono text-[10px] text-amber-300"
        >
          {d}
        </span>
      ))}
    </span>
  );
}

function SourcesPanel({ sources }: { sources: ChatSources }) {
  const [open, setOpen] = useState(false);
  if (!sources.sources.length && !sources.image_description) return null;
  return (
    <div className="mt-2 rounded border border-zinc-700/60 bg-zinc-800/40 text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-zinc-400 hover:text-zinc-200"
      >
        <span>{open ? "▾" : "▸"}</span>
        <span>{sources.sources.length} sources</span>
        {sources.image_description && <span>· image described</span>}
        <DegradedBadges degraded={sources.degraded} />
      </button>
      {open && (
        <div className="space-y-2 border-t border-zinc-700/60 p-2">
          {sources.image_description && (
            <p className="text-zinc-400">
              <span className="font-semibold text-zinc-300">image:</span>{" "}
              {sources.image_description}
            </p>
          )}
          {sources.sources.map((s) => (
            <div key={s.id}>
              <p className="font-mono text-emerald-400">
                [{s.index}] {s.source}
                {s.section ? ` — ${s.section}` : ""}
              </p>
              <p className="line-clamp-2 text-zinc-500">{s.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatsLine({ done }: { done: ChatDone }) {
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-3 font-mono text-[10px] text-zinc-500">
      <span>{done.model}</span>
      {done.first_token_ms != null && (
        <span>first token {(done.first_token_ms / 1000).toFixed(1)}s</span>
      )}
      <span>{(done.latency_ms / 1000).toFixed(1)}s total</span>
      {done.prompt_tokens != null && (
        <span>
          {done.prompt_tokens}→{done.completion_tokens} tok
        </span>
      )}
      {done.cost_usd != null && <span>${done.cost_usd.toFixed(5)}</span>}
      {done.cited.length > 0 && (
        <span>cited {done.cited.map((c) => `[${c}]`).join("")}</span>
      )}
      <DegradedBadges degraded={done.degraded} />
    </p>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [image, setImage] = useState<{ b64: string; mime: string; name: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function send() {
    const query = input.trim();
    if (!query || busy) return;
    setBusy(true);
    setInput("");

    const history: ChatTurn[] = messages
      .filter((m) => !("error" in m && m.error))
      .map((m) => ({ role: m.role, content: m.content }));

    const assistant: AssistantMessage = { role: "assistant", content: "" };
    setMessages((prev) => [
      ...prev,
      { role: "user", content: query, hasImage: !!image },
      assistant,
    ]);
    const patch = (fn: (a: AssistantMessage) => AssistantMessage) =>
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = fn(next[next.length - 1] as AssistantMessage);
        return next;
      });

    try {
      for await (const event of streamChat({
        query,
        history,
        image_base64: image?.b64 ?? null,
        image_mime: image?.mime ?? "image/png",
      })) {
        if (event.type === "sources") patch((a) => ({ ...a, sources: event }));
        else if (event.type === "delta")
          patch((a) => ({ ...a, content: a.content + event.text }));
        else if (event.type === "done") patch((a) => ({ ...a, done: event }));
        else patch((a) => ({ ...a, error: event.message }));
      }
    } catch (err) {
      patch((a) => ({ ...a, error: String(err) }));
    } finally {
      setImage(null);
      if (fileRef.current) fileRef.current.value = "";
      setBusy(false);
    }
  }

  function onFile(file: File | undefined) {
    if (!file) return setImage(null);
    const reader = new FileReader();
    reader.onload = () => {
      const url = reader.result as string; // data:<mime>;base64,<data>
      const [meta, b64] = url.split(",", 2);
      const mime = meta.slice(5).split(";")[0];
      setImage({ b64, mime, name: file.name });
    };
    reader.readAsDataURL(file);
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.length === 0 && (
          <p className="pt-16 text-center text-sm text-zinc-500">
            Ask about Kubernetes, Docker, Terraform, MLflow… Answers are
            grounded in the ingested corpus with [n] citations.
          </p>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div
              key={i}
              className="ml-auto max-w-[80%] rounded-lg bg-emerald-900/40 px-3 py-2"
            >
              <p className="whitespace-pre-wrap text-sm">{m.content}</p>
              {m.hasImage && (
                <p className="mt-1 font-mono text-[10px] text-zinc-400">
                  📎 image attached
                </p>
              )}
            </div>
          ) : (
            <div key={i} className="max-w-[95%]">
              {m.sources && <SourcesPanel sources={m.sources} />}
              <div className="prose prose-invert prose-sm mt-2 max-w-none rounded-lg bg-zinc-800/60 px-4 py-3 [&_code]:text-emerald-300 [&_pre]:overflow-x-auto [&_pre]:rounded [&_pre]:bg-zinc-950 [&_pre]:p-3">
                {m.content ? (
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                ) : (
                  !m.error && (
                    <p className="animate-pulse text-zinc-500">retrieving…</p>
                  )
                )}
              </div>
              {m.error && (
                <p className="mt-1 rounded bg-red-900/40 px-2 py-1 font-mono text-xs text-red-300">
                  {m.error}
                </p>
              )}
              {m.done && <StatsLine done={m.done} />}
            </div>
          ),
        )}
      </div>

      <div className="flex items-end gap-2 border-t border-zinc-800 pt-3">
        <label className="cursor-pointer rounded border border-zinc-700 px-2 py-2 text-xs text-zinc-400 hover:text-zinc-200">
          {image ? `📎 ${image.name}` : "📎 image"}
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
        </label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={2}
          placeholder="How do I healthcheck a postgres container?  (Enter to send)"
          className="flex-1 resize-none rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
        <button
          onClick={send}
          disabled={busy || !input.trim()}
          className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium disabled:opacity-40"
        >
          {busy ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
