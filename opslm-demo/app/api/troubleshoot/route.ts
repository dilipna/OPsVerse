import corpus from "../../../public/runbooks.json";
import {handleRequest} from "../../../lib/troubleshoot-http.mjs";

export const runtime="nodejs";
export const maxDuration=60;
export async function GET() {
  return Response.json({generation_configured:Boolean(process.env.OPSVERSE_TROUBLESHOOT_ENDPOINT),
    note:"Configuration does not establish model availability. The public browser workflow needs no model."});
}
export async function POST(request:Request) {
  return handleRequest(request,{corpus,
    endpoint:process.env.OPSVERSE_TROUBLESHOOT_ENDPOINT,
    apiKey:process.env.OPSVERSE_TROUBLESHOOT_API_KEY,
    model:process.env.OPSVERSE_TROUBLESHOOT_MODEL??"opslm"});
}
