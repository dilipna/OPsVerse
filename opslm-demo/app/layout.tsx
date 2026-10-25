import type { Metadata } from "next";
import "./globals.css";
import "./workspace.css";

export const metadata: Metadata = {
  title: "OpsVerse — a little clarity for your Kubernetes cluster",
  description:
    "Ask about a Kubernetes problem, explore relevant documentation, and save what you find. Simple questions, inspectable sources, and no cluster connection.",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%23087f73'/%3E%3Cpath d='M10 23L23 10M10 10H23V23' fill='none' stroke='%23ffffff' stroke-width='2.5'/%3E%3C/svg%3E",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preload" href="/fonts/PlusJakartaSans.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/>
        <link rel="preload" href="/fonts/Inter.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/>
        <link rel="preload" href="/fonts/IBMPlexMono.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/>
      </head>
      <body>{children}</body>
    </html>
  );
}
