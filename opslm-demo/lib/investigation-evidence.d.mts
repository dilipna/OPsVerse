import type {Corpus,Chunk} from "./runbooks.mjs";
export type EvidencePolicy={version:1;strategy:"bounded-signal-family";
  attempts:{kind:string;family?:string;query:string;returned:string[]}[];
  coverage:{signal:string;document:string;source_ids:string[]}[];missing_signals:string[];
  limits:{passages:number;characters:number;retrieval_attempts:number};
  usage:{passages:number;characters:number;retrieval_attempts:number};
  omitted:{source_id:string;reason:string}[];scope:string};
export function investigationEvidence(corpus:Corpus,query:string,signals:{label:string;query:string;document:string}[]):{sources:Chunk[];evidence_policy:EvidencePolicy};
