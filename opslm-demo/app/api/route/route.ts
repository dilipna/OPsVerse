import corpus from "../../../public/runbooks.json";
import {handleRypeRequest,routingMetadata} from "../../../lib/rype-http.mjs";
export const runtime="nodejs";
export const maxDuration=60;
const apiKey=()=>process.env.RYPE_OPENROUTER_API_KEY||process.env.OPENROUTER_API_KEY;
export async function GET(){return Response.json(await routingMetadata({apiKey:apiKey()}),{headers:{"Cache-Control":"no-store"}});}
export async function POST(request:Request){return handleRypeRequest(request,{corpus,apiKey:apiKey()});}
