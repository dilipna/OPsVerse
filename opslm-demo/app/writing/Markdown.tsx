import type { ReactNode } from "react";
import type { Block, Inline } from "../../lib/markdown.mjs";
import { inlineText } from "../../lib/markdown.mjs";

// Renders the parsed tree as React elements. There is no path from a post to raw HTML:
// every node becomes a fixed element, and text is escaped by React.

export const headingId = (nodes: Inline[]) =>
  inlineText(nodes)
    .toLowerCase()
    .replace(/[^a-z0-9 -]/g, "")
    .trim()
    .replace(/\s+/g, "-");

function Inlines({ nodes }: { nodes: Inline[] }): ReactNode {
  return nodes.map((n, i) => {
    switch (n.t) {
      case "text":
        return n.v;
      case "code":
        return <code key={i}>{n.v}</code>;
      case "strong":
        return (
          <strong key={i}>
            <Inlines nodes={n.c} />
          </strong>
        );
      case "em":
        return (
          <em key={i}>
            <Inlines nodes={n.c} />
          </em>
        );
      case "link": {
        const external = /^https?:/i.test(n.href);
        return (
          <a key={i} href={n.href} {...(external ? { rel: "noopener noreferrer nofollow" } : {})}>
            <Inlines nodes={n.c} />
          </a>
        );
      }
    }
  });
}

export default function Markdown({ blocks }: { blocks: Block[] }): ReactNode {
  return blocks.map((b, i) => {
    switch (b.t) {
      case "h": {
        const Tag = `h${Math.min(6, b.level)}` as "h2";
        return (
          <Tag key={i} id={headingId(b.c)}>
            <Inlines nodes={b.c} />
          </Tag>
        );
      }
      case "p":
        return (
          <p key={i}>
            <Inlines nodes={b.c} />
          </p>
        );
      case "code":
        return (
          <pre key={i} data-lang={b.lang || undefined}>
            <code>{b.v}</code>
          </pre>
        );
      case "hr":
        return <hr key={i} />;
      case "quote":
        return (
          <blockquote key={i}>
            <Markdown blocks={b.c} />
          </blockquote>
        );
      case "list": {
        const items = b.items.map((item, j) => (
          <li key={j}>
            <Inlines nodes={item} />
          </li>
        ));
        return b.ordered ? (
          <ol key={i} start={b.start}>
            {items}
          </ol>
        ) : (
          <ul key={i}>{items}</ul>
        );
      }
      case "table":
        return (
          <div key={i} className="table-scroll" tabIndex={0} role="region" aria-label="Table">
            <table>
              <thead>
                <tr>
                  {b.head.map((cell, j) => (
                    <th key={j} style={{ textAlign: b.align[j] as "left" }}>
                      <Inlines nodes={cell} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {b.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, j) => (
                      <td key={j} style={{ textAlign: b.align[j] as "left" }}>
                        <Inlines nodes={cell} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
    }
  });
}
