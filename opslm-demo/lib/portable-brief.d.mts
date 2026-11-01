import type {Corpus} from "./runbooks.mjs";
import type {Result} from "./troubleshoot.mjs";
export const MAX_BRIEF_BYTES:number;
export const SAVED_GUIDES_KEY:string;
export type Brief=Result & {schema_version:number;created_at:string;review:{status:string;notes:string;notes_redactions:number};source_revision:string;boundary:string};
export function createBrief(result:Result,notes:string,revision:string,createdAt?:string):Brief;
export function restoreBrief(text:string,corpus:Corpus):{issue:string;diagnostics:string;notes:string};
export function markdownBrief(brief:Brief):string;
export function savedGuideIds(text:string|null,corpus:Corpus):string[];
