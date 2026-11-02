export type AskChunk = { id: string; path: string; title: string; heading: string; text: string };
export type AskIndex = { chunks: AskChunk[] };
export function stem(t: string): string;
export function tokenize(text: string): string[];
export function chunkMarkdown(path: string, markdown: string, max?: number): AskChunk[];
export function cleanMarkdown(text: string): string;
export function buildIndex(chunks: AskChunk[]): AskIndex;
export function ask(
  index: AskIndex,
  question: string,
  k?: number,
): { chunk: AskChunk; score: number; matched: number }[];
export function bestSentence(text: string, question: string): string;
export function evaluate(
  index: AskIndex,
  questions: { q: string; expect: string[] }[],
  k?: number,
): { n: number; hit1: number; hitk: number; k: number; rows: unknown[] };
