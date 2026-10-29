import type {PrivateDocument} from "./knowledge.mjs";
export function readLibrary():Promise<PrivateDocument[]>;
export function addDocuments(documents:PrivateDocument[]):Promise<PrivateDocument[]>;
export function removeDocument(id:string):Promise<PrivateDocument[]>;
export function clearLibrary():Promise<PrivateDocument[]>;
