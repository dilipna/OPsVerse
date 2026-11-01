export type Chunk = {id:string; document:string; section:string; text:string; source:string; canonical:string;origin?:string};
export type Corpus = {schema:number; chunks:Chunk[]; manifest:{revision:string; retrieved_at:string; documents:unknown[]}};
export function terms(text:string):string[];
export function search(corpus:Corpus, query:string, limit?:number, mode?:string):(Chunk & {score:number; matched:number})[];
