import type { Metadata } from "next";
import "./globals.css";
import "./workspace.css";

export const metadata: Metadata = {
  title: "OpsVerse — Kubernetes investigation workspace",
  description:
    "Turn Kubernetes symptoms into an inspectable incident brief. Find official source passages, review evidence, and explore the engineering behind OpsVerse.",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='16' fill='%23244fb8'/%3E%3Cpath d='M16 5L26 16L16 27L6 16Z' fill='none' stroke='%23fffefa' stroke-width='1.5'/%3E%3Ccircle cx='16' cy='16' r='3' fill='%23fffefa'/%3E%3C/svg%3E",
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
