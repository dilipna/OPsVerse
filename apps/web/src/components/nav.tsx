"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Chat" },
  { href: "/evals", label: "Evals" },
  { href: "/costs", label: "Costs" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <header className="border-b border-zinc-800 bg-zinc-950">
      <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
        <span className="font-mono text-sm font-bold tracking-tight text-emerald-400">
          OpsVerse<span className="text-zinc-500">.ai</span>
        </span>
        {links.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={`text-sm ${
              pathname === href
                ? "font-medium text-zinc-100"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
