"""OpenAI-compatible server for OpsLM on a free HF Space (CPU).

Loads the committed GGUF (Q4_K_M) from the Hub with llama.cpp and exposes
`/v1/chat/completions`, so the Vercel demo site can point `OPSLM_ENDPOINT` at
`https://<user>-opslm.hf.space/v1`. CPU inference is slow-but-free by design.
"""

import os

from fastapi import FastAPI
from huggingface_hub import hf_hub_download
from llama_cpp import Llama
from pydantic import BaseModel

MODEL_REPO = os.environ.get("OPSLM_REPO", "dhf1234/OpsLM-v1")
GGUF_FILE = os.environ.get("OPSLM_GGUF", "qwen3-4b-base.Q4_K_M.gguf")
N_THREADS = int(os.environ.get("OPSLM_THREADS", "2"))  # free Space = 2 vCPU
N_CTX = int(os.environ.get("OPSLM_CTX", "2048"))

app = FastAPI(title="OpsLM inference")
_llm: Llama | None = None


def get_llm() -> Llama:
    global _llm
    if _llm is None:
        path = hf_hub_download(repo_id=MODEL_REPO, filename=GGUF_FILE)
        _llm = Llama(
            model_path=path,
            n_ctx=N_CTX,
            n_threads=N_THREADS,
            chat_format="chatml",  # Qwen3 uses a ChatML-style template
            verbose=False,
        )
    return _llm


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "opslm"
    messages: list[Message]
    temperature: float = 0.3
    max_tokens: int = 512


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": MODEL_REPO, "gguf": GGUF_FILE}


@app.post("/v1/chat/completions")
def chat_completions(req: ChatRequest) -> dict:
    llm = get_llm()
    out = llm.create_chat_completion(
        messages=[m.model_dump() for m in req.messages],
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    # llama.cpp already returns the OpenAI chat-completion shape.
    return out
