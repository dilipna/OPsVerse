// One header for every page, so navigation is identical wherever a visitor lands.
const LINKS: [string, string][] = [
  ["/lab", "Lab"],
  ["/agent", "Agent"],
  ["/security", "Security"],
  ["/troubleshoot", "Workspace"],
  ["/writing", "Writing"],
  ["/engineering", "Engineering"],
];

export default function SiteHeader({ section, current }: { section: string; current?: string }) {
  return (
    <header className="site-header">
      <a className="wordmark" href="/">
        RY<span>PE</span>
        <small> / {section}</small>
      </a>
      <nav aria-label="Main navigation">
        {LINKS.map(([href, label]) => (
          <a key={href} href={href} aria-current={href === current ? "page" : undefined}>
            {label}
          </a>
        ))}
        <a href="https://github.com/dilipna/OPsVerse">GitHub ↗</a>
      </nav>
    </header>
  );
}
