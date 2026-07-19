# OpsVerse MCP Server

Exposes the OpsVerse platform to MCP clients (Claude Desktop, Cursor) as five
tools. It wraps the running API over HTTP, so an MCP session sees exactly what
the web UI sees.

## Tools

| Tool | What it does |
|---|---|
| `search_docs(query, k, tool?)` | Hybrid (dense+sparse) retrieval over the DevOps corpus |
| `ask_opsverse(query, k?)` | Citation-grounded RAG answer |
| `list_eval_reports()` | The platform's own eval reports (retrieval ablations, RAG-quality, security) |
| `get_eval_report(name)` | One report in full |
| `get_costs_summary(hours?)` | Per-model spend & tokens from the request ledger |

## Prerequisite

The OpsVerse stack must be running (API on `:8100`):

```bash
docker compose -f infra/compose/docker-compose.yml up -d --wait
uv run uvicorn opsverse_api.main:app --port 8100
```

Override the target with `OPSVERSE_API_URL` (default `http://localhost:8100`).

## Run it directly

```bash
uv run opsverse-mcp        # stdio server; speaks MCP on stdin/stdout
```

## Claude Desktop

Add to `claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/`, Windows:
`%APPDATA%\Claude\`), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "opsverse": {
      "command": "uv",
      "args": ["run", "--directory", "C:/Users/Dilip/OneDrive/Pictures/ftrag", "opsverse-mcp"],
      "env": { "OPSVERSE_API_URL": "http://localhost:8100" }
    }
  }
}
```

Then in Claude: *"Use opsverse to search for how a Kubernetes HPA scales on
custom metrics"* or *"Ask opsverse what Terraform state locking is and cite
sources."*

## Cursor

`Settings → MCP → Add new server`, or add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "opsverse": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/ftrag", "opsverse-mcp"]
    }
  }
}
```

## Notes

- The server exits cleanly if the API is unreachable per-call (tools return the
  upstream error), so a stopped stack doesn't crash the MCP session.
- Auth for a remote (SSE) transport is out of scope for the local demo; stdio
  runs as the user, no keys needed.
