"""OpsVerse MCP server (stdio): the platform's search/chat/evals/costs as tools.

Requires the OpsVerse stack to be running (API on :8100 by default; override
with OPSVERSE_API_URL). Claude Desktop config example lives in the README
section "MCP server".

Run directly:  uv run opsverse-mcp
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from opsverse_mcp import client as api

mcp = FastMCP(
    "opsverse",
    instructions=(
        "OpsVerse is a DevOps/MLOps documentation RAG platform (Kubernetes, "
        "Docker, Terraform, MLflow). Use search_docs for raw retrieval, "
        "ask_opsverse for citation-grounded answers, and the eval/cost tools "
        "to inspect the platform's own measured quality and spend."
    ),
)


@mcp.tool()
async def search_docs(query: str, k: int = 6, tool: str | None = None) -> list[dict[str, Any]]:
    """Hybrid (dense+sparse) search over the ingested DevOps documentation corpus.

    Args:
        query: what to search for
        k: number of chunks to return (1-20)
        tool: optional filter — one of kubernetes, docker, terraform, mlflow
    """
    async with api.build_client() as client:
        return await api.search_docs(client, query, k=min(max(k, 1), 20), tool=tool)


@mcp.tool()
async def ask_opsverse(question: str) -> dict[str, Any]:
    """Ask the OpsVerse RAG assistant. Returns a citation-grounded answer plus
    the sources it cited. Uses the live LLM (free-tier quota) — prefer
    search_docs when raw documentation excerpts are enough."""
    async with api.build_client() as client:
        return await api.ask(client, question)


@mcp.tool()
async def list_eval_reports() -> list[dict[str, Any]]:
    """List the platform's evaluation reports (retrieval ablations, RAG answer
    quality, security red-team) — name, kind, and date."""
    async with api.build_client() as client:
        return await api.list_eval_reports(client)


@mcp.tool()
async def get_eval_report(name: str) -> dict[str, Any]:
    """Fetch one evaluation report by name (e.g. retrieval-ablation-v3) with
    its full measured results table."""
    async with api.build_client() as client:
        return await api.get_eval_report(client, name)


@mcp.tool()
async def get_costs_summary(hours: int = 168) -> dict[str, Any]:
    """LLM spend/token/latency summary from the request ledger over the last
    N hours (default: one week), total and per model."""
    async with api.build_client() as client:
        return await api.get_costs_summary(client, hours=hours)


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
