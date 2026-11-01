import {validateLibrary} from "./knowledge.mjs";
const DB="rype-private-library-v1",STORE="library";
async function open(){return new Promise((resolve,reject)=>{const r=indexedDB.open(DB,1);r.onupgradeneeded=()=>r.result.createObjectStore(STORE);r.onerror=()=>reject(Error("Private storage is unavailable. Your documents were not saved."));r.onblocked=()=>reject(Error("Close other RYPE tabs, then retry opening your library."));r.onsuccess=()=>resolve(r.result);});}
async function transact(change){
  const db=await open();
  try{return await new Promise((resolve,reject)=>{const tx=db.transaction(STORE,change?"readwrite":"readonly"),store=tx.objectStore(STORE),request=store.get("documents");let result=[];
    request.onsuccess=()=>{try{const current=validateLibrary(request.result||[]);result=change?validateLibrary(change(current)):current;if(change)store.put(result,"documents");}catch(e){reject(e);tx.abort();}};
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(Error("Storage failed or is full. No change was saved; export a backup before retrying."));tx.onabort=()=>reject(Error("The library update was not saved."));
  });}finally{db.close();}
}
export async function readLibrary(){return transact();}
export async function addDocuments(documents){return transact(current=>{const next=[...current];for(const d of documents){if(next.some(x=>x.id===d.id))throw Error(`Already saved: ${d.name}`);next.push(d);}return next;});}
export async function removeDocument(id){return transact(current=>current.filter(d=>d.id!==id));}
export async function clearLibrary(){return transact(()=>[]);}
