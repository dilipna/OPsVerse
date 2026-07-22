import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpsLM — a DevOps language model, measured end to end",
  description:
    "OpsLM is a Qwen3-4B model fine-tuned on a decontaminated DevOps/MLOps corpus, served with a hybrid-RAG stack and gated by an eval-first platform.",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%23080808'/%3E%3Ctext x='4' y='24' font-family='monospace' font-size='22' fill='%23ff2b2b'%3E%3E_%3C/text%3E%3C/svg%3E",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
