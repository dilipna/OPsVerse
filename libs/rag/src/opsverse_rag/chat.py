"""Citation-grounded RAG chat: retrieval -> numbered context prompt -> streamed answer.

Degradation ladder (see docs/latency-budget.md):
  1. hybrid retrieval + rerank        (full quality)
  2. hybrid retrieval, no rerank      (rerank failed or timed out)
  3. no retrieval, ungrounded answer  (retrieval failed; answer carries a warning)
  4. error event                      (the LLM itself failed)
Each step down is recorded in the `degraded` list on the sources/done events.
"""

import re
import time
from collections.abc import AsyncIterator
from typing import Literal, Protocol

import anyio
from pydantic import BaseModel

from opsverse_core.llm import LLMDelta, LLMResult, LLMStreamEvent, Message
from opsverse_core.tracing import NullTracer, Tracer
from opsverse_rag.schemas import RetrievedChunk, SearchFilters

GROUNDED_SYSTEM_PROMPT = """\
You are OpsVerse, an assistant for DevOps, MLOps, and platform engineering questions.
Answer using ONLY the numbered context blocks provided with the question.
Cite the blocks you use inline with bracketed numbers, e.g. [1] or [2][3], placed
right after the statement they support. Do not invent citations.
If the context does not contain enough information to answer, say so plainly and
do not guess. Prefer concrete configuration examples from the context over
generic advice. Answer in Markdown."""

UNGROUNDED_SYSTEM_PROMPT = """\
You are OpsVerse, an assistant for DevOps, MLOps, and platform engineering questions.
Document retrieval is currently unavailable, so you have NO context from the
knowledge base. Start your answer with exactly this line:
> Note: answering from general knowledge; the knowledge base is unreachable.
Then answer from general knowledge, being explicit about anything you are
unsure of. Answer in Markdown."""

IMAGE_DESCRIPTION_PROMPT = """\
Describe this image for a DevOps documentation search engine. Focus on what is
technically identifiable: technologies, error messages, commands, configuration
keys/values, architecture components and their relationships. Transcribe any
visible text exactly. 2-6 sentences, no preamble."""

MAX_HISTORY_TURNS = 8
_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SourceInfo(BaseModel):
    index: int  # the [n] number used in the answer
    id: str
    source: str
    section: str | None = None
    tool: str | None = None
    doc_type: str | None = None
    score: float
    rerank_score: float | None = None
    text: str


class ChatSources(BaseModel):
    type: Literal["sources"] = "sources"
    sources: list[SourceInfo]
    image_description: str | None = None
    degraded: list[str] = []


class ChatDelta(BaseModel):
    type: Literal["delta"] = "delta"
    text: str


class ChatDone(BaseModel):
    type: Literal["done"] = "done"
    model: str
    cited: list[int]  # which [n] source indices the answer actually used
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float
    first_token_ms: float | None = None
    degraded: list[str] = []


class ChatError(BaseModel):
    type: Literal["error"] = "error"
    message: str


ChatEvent = ChatSources | ChatDelta | ChatDone | ChatError


class SupportsStream(Protocol):
    def stream(self, messages: list[Message]) -> AsyncIterator[LLMStreamEvent]: ...

    async def complete(self, messages: list[Message]) -> LLMResult: ...


class SupportsSearch(Protocol):
    async def search(
        self,
        query: str,
        *,
        k: int = ...,
        rerank: bool = ...,
        filters: SearchFilters | None = ...,
    ) -> list[RetrievedChunk]: ...


def build_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, chunk in enumerate(chunks, 1):
        header = f"[{i}] {chunk.source}"
        if chunk.section:
            header += f" — {chunk.section}"
        blocks.append(f"{header}\n{chunk.text}")
    return "\n\n".join(blocks)


