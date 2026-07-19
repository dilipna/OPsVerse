import json

import httpx

from opsverse_mcp import client as api


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://t", transport=httpx.MockTransport(handler), timeout=5)


async def test_search_docs_trims_hits_and_passes_tool_filter():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "id": "c1",
                        "document_id": "d1",
                        "score": 0.9,
                        "source": "k8s.md",
                        "section": "HPA",
                        "tool": "kubernetes",
                        "doc_type": "markdown",
                        "language": None,
                        "text": "HPA scales pods",
                    }
                ]
            },
        )

    async with mock_client(handler) as client:
        hits = await api.search_docs(client, "hpa", k=3, tool="kubernetes")
    assert captured["body"] == {"query": "hpa", "k": 3, "filters": {"tool": "kubernetes"}}
    assert hits == [
        {
            "source": "k8s.md",
            "section": "HPA",
            "tool": "kubernetes",
            "score": 0.9,
            "text": "HPA scales pods",
        }
    ]


async def test_ask_returns_answer_with_citations():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "answer": "Use an HPA [1].",
                "sources": {
                    "sources": [
                        {
                            "index": 1,
                            "id": "c1",
                            "source": "k8s.md",
                            "section": "HPA",
                            "score": 0.9,
                            "text": "...",
                        }
                    ]
                },
                "done": {"model": "m", "cited": [1], "latency_ms": 10.0},
                "error": None,
            },
        )

    async with mock_client(handler) as client:
        result = await api.ask(client, "how to autoscale?")
    assert result["answer"] == "Use an HPA [1]."
    assert result["citations"] == [{"index": 1, "source": "k8s.md", "section": "HPA"}]
    assert result["cited_indices"] == [1]


async def test_ask_surfaces_upstream_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "answer": "",
                "sources": {"sources": []},
                "done": None,
                "error": "generation failed: boom",
            },
        )

    async with mock_client(handler) as client:
        result = await api.ask(client, "q")
    assert result == {"error": "generation failed: boom"}


async def test_reports_roundtrip():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/evals/reports":
            return httpx.Response(
                200,
                json=[
                    {
                        "report": "retrieval-ablation-v3",
                        "kind": "retrieval-ablation",
                        "date": "2026-07-17",
                        "results": {},
                    }
                ],
            )
        return httpx.Response(200, json={"report": "retrieval-ablation-v3", "results": {}})

    async with mock_client(handler) as client:
        listed = await api.list_eval_reports(client)
        one = await api.get_eval_report(client, "retrieval-ablation-v3")
    assert listed == [
        {"report": "retrieval-ablation-v3", "kind": "retrieval-ablation", "date": "2026-07-17"}
    ]
    assert one["report"] == "retrieval-ablation-v3"
