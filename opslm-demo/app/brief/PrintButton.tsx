"use client";

import { useEffect } from "react";

export default function PrintButton() {
  // /brief?print opens the browser's print dialog, so "Save as PDF" is one click.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("print")) {
      const t = window.setTimeout(() => window.print(), 400);
      return () => window.clearTimeout(t);
    }
  }, []);
  return (
    <button type="button" onClick={() => window.print()}>
      Print / save as PDF
    </button>
  );
}
