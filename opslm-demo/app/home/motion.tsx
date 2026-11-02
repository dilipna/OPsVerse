"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

const reduced = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function useInView<T extends Element>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (reduced() || !("IntersectionObserver" in window)) {
      setSeen(true);
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold: 0.25 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  return [ref, seen];
}

/** Fades and lifts its children in the first time they scroll into view. */
export function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const [ref, seen] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={`reveal ${seen ? "in" : ""} ${className}`}>
      {children}
    </div>
  );
}

/** Counts up to `value` once visible. The final text is what screen readers get. */
export function Counter({
  value,
  decimals = 0,
  suffix = "",
}: {
  value: number;
  decimals?: number;
  suffix?: string;
}) {
  const [ref, seen] = useInView<HTMLSpanElement>();
  const [current, setCurrent] = useState(0);
  useEffect(() => {
    if (!seen) return;
    if (reduced()) {
      setCurrent(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 1100);
      setCurrent(value * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [seen, value]);
  const fmt = (x: number) =>
    x.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  const final = `${fmt(value)}${suffix}`;
  return (
    <span ref={ref} aria-label={final}>
      <span aria-hidden="true">
        {fmt(seen ? current : 0)}
        {suffix}
      </span>
    </span>
  );
}

type Bar = {
  label: string;
  detail: string;
  value: number;
  ci?: number[];
  tone: "good" | "bad" | "mid";
};

/** Horizontal rate bars with 95% interval whiskers; they grow in when visible. */
export function RateBars({ bars }: { bars: Bar[] }) {
  const [ref, seen] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={`rate-bars ${seen ? "in" : ""}`} role="list">
      {bars.map((b) => (
        <div key={b.label} className={`rate-row ${b.tone}`} role="listitem">
          <div className="rate-label">
            <strong>{b.label}</strong>
            <span>{b.detail}</span>
          </div>
          <div
            className="rate-track"
            aria-label={`${Math.round(b.value * 100)}%${b.ci ? `, 95% interval ${Math.round(b.ci[0] * 100)} to ${Math.round(b.ci[1] * 100)}%` : ""}`}
          >
            <div className="rate-fill" style={{ width: seen ? `${b.value * 100}%` : 0 }} />
            {b.ci && (
              <div
                className="rate-ci"
                style={{ left: `${b.ci[0] * 100}%`, width: `${(b.ci[1] - b.ci[0]) * 100}%` }}
              />
            )}
            <b>{Math.round(b.value * 100)}%</b>
          </div>
        </div>
      ))}
    </div>
  );
}