def build_messages(
    query: str,
    chunks: list[RetrievedChunk],
    history: list[ChatTurn],
    image_description: str | None = None,
) -> list[Message]:
    system = GROUNDED_SYSTEM_PROMPT if chunks else UNGROUNDED_SYSTEM_PROMPT
    messages: list[Message] = [{"role": "system", "content": system}]
    for turn in history[-MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    parts: list[str] = []
    if chunks:
        parts.append(f"Context blocks:\n\n{build_context(chunks)}")
    if image_description:
        parts.append(f"The user attached an image. Description:\n{image_description}")
    parts.append(f"Question: {query}" if parts else query)
    messages.append({"role": "user", "content": "\n\n".join(parts)})
    return messages


def extract_citations(answer: str, n_sources: int) -> list[int]:
    """Source indices ([1]-based) the answer actually cited, in order."""
    seen: list[int] = []
    for match in _CITATION_RE.finditer(answer):
        idx = int(match.group(1))
        if 1 <= idx <= n_sources and idx not in seen:
            seen.append(idx)
    return seen


class ChatService:
    def __init__(
        self,
        retriever: SupportsSearch,
        llm: SupportsStream,
        *,
        context_k: int = 6,
        retrieval_timeout_s: float = 10.0,
        rerank: bool = False,
        tracer: Tracer | None = None,
    ):
        self._retriever = retriever
        self._llm = llm
        self._context_k = context_k
        self._retrieval_timeout_s = retrieval_timeout_s
        # Off by default: the v1 retrieval ablation measured the CPU
        # cross-encoder as slightly quality-negative at ~9s/query.
        self._rerank = rerank
        # NullTracer by default: tracing is a no-op unless Langfuse is wired.
        self._tracer: Tracer = tracer or NullTracer()

    async def _retrieve(
        self, query: str, k: int, filters: SearchFilters | None
    ) -> tuple[list[RetrievedChunk], list[str]]:
        """Steps 1-3 of the ladder: (rerank ->) no rerank -> no retrieval."""
        degraded: list[str] = []
        attempts = (True, False) if self._rerank else (False,)
        for rerank in attempts:
            try:
                with anyio.fail_after(self._retrieval_timeout_s):
                    chunks = await self._retriever.search(
                        query, k=k, rerank=rerank, filters=filters
                    )
                return chunks, degraded
            except Exception:
                degraded.append("rerank_skipped" if rerank else "retrieval_skipped")
        return [], degraded

    async def describe_image(self, image_b64: str, mime: str) -> str:
        result = await self._llm.complete(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": IMAGE_DESCRIPTION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                        },
                    ],
                }
            ]
        )
        return result.text.strip()

    async def stream_chat(
        self,
        query: str,
        *,
        history: list[ChatTurn] | None = None,
        k: int | None = None,
        filters: SearchFilters | None = None,
        image_b64: str | None = None,
        image_mime: str = "image/png",
    ) -> AsyncIterator[ChatEvent]:
        started = time.perf_counter()
        degraded: list[str] = []
        trace = self._tracer.trace(
            "chat",
            input=query,
            metadata={"has_image": image_b64 is not None, "k": k or self._context_k},
        )
        image_description: str | None = None
        if image_b64:
            with trace.span("vision", input="<image>") as span:
                try:
                    image_description = await self.describe_image(image_b64, image_mime)
                    span.update(output=image_description)
                except Exception:
                    degraded.append("vision_skipped")
                    span.update(level="WARNING", status_message="vision_skipped")

        # The image description joins the retrieval query so chunks matching
        # what's *in* the image (error text, config keys) are found.
        retrieval_query = f"{query}\n{image_description}" if image_description else query
        with trace.span("retrieval", input=retrieval_query) as span:
            chunks, retrieve_degraded = await self._retrieve(
                retrieval_query, k or self._context_k, filters
            )
            span.update(
                output=[{"id": c.id, "source": c.source, "score": c.score} for c in chunks],
                metadata={"n_chunks": len(chunks), "degraded": retrieve_degraded},
            )
        degraded += retrieve_degraded
        yield ChatSources(
            image_description=image_description,
            sources=[
                SourceInfo(
                    index=i,
                    id=c.id,
                    source=c.source,
                    section=c.section,
                    tool=c.tool,
                    doc_type=c.doc_type,
                    score=c.score,
                    rerank_score=c.rerank_score,
                    text=c.text,
                )
                for i, c in enumerate(chunks, 1)
            ],
            degraded=degraded,
        )

        messages = build_messages(query, chunks, history or [], image_description)
        first_token_ms: float | None = None
        gen_span = trace.span("generation", input=messages, metadata={"grounded": bool(chunks)})
        try:
            async for event in self._llm.stream(messages):
                if isinstance(event, LLMDelta):
                    if first_token_ms is None:
                        first_token_ms = (time.perf_counter() - started) * 1000
                    yield ChatDelta(text=event.text)
                elif isinstance(event, LLMResult):
                    cited = extract_citations(event.text, len(chunks))
                    gen_span.update(
                        output=event.text,
                        metadata={
                            "model": event.model,
                            "prompt_tokens": event.prompt_tokens,
                            "completion_tokens": event.completion_tokens,
                            "cost_usd": event.cost_usd,
                            "first_token_ms": first_token_ms,
                            "cited": cited,
                            "cached": "(cached)" in event.model,
                        },
                    )
                    gen_span.end()
                    trace.update(output=event.text)
                    yield ChatDone(
                        model=event.model,
                        cited=cited,
                        prompt_tokens=event.prompt_tokens,
                        completion_tokens=event.completion_tokens,
                        cost_usd=event.cost_usd,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        first_token_ms=first_token_ms,
                        degraded=degraded,
                    )
        except Exception as exc:  # step 4: the LLM itself failed
            gen_span.update(level="ERROR", status_message=str(exc))
            gen_span.end()
            yield ChatError(message=f"generation failed: {exc}")
        finally:
            self._tracer.flush()
