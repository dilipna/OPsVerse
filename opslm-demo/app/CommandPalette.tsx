"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import security from "../public/security.json";

const BLOB = "https://github.com/dilipna/OPsVerse/blob/main";

type Item = { group: string; label: string; hint: string; href: string };

const ITEMS: Item[] = [
  { group: "Go to", label: "Home", hint: "The story in one page", href: "/" },
  { group: "Go to", label: "Security Lab", hint: "Run the controls on your input", href: "/lab" },
  { group: "Go to", label: "Agent replays", hint: "Step through recorded runs", href: "/agent" },
  {
    group: "Go to",
    label: "Security",
    hint: "Threat model and measured controls",
    href: "/security",
  },
  {
    group: "Go to",
    label: "Incident workspace",
    hint: "Cited Kubernetes investigation",
    href: "/troubleshoot",
  },
  {
    group: "Go to",
    label: "Engineering case study",
    hint: "How it was built",
    href: "/engineering",
  },
  { group: "Go to", label: "Evaluation methods", hint: "Methods and outcomes", href: "/study" },
  {
    group: "Go to",
    label: "Runbook navigator",
    hint: "Search official runbooks",
    href: "/runbooks",
  },
  {
    group: "Go to",
    label: "One-page brief",
    hint: "Printable, for hiring managers",
    href: "/brief",
  },
  { group: "Do", label: "Take the 60-second tour", hint: "Guided walkthrough", href: "/?tour" },
  { group: "Do", label: "Try to break the agent", hint: "Make it read a Secret", href: "/#break" },
  {
    group: "Do",
    label: "Ask the project a question",
    hint: "RAG over the repo's docs",
    href: "/#ask",
  },
  { group: "Do", label: "Print the brief", hint: "Save as PDF", href: "/brief?print" },
  ...security.threats.map((t) => ({
    group: "Threats",
    label: `${t.id} · ${t.threat}`,
    hint: t.status,
    href: `${BLOB}/docs/security/threat-model.md`,
  })),
  ...(
    [
      ["Agent evaluation", "docs/reports/agent-v1.md"],
      ["Injection benchmark (external)", "docs/reports/security-classifier-v1.md"],
      ["Detector robustness", "docs/reports/security-robustness-v1.md"],
      ["Retrieval ablation v3", "docs/reports/retrieval-ablation-v3.md"],
      ["Judge validation against humans", "docs/reports/judge-validation-v2.md"],
      ["Generation: contextual recall", "docs/reports/generator-golden-v1.md"],
      ["Embedding model ablation", "docs/reports/embedding-ablation-v1.md"],
      ["Capacity and SLO", "docs/reports/capacity-and-slo-v1.md"],
      ["Evidence index: claims withdrawn", "docs/evidence.md"],
      ["Known limitations", "docs/limitations.md"],
    ] as const
  ).map(([label, path]) => ({ group: "Reports", label, hint: path, href: `${BLOB}/${path}` })),
  {
    group: "Source",
    label: "GitHub repository",
    hint: "dilipna/OPsVerse",
    href: "https://github.com/dilipna/OPsVerse",
  },
  {
    group: "Source",
    label: "Write-ups",
    hint: "dilipna.hashnode.dev",
    href: "https://dilipna.hashnode.dev",
  },
];

function score(item: Item, q: string) {
  if (!q) return 1;
  const hay = `${item.label} ${item.hint} ${item.group}`.toLowerCase();
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.every((w) => hay.includes(w))) return 0;
  return item.label.toLowerCase().startsWith(words[0]) ? 3 : 2;
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target as HTMLElement)?.tagName ?? "");
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "/" && !typing && !open) {
        e.preventDefault();
        setOpen(true);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("rype:palette", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("rype:palette", onOpen);
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      requestAnimationFrame(() => input.current?.focus());
    }
  }, [open]);

  const results = useMemo(
    () =>
      ITEMS.map((item) => ({ item, s: score(item, query.trim()) }))
        .filter((r) => r.s > 0)
        .sort((a, b) => b.s - a.s)
        .slice(0, 40)
        .map((r) => r.item),
    [query],
  );

  useEffect(() => {
    list.current
      ?.querySelector<HTMLElement>(`[data-i="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function go(item: Item | undefined) {
    if (!item) return;
    setOpen(false);
    if (item.href.startsWith("http")) window.open(item.href, "_blank", "noopener,noreferrer");
    else window.location.assign(item.href);
  }

  return (
    <>
      <button
        type="button"
        className="palette-hint"
        onClick={() => setOpen(true)}
        aria-label="Open the command palette"
      >
        <span>Search</span> <kbd>⌘K</kbd>
      </button>
      {open && (
        <div className="palette-backdrop" onMouseDown={() => setOpen(false)}>
          <div
            className="palette"
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <input
              ref={input}
              value={query}
              placeholder="Jump to a page, report, threat or action…"
              aria-label="Search"
              aria-controls="palette-list"
              aria-activedescendant={results[active] ? `palette-${active}` : undefined}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActive((a) => Math.min(a + 1, results.length - 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActive((a) => Math.max(a - 1, 0));
                } else if (e.key === "Enter") {
                  e.preventDefault();
                  go(results[active]);
                } else if (e.key === "Escape") {
                  setOpen(false);
                }
              }}
            />
            <ul id="palette-list" ref={list} role="listbox">
              {results.length === 0 && <li className="palette-empty">No matches.</li>}
              {results.map((item, i) => (
                <li
                  key={`${item.group}-${item.label}`}
                  id={`palette-${i}`}
                  data-i={i}
                  role="option"
                  aria-selected={i === active}
                  className={i === active ? "active" : ""}
                  onMouseMove={() => setActive(i)}
                  onClick={() => go(item)}
                >
                  <small>{item.group}</small>
                  <span>{item.label}</span>
                  <em>{item.hint}</em>
                </li>
              ))}
            </ul>
            <footer>
              <span>
                <kbd>↑</kbd> <kbd>↓</kbd> move · <kbd>↵</kbd> open · <kbd>esc</kbd> close
              </span>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
