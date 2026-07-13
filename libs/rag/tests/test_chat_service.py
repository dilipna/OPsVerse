from opsverse_core.llm import LLMDelta, LLMError, LLMResult
from opsverse_rag.chat import (
    ChatDelta,
    ChatDone,
    ChatError,
    ChatService,
    ChatSources,
    ChatTurn,
    build_context,
    build_messages,
    extract_citations,
)
from opsverse_rag.schemas import RetrievedChunk


def make_chunk(i: int, text: str = "some text") -> RetrievedChunk:
    return RetrievedChunk(
        id=f"c{i}", score=0.9, text=text, source=f"doc{i}.md", section="Intro", document_id=f"d{i}"
    )


class FakeRetriever:
    def __init__(self, *, fail_rerank: bool = False, fail_all: bool = False, chunks=None):
        self.fail_rerank = fail_rerank
        self.fail_all = fail_all
        self.chunks = chunks if chunks is not None else [make_chunk(1), make_chunk(2)]
        self.calls: list[dict] = []

    async def search(self, query, *, k=6, rerank=False, filters=None, **kwargs):
        self.calls.append({"k": k, "rerank": rerank})
        if self.fail_all or (self.fail_rerank and rerank):
            raise RuntimeError("boom")
        return self.chunks


class FakeLLM:
    def __init__(self, deltas: list[str], *, fail: bool = False):
        self.deltas = deltas
        self.fail = fail
        self.messages = None

    async def stream(self, messages):
        self.messages = messages
        if self.fail:
            raise LLMError("all models failed")
        for d in self.deltas:
            yield LLMDelta(text=d)
        yield LLMResult(
            text="".join(self.deltas),
            model="gemini/gemini-2.5-flash",
            prompt_tokens=100,
            completion_tokens=20,
            cost_usd=0.0001,
        )


def test_build_context_numbers_blocks():
    ctx = build_context([make_chunk(1, "alpha"), make_chunk(2, "beta")])
    assert "[1] doc1.md — Intro\nalpha" in ctx
    assert "[2] doc2.md — Intro\nbeta" in ctx


def test_build_messages_grounded_vs_ungrounded():
    grounded = build_messages("q?", [make_chunk(1)], [])
    assert "ONLY the numbered context blocks" in grounded[0]["content"]
    assert grounded[-1]["content"].startswith("Context blocks:")

    ungrounded = build_messages("q?", [], [])
    assert "knowledge base is unreachable" in ungrounded[0]["content"]
    assert ungrounded[-1]["content"] == "q?"


def test_build_messages_bounds_history():
    history = [ChatTurn(role="user", content=f"t{i}") for i in range(20)]
    messages = build_messages("q?", [], history)
    # system + 8 history turns + user question
    assert len(messages) == 10


def test_extract_citations_dedupes_and_bounds():
    assert extract_citations("uses [1] and [2][1], not [7] or [99]", 3) == [1, 2]
    assert extract_citations("no citations here", 3) == []


async def collect(service, query="how do I configure X?"):
    return [event async for event in service.stream_chat(query)]


async def test_full_pipeline_happy_path():
    llm = FakeLLM(["Use X ", "[1]."])
    service = ChatService(FakeRetriever(), llm, context_k=2)
    events = await collect(service)

    sources = events[0]
    assert isinstance(sources, ChatSources)
    assert [s.index for s in sources.sources] == [1, 2]
    assert sources.degraded == []

    deltas = [e for e in events if isinstance(e, ChatDelta)]
    assert "".join(d.text for d in deltas) == "Use X [1]."

    done = events[-1]
    assert isinstance(done, ChatDone)
    assert done.cited == [1]
    assert done.prompt_tokens == 100
    assert done.first_token_ms is not None
    assert done.degraded == []


async def test_rerank_failure_degrades_not_fails():
    retriever = FakeRetriever(fail_rerank=True)
    service = ChatService(retriever, FakeLLM(["ok [2]"]))
    events = await collect(service)

    sources = events[0]
    assert isinstance(sources, ChatSources)
    assert sources.degraded == ["rerank_skipped"]
    assert len(sources.sources) == 2
    assert [c["rerank"] for c in retriever.calls] == [True, False]

    done = events[-1]
    assert isinstance(done, ChatDone)
    assert done.degraded == ["rerank_skipped"]


async def test_retrieval_failure_answers_ungrounded():
    service = ChatService(FakeRetriever(fail_all=True), llm := FakeLLM(["general answer"]))
    events = await collect(service)

    sources = events[0]
    assert isinstance(sources, ChatSources)
    assert sources.sources == []
    assert sources.degraded == ["rerank_skipped", "retrieval_skipped"]

    assert llm.messages is not None
    assert "knowledge base is unreachable" in llm.messages[0]["content"]
    done = events[-1]
    assert isinstance(done, ChatDone)
    assert done.cited == []


async def test_llm_failure_yields_error_event():
    service = ChatService(FakeRetriever(), FakeLLM([], fail=True))
    events = await collect(service)
    assert isinstance(events[0], ChatSources)
    error = events[-1]
    assert isinstance(error, ChatError)
    assert "generation failed" in error.message
