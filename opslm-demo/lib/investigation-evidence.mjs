import {search} from "./runbooks.mjs";

// A bounded lexical policy over the pinned corpus, not an answerability judge.
// One initial retrieval plus at most three missing-family retries. Results never
// instruct an executor and cannot expand the caller's document/context budgets.
export function investigationEvidence(corpus,query,signals){
  const initial=search(corpus,query,3);
  const attempts=[{kind:"initial",query,returned:initial.map(s=>s.id)}];
  const families=[...new Set(signals.map(s=>s.document))];
  const candidates=[];
  for(const family of families){
    let source=initial.find(s=>s.document===family);
    if(!source && attempts.length<4){
      const scoped={...corpus,chunks:corpus.chunks.filter(s=>s.document===family)};
      const scopedQuery=signals.filter(s=>s.document===family).map(s=>s.query).join(" ").slice(0,500);
      const found=search(scoped,scopedQuery,1);
      attempts.push({kind:"missing_family",family,query:scopedQuery,returned:found.map(s=>s.id)});
      source=found[0];
    }
    if(source)candidates.push(source);
  }
  // Preserve represented families from the baseline before filling missing ones;
  // a tight budget must not silently replace all previously covered evidence.
  const represented=candidates.filter(s=>initial.some(p=>p.document===s.document));
  const additions=candidates.filter(s=>!initial.some(p=>p.document===s.document));
  // Reserve one slot per observed family before adding redundant passages.
  const selected=[];
  for(const source of [...represented,...additions,...initial]){
    if(selected.length===3)break;
    if(!selected.some(s=>s.id===source.id))selected.push(source);
  }
  let remaining=6000;
  const sources=selected.map(s=>{
    const text=s.text.slice(0,Math.min(2500,remaining));remaining-=text.length;
    return {...s,text};
  }).filter(s=>s.text.length>=20);
  const coverage=signals.map(s=>({signal:s.label,document:s.document,
    source_ids:sources.filter(p=>p.document===s.document).map(p=>p.id)}));
  return {sources,evidence_policy:{version:1,strategy:"bounded-signal-family",attempts,
    coverage,missing_signals:coverage.filter(c=>!c.source_ids.length).map(c=>c.signal),
    limits:{passages:3,characters:6000,retrieval_attempts:4},
    usage:{passages:sources.length,characters:sources.reduce((n,s)=>n+s.text.length,0),retrieval_attempts:attempts.length},
    omitted:selected.filter(s=>sources.find(p=>p.id===s.id)?.text.length<s.text.length)
      .map(s=>({source_id:s.id,reason:"character_budget"})),
    scope:"Document-family presence only; passages may not support the requested conclusion. Missing signals require further evidence; no root cause is confirmed."}};
}
