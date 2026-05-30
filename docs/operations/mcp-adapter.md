# MCP Adapter — Tomorrowland Researcher API

## Overview

The MCP (Model Context Protocol) adapter exposes Tomorrowland's permissioned
researcher API endpoints as MCP tools that any MCP client (including Hermes,
Claude Code, or custom scripts) can call through the standard MCP protocol.

**What it does:**
- Registers six read-only MCP tools that map 1:1 to the `/api/agent/v1/*`
  endpoints from [#558](/issues/558).
- Forwards every tool call as an HTTP request to the Tomorrowland API,
  preserving authentication and authorization.
- Returns JSON-serialised responses that match the researcher API schemas.

**What it does NOT do:**
- No direct database access.
- No direct Qdrant or Meilisearch access.
- No duplicated ACL logic — all authorization happens in the Tomorrowland API.
- No write tools (no create, update, or delete operations).
- No secrets in logs (Authorization headers are redacted).

## Architecture

```text
┌──────────────┐     MCP     ┌──────────────────┐   HTTP    ┌──────────────────┐
│  MCP Client   │ ◄───────── │  MCP Adapter      │ ────────► │  Tomorrowland API │
│  (Hermes,     │   tools    │  (FastMCP server) │  Bearer   │  /api/agent/v1/*  │
│   Claude Code)│            │  localhost:8001   │   auth    │  localhost:8000   │
└──────────────┘            └──────────────────┘           └──────────────────┘
```

The adapter is a **standalone process** that runs alongside the Tomorrowland
API.  It uses the `mcp` Python SDK (v1.x) with **Streamable HTTP** transport.

## Configuration

The adapter reads the following environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `TOMORROWLAND_API_URL` | `http://localhost:8000` | Base URL of the Tomorrowland API |
| `TOMORROWLAND_API_KEY` | *(empty)* | Bearer token for API authentication |
| `TOMORROWLAND_API_TIMEOUT` | `30.0` | HTTP request timeout in seconds |
| `MCP_HOST` | `127.0.0.1` | Address to bind the MCP server |
| `MCP_PORT` | `8001` | Port to bind the MCP server |

## Running

### Standalone (Streamable HTTP)

```bash
# Set required env vars
export TOMORROWLAND_API_URL=http://localhost:8000
export TOMORROWLAND_API_KEY=your-bearer-token

# Run the MCP server
uv run tomorrowland-mcp-server
```

The server starts on `http://127.0.0.1:8001/mcp` with Streamable HTTP transport.

### Connecting Claude Code

```bash
claude mcp add --transport http tomorrowland http://127.0.0.1:8001/mcp
```

### Connecting Hermes

```ini
; hermes.toml
[[mcp_servers]]
name = "tomorrowland"
transport = "http"
url = "http://127.0.0.1:8001/mcp"
api_key = "your-bearer-token"
```

### Air-gapped / local mode

When running in an air-gapped environment, ensure both the Tomorrowland API
and the MCP adapter are running on the same host:

```bash
export TOMORROWLAND_API_URL=http://host.docker.internal:8000
export TOMORROWLAND_API_KEY=$(cat /run/secrets/tomorrowland_api_key)
uv run tomorrowland-mcp-server
```

## Available Tools

The MCP server exposes exactly six tools:

| MCP Tool | HTTP Endpoint | Description |
|----------|--------------|-------------|
| `tomorrowland_search_documents` | `POST /api/agent/v1/search_documents` | Hybrid search (BM25 + vector) |
| `tomorrowland_get_document` | `GET /api/agent/v1/get_document` | Document metadata |
| `tomorrowland_get_passages` | `GET /api/agent/v1/get_passages` | Text passages (chunks) |
| `tomorrowland_ask_corpus` | `POST /api/agent/v1/ask_corpus` | RAG question answering |
| `tomorrowland_get_related_documents` | `GET /api/agent/v1/get_related_documents` | Related document discovery |
| `tomorrowland_list_facets` | `GET /api/agent/v1/list_facets` | Facet distributions |

### Input Validation

Each tool enforces the same input limits as the researcher API:

| Tool | Parameter | Limits |
|------|-----------|--------|
| `search_documents` | `query` | 1–500 characters |
| | `top_k` | 1–50 (default 20) |
| | `page` | 1–20 (default 1) |
| `get_document` | `document_id` | 1–64 characters |
| `get_passages` | `document_id` | 1–64 characters |
| | `limit` | 1–100 (default 50) |
| | `offset` | 0–10000 (default 0) |
| `ask_corpus` | `question` | 1–2000 characters |
| | `top_k` | 1–50 (optional) |
| | `document_id` | 1–64 characters (optional) |
| `get_related_documents` | `document_id` | 1–64 characters |
| `list_facets` | `query` | 0–500 characters (optional) |

## Security

### Authentication

The MCP adapter does **not** authenticate the MCP client itself.  It forwards
the Bearer token received from the MCP client to the Tomorrowland API in the
`Authorization` header.  The Tomorrowland API then applies its standard
JWT-based authentication and ACL enforcement.

**Never log the Authorization header.**  The adapter explicitly redacts
sensitive headers in debug logs.

### Authorization

All authorization is delegated to the Tomorrowland API's researcher endpoints
(#558).  The adapter never:

- Checks group membership
- Queries the database
- Calls Qdrant or Meilisearch directly
- Duplicates ACL logic

### Write Protection

The adapter exposes **no write tools**.  Even if an MCP client attempts to
call a non-existent tool, the protocol rejects it.

## Troubleshooting

### "Cannot reach Tomorrowland API"

Check that:
1. The Tomorrowland API is running (`curl http://localhost:8000/health`)
2. `TOMORROWLAND_API_URL` points to the correct address
3. Network connectivity exists between the MCP adapter host and the API host

### "Authentication failed (HTTP 401)"

Check that:
1. `TOMORROWLAND_API_KEY` is set to a valid bearer token
2. The token has not expired (JWT expiry)
3. The token is for the correct Tomorrowland deployment

### "Access denied (HTTP 403)"

The authenticated user does not have permission to access the requested
resource.  Verify the user's group membership in the Tomorrowland admin UI.

### "Service unavailable (HTTP 503)"

The Tomorrowland API is running but one of its dependencies (Qdrant,
Meilisearch, Ollama) is unavailable.  Check the API logs for degraded-service
warnings.

### Tool returns empty results

- Verify the document exists and is indexed
- Verify the authenticated user has access to the source containing the
  document
- For `search_documents`, try a broader query with fewer filters
- For `ask_corpus`, check that the Ollama model is loaded and responding

## Development

### Running tests

```bash
uv run pytest tests/unit/test_mcp_server.py -q
```

### Adding a new tool

1. Add the method to `TomorrowlandClient` in
   `src/services/mcp/client.py`
2. Register the tool in `create_mcp_server()` in
   `src/services/mcp/server.py`
3. Add input validation in the tool function
4. Add unit tests in `tests/unit/test_mcp_server.py`

## MCP Transport Details

The adapter uses **Streamable HTTP** transport (MCP v1.1+), which means:

- The server exposes a single HTTP endpoint at `/mcp`
- Clients send tool calls as HTTP POST requests to `/mcp`
- Responses are returned synchronously in the HTTP response body
- No WebSocket or SSE connection is required

This is the simplest and most compatible transport for HTTP-based MCP clients.

## Changelog Entry

```markdown
### Added
- Issue #560: Hermes MCP adapter for researcher API — new
  `tomorrowland-mcp-server` binary exposes six read-only MCP tools
  (`search_documents`, `get_document`, `get_passages`, `ask_corpus`,
  `get_related_documents`, `list_facets`) that proxy to the permissioned
  `/api/agent/v1/*` endpoints from #558. Streamable HTTP transport on
  `localhost:8001`. No direct DB/Qdrant/Meilisearch access. Auth forwarded
  as Bearer token. No secrets in logs. 25+ unit tests.
```
