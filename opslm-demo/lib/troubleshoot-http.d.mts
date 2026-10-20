import type {Corpus} from "./runbooks.mjs";
export function handleRequest(request:Request,options:{corpus:Corpus;endpoint?:string;apiKey?:string;model?:string;fetcher?:typeof fetch;timeoutMs?:number}):Promise<Response>;
