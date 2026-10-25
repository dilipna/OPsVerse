import type { Metadata } from "next";
import "./globals.css";
import "./workspace.css";

export const metadata: Metadata = {
  title: "RYPE — Route Your Prompt Efficiently",
  description:
    "Route Your Prompt Efficiently: retrieve covered Kubernetes guidance without inference, route other questions to eligible free OpenRouter models, and inspect route and cost receipts.",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%23e8ff74'/%3E%3Cpath d='M10 23L23 10M10 10H23V23' fill='none' stroke='%2310172b' stroke-width='2.5'/%3E%3C/svg%3E",
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
        <link rel="preload" href="/fonts/SpaceGrotesk.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/>
        <link rel="preload" href="/fonts/PlusJakartaSans.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/>
        <link rel="preload" href="/fonts/Inter.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/>
        <link rel="preload" href="/fonts/IBMPlexMono.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/>
      </head>
      <body>{children}</body>
    </html>
  );
}
