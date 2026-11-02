import type { Metadata } from "next";
import "./writing.css";
import writing from "../../public/writing.json";
import SiteHeader from "../SiteHeader";

export const metadata: Metadata = {
  title: "RYPE · Writing",
  description:
    "Write-ups from building and attacking RYPE: evaluation-first retrieval, RAG security at ingest, serving benchmarks, auditing an LLM judge, and a detector that failed a zero-width space.",
};

const STATUS: Record<string, string> = {
  published: "Published",
  draft: "Draft",
  repo: "In the repository",
};

export default function WritingIndex() {
  const posts = [...writing.posts].reverse();
  return (
    <div className="navigator writing-page">
      <SiteHeader section="writing" current="/writing" />
      <main>
        <section className="intro">
          <p className="eyebrow">WRITING / WHAT I LEARNED</p>
          <h1>
            The numbers changed my mind.
            <br />
            <span>Here is where, and why.</span>
          </h1>
          <p className="intro-copy">
            Each post is tied to committed reports in the repository. Several are about results that
            did not survive a harder test. Posts 01–04 were written when the project was called
            OpsVerse.
          </p>
        </section>
        <ol className="post-list">
          {posts.map((p) => (
            <li key={p.slug}>
              <a href={`/writing/${p.slug}`}>
                <span className="post-n">{p.n}</span>
                <span className="post-main">
                  <strong>{p.title}</strong>
                  <span>{p.excerpt}</span>
                  <small>
                    <b className={`badge ${p.status}`}>{STATUS[p.status]}</b> · {p.minutes} min read
                  </small>
                </span>
                <i aria-hidden="true">→</i>
              </a>
            </li>
          ))}
        </ol>
      </main>
    </div>
  );
}
