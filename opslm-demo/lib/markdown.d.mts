export type Inline =
  | { t: "text"; v: string }
  | { t: "code"; v: string }
  | { t: "strong"; c: Inline[] }
  | { t: "em"; c: Inline[] }
  | { t: "link"; href: string; c: Inline[] };
export type Block =
  | { t: "h"; level: number; c: Inline[] }
  | { t: "p"; c: Inline[] }
  | { t: "code"; lang: string; v: string }
  | { t: "hr" }
  | { t: "quote"; c: Block[] }
  | { t: "table"; head: Inline[][]; align: string[]; rows: Inline[][][] }
  | { t: "list"; ordered: boolean; start: number; items: Inline[][] };
export function parseInline(src: string): Inline[];
export function parseMarkdown(markdown: string): Block[];
export function inlineText(nodes: Inline[]): string;
