import type {Corpus} from "./runbooks.mjs";
import type {Input,Result} from "./troubleshoot.mjs";
import type {RoutingMetadata} from "./rype-routing.mjs";
import type {PrivateDocument} from "./knowledge.mjs";
export function workspaceRoute(corpus:Corpus,input:Input,metadata?:RoutingMetadata|null,options?:{documents?:PrivateDocument[];restored?:boolean}):Promise<Result>;
