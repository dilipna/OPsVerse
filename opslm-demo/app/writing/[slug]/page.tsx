import type { Metadata } from "next";
import { notFound } from "next/navigation";
import "../writing.css";
import type { Block } from "../../../lib/markdown.mjs";
import { inlineText } from "../../../lib/markdown.mjs";
import writing from "../../../public/writing.json";
import SiteHeader from "../../SiteHeader";
import Markdown, { headingId } from "../Markdown";

type Post = (typeof writing.posts)[number] & { blocks: Block[] };
const posts = writing.posts as Post[];

export const dynamicParams = false;

export function generateStaticParams() {
  return posts.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = posts.find((p) => p.slug === slug);
  if (!post) return {};
  return {
    title: `${post.title} · RYPE`,
    description: post.excerpt,
    alternates: post.canonical ? { canonical: post.canonical } : undefined,
    openGraph: { title: post.title, description: post.excerpt, type: "article" },
  };
}

export default async function PostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const i = posts.findIndex((p) => p.slug === slug);
  if (i === -1) notFound();
  const post = posts[i];
  const prev = posts[i - 1];
  const next = posts[i + 1];
  const toc = post.blocks.filter(
    (b): b is Extract<Block, { t: "h" }> => b.t === "h" && b.level === 2,
  );

  return (
    <div className="navigator writing-page">
      <SiteHeader section="writing" current="/writing" />
      <main className="post-layout">
        <article className="post">
          <p className="eyebrow">
            <a href="/writing">WRITING</a> / {post.n} · {post.minutes} MIN READ
          </p>
          <h1>{post.title}</h1>
          <p className="post-meta">
            <b className={`badge ${post.status}`}>
              {post.status === "published"
                ? "Published"
                : post.status === "draft"
                  ? "Draft"
                  : "In the repository"}
            </b>
            {post.canonical && (
              <a href={post.canonical} rel="noopener noreferrer">
                Originally on Hashnode ↗
              </a>
            )}
            <a href={post.source}>Source on GitHub ↗</a>
          </p>
          <div className="prose">
            <Markdown blocks={post.blocks} />
          </div>
          <nav className="post-pager" aria-label="More posts">
            {prev ? (
              <a href={`/writing/${prev.slug}`}>
                <small>← {prev.n}</small>
                {prev.title}
              </a>
            ) : (
              <span />
            )}
            {next ? (
              <a href={`/writing/${next.slug}`} className="next">
                <small>{next.n} →</small>
                {next.title}
              </a>
            ) : (
              <span />
            )}
          </nav>
        </article>
        {toc.length > 2 && (
          <aside className="post-toc" aria-label="On this page">
            <p className="eyebrow">ON THIS PAGE</p>
            <ol>
              {toc.map((h) => (
                <li key={headingId(h.c)}>
                  <a href={`#${headingId(h.c)}`}>{inlineText(h.c)}</a>
                </li>
              ))}
            </ol>
          </aside>
        )}
      </main>
    </div>
  );
}
