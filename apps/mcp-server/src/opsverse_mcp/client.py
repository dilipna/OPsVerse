"""Thin HTTP client for the OpsVerse API — the MCP tools call through here.

Deliberately HTTP (not in-process libs): the running API is the single source
of truth for retrieval config, degradation behavior, and the request ledger;
an MCP session should see exactly what the web UI sees. Costs one local hop.
"""

import os
from typing import Any

import httpx

DEFAULT_API = os.environ.get("OPSVERSE_API_URL", "http://localhost:8100")


def build_client(base_url: str = DEFAULT_API) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=180.0)


async def search_docs(
    client: httpx.AsyncClient, query: str, k: int = 6, tool: str | None = None
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {"query": query, "k": k}
    if tool:
        body["filters"] = {"tool": tool}
    resp = await client.post("/v1/search", json=body)
    resp.raise_for_status()
    hits = resp.json()["hits"]
    # trim to what an LLM consumer needs; scores stay for transparency
    return [
        {
            "source": h["source"],
            "section": h.get("section"),
            "tool": h.get("tool"),
            "score": h["score"],
            "text": h["text"],
        }
        for h in hits
    ]


async def ask(client: httpx.AsyncClient, question: str) -> dict[str, Any]:
    resp = await client.post("/v1/chat", json={"query": question, "stream": False})
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        return {"error": data["error"]}
    return {
        "answer": data["answer"],
        "citations": [
            {"index": s["index"], "source": s["source"], "section": s.get("section")}
            for s in data["sources"]["sources"]
        ],
        "cited_indices": data["done"]["cited"] if data.get("done") else [],
    }


async def list_eval_reports(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    resp = await client.get("/v1/evals/reports")
    resp.raise_for_status()
    return [
        {"report": r["report"], "kind": r.get("kind"), "date": r.get("date")} for r in resp.json()
    ]


async def get_eval_report(client: httpx.AsyncClient, name: str) -> dict[str, Any]:
    resp = await client.get(f"/v1/evals/reports/{name}")
    resp.raise_for_status()
    return resp.json()


async def get_costs_summary(client: httpx.AsyncClient, hours: int = 168) -> dict[str, Any]:
    resp = await client.get("/v1/costs/summary", params={"hours": hours})
    resp.raise_for_status()
    return resp.json()
