import type {Corpus} from "./runbooks.mjs";
import type {RoutingMetadata} from "./rype-routing.mjs";
export function routingMetadata(options?:{apiKey?:string;fetcher?:typeof fetch;now?:number;cache?:boolean}):Promise<RoutingMetadata>;
export function handleRypeRequest(request:Request,options:{corpus:Corpus;apiKey?:string;metadata?:RoutingMetadata;fetcher?:typeof fetch;timeoutMs?:number}):Promise<Response>;
