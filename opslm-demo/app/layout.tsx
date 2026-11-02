import type { Metadata } from "next";
import "./globals.css";

const title = "RYPE: LLM systems, built to be attacked";
const description =
  "A RAG assistant and tool-using Kubernetes agent by Dilip Nallamasa, defended like production: every control mapped to a threat, tested, and measured against attacks it didn't write. Try to break it in your browser.";

export const metadata: Metadata = {
  metadataBase: new URL("https://ops-verse.vercel.app"),
  title,
  description,
  openGraph: { title, description, type: "website", siteName: "RYPE" },
  twitter: { card: "summary_large_image", title, description },
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%230b0e11'/%3E%3Ctext x='5' y='23' font-family='monospace' font-size='19' font-weight='700' fill='%239ce5b8'%3E%3E_%3C/text%3E%3C/svg%3E",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
