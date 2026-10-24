import {prepare,completeInvestigation} from "./troubleshoot.mjs";

export async function handleRequest(request, {corpus,endpoint,apiKey,model="opslm",fetcher=fetch,timeoutMs=55000}) {
  // Bound bytes while reading, before allocating an arbitrarily large string.
  const reader=request.body?.getReader(),decoder=new TextDecoder();
  let text="",bytes=0;
  if(reader){
    try{
      while(true){
        const {value,done}=await reader.read();if(done)break;
        bytes+=value.byteLength;
        if(bytes>24000){await reader.cancel();return Response.json({error:"Request is too large."},{status:413});}
        text+=decoder.decode(value,{stream:true});
      }
      text+=decoder.decode();
    }catch{return Response.json({error:"The request body could not be read."},{status:400});}
    finally{reader.releaseLock();}
  }
  let input;
  try {input=JSON.parse(text);}catch{return Response.json({error:"Send a valid JSON request."},{status:400});}
  // Keep input/schema errors separate from model/upstream failures.
  let prepared;
  try {prepared=prepare(corpus,input);}catch(e){return Response.json({error:e.message},{status:400});}
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
  try{return Response.json(await completeInvestigation(prepared,generate));}
  catch{return Response.json({error:"The model failed or its response did not pass evidence validation. No generated answer was accepted. Inspect the retrieved passages or retry."},{status:502});}
}
