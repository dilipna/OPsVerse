import {troubleshoot} from "./troubleshoot.mjs";

export async function handleRequest(request, {corpus,endpoint,apiKey,model="opslm",fetcher=fetch,timeoutMs=55000}) {
  const text=await request.text();
  if(new TextEncoder().encode(text).length>24000)return Response.json({error:"Request is too large."},{status:413});
  let input;
  try {input=JSON.parse(text);}catch{return Response.json({error:"Send a valid JSON request."},{status:400});}
  // Keep input/schema errors separate from model/upstream failures.
  try {await troubleshoot(corpus,input);}catch(e){return Response.json({error:e.message},{status:400});}
  const generate=endpoint ? async messages=>{
    const response=await fetcher(endpoint.replace(/\/$/,"")+"/chat/completions",{
      method:"POST",headers:{"content-type":"application/json",...(apiKey?{authorization:`Bearer ${apiKey}`}:{})},
      signal:AbortSignal.timeout(timeoutMs),
      body:JSON.stringify({model,messages,temperature:0,seed:42,max_tokens:384,stream:false})
    });
    if(!response.ok)throw new Error("upstream unavailable");
    const data=await response.json(),choice=data?.choices?.[0];
    if(typeof choice?.message?.content!=="string")throw new Error("empty upstream response");
    return {text:choice.message.content,finish_reason:choice.finish_reason,model:data.model??model,usage:data.usage??null};
  }:undefined;
  try{return Response.json(await troubleshoot(corpus,input,generate));}
  catch{return Response.json({error:"The model failed or its response did not pass evidence validation. No generated answer was accepted. Inspect the retrieved passages or retry."},{status:502});}
}
