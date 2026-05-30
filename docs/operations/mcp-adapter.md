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

```toml
# hermes.toml
[[mcp_servers]]
name = "tomorrowland"
transport = "http"
url = "http://127.0.0.1:8001/mcp"
api_key = "your-bearer-token"

# Tool include list — limit Hermes to Tomorrowland's six read-only tools.
# Omitting this list exposes all tools served by the MCP adapter.
#
# Exact filter syntax depends on your Hermes version.  The tool names
# listed below are the canonical MCP tool names as registered by FastMCP.
# Common Hermes formats include a string array under `tools.include` or
# a TOML section with per-tool booleans (shown here).  Refer to your
# Hermes documentation for the supported syntax.
[mcp_servers.tool_include]
tomorrowland_search_documents = true
tomorrowland_get_document = true
tomorrowland_get_passages = true
tomorrowland_ask_corpus = true
tomorrowland_get_related_documents = true
tomorrowland_list_facets = true
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

## Researcher Tool Guide

Each tool maps to a read-only researcher API endpoint.  Below is a
researcher-facing explanation of what each tool does, what it returns, and
when to use it.

### `tomorrowland_search_documents`

**Purpose:** Find documents in the researcher's accessible corpus using hybrid
(BM25 + vector) search.

**Returns:** A list of matching documents with snippets, relevance scores,
document IDs, sources, MIME types, and languages.

**When to use:**

- A researcher asks "find all documents about solar panel degradation"
- A researcher wants to browse what's available on a topic before asking
  specific questions
- A researcher needs to narrow results by source, MIME type, language, or
  tag filters

**Key parameters:**

| Parameter | Description |
|-----------|-------------|
| `query` | Free-text search query (1–500 chars) |
| `top_k` | Number of results per page (1–50, default 20) |
| `page` | Page number for pagination (1–20) |
| `filters` | Optional dict with `sources`, `mime_types`, `languages`, `tags`, `date_from` (ISO 8601 date, maps to `created_after`), `date_to` (ISO 8601 date, maps to `updated_after`) |

### `tomorrowland_get_document`

**Purpose:** Retrieve metadata for a single document by its ID.

**Returns:** Document metadata — title, source, MIME type, languages, tags,
summary (if the intelligence worker has processed it), version information,
and timestamps.

**When to use:**

- After `search_documents` returns a promising result, to inspect its full
  metadata
- Before calling `get_passages` or `get_related_documents`, to verify the
  document is the right one
- When a researcher needs to check a document's source, language, or
  translation status

**Key parameters:**

| Parameter | Description |
|-----------|-------------|
| `document_id` | UUID of the document (1–64 chars) |

### `tomorrowland_get_passages`

**Purpose:** Retrieve the text passages (chunks) of a document the researcher
can access.

**Returns:** Ordered passages with chunk IDs, text content, page numbers,
section headings, and language metadata.

**When to use:**

- A researcher wants to read the actual content of a document identified via
  search
- A researcher needs to inspect specific sections without downloading the
  original file
- Building an evidence pack or reviewing citations

**Key parameters:**

| Parameter | Description |
|-----------|-------------|
| `document_id` | UUID of the document (1–64 chars) |
| `limit` | Maximum passages to return (1–100, default 50) |
| `offset` | Pagination offset (0–10000, default 0) |

### `tomorrowland_ask_corpus`

**Purpose:** Ask a natural-language question over the researcher's accessible
document corpus and receive an answer with citations.

**Returns:** A generated answer backed by citations to specific documents
and passages.  Each citation includes the document ID, title, chunk text,
and relevance score.

**When to use:**

- A researcher asks "summarise what our documents say about quarterly
  earnings"
- A researcher needs factual answers backed by source documents
- Narrowing the scope to a single document by passing `document_id`

**Key parameters:**

| Parameter | Description |
|-----------|-------------|
| `question` | Natural-language question (1–2000 chars) |
| `top_k` | Number of chunks to retrieve (1–20, optional; the effective API limit is 20) |
| `document_id` | Restrict to a single document (optional) |

### `tomorrowland_get_related_documents`

**Purpose:** Discover documents that are semantically or topically related to
a given document.

**Returns:** A list of related documents with IDs, titles, relevance scores,
and relation reasons where available.

**When to use:**

- A researcher finds a key document and wants to discover related material
- Exploring connections between documents that may not share explicit
  metadata tags

**Key parameters:**

| Parameter | Description |
|-----------|-------------|
| `document_id` | UUID of the seed document (1–64 chars) |

### `tomorrowland_list_facets`

**Purpose:** List facet distributions (sources, MIME types, languages, tags)
over the documents the researcher can access.

**Returns:** A dictionary of facet categories and their value counts.

**When to use:**

- A researcher wants to understand the shape of their accessible corpus
  before searching
- Narrowing search filters by discovering available sources, languages, or
  MIME types

**Key parameters:**

| Parameter | Description |
|-----------|-------------|
| `query` | Optional free-text query to filter facet counts (0–500 chars) |

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
| | `top_k` | 1–20 (optional; per API schema in #558) |
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

## Example Researcher Prompts

Below are example prompts a researcher might give to Hermes (or any MCP
client) to use the Tomorrowland tools.  Substitute real document IDs,
queries, and questions as appropriate.

### Search for documents on a topic

> Search Tomorrowland for documents about carbon capture technology.

Hermes invokes `tomorrowland_search_documents` with `query="carbon capture
technology"` and presents the results.

### Narrow search by source filter

> Search Tomorrowland for documents about emissions reporting, limited to the
> "regulatory-filings" source.

Hermes invokes `tomorrowland_search_documents` with
`filters={"sources": ["regulatory-filings"]}`.

### Inspect document metadata

> Get the metadata for document
> "550e8400-e29b-41d4-a716-446655440000".

Hermes invokes `tomorrowland_get_document`.

### Read document passages

> Show me the first 25 passages from document
> "550e8400-e29b-41d4-a716-446655440000".

Hermes invokes `tomorrowland_get_passages` with `limit=25, offset=0`.

### Ask the corpus with citations

> Using Tomorrowland, what do our documents say about the impact of
> remote work on productivity? Cite your sources.

Hermes invokes `tomorrowland_ask_corpus` and includes returned citations in
its response.

### Ask a single document

> Using Tomorrowland, summarise the key findings in document
> "550e8400-e29b-41d4-a716-446655440000".

Hermes invokes `tomorrowland_ask_corpus` with
`document_id="550e8400-e29b-41d4-a716-446655440000"`.

### Find related documents

> What other documents are related to
> "550e8400-e29b-41d4-a716-446655440000"?

Hermes invokes `tomorrowland_get_related_documents`.

### Explore the corpus with facets

> List the available facets in Tomorrowland so I can understand what
> sources and document types are available.

Hermes invokes `tomorrowland_list_facets`.

### Multi-step research workflow

> 1. Search Tomorrowland for documents about supply chain resilience.
> 2. Pick the top 3 results and get their metadata.
> 3. For each, read the first 10 passages.
> 4. Then ask the corpus: what are the common themes across these
>    documents?

Hermes chains multiple tool calls — `search_documents` → `get_document` →
`get_passages` → `ask_corpus` — to build a multi-step research answer.

## Citation Behavior

### How citations are generated

When `tomorrowland_ask_corpus` returns an answer, it includes a `citations`
array.  Each citation references:

| Field | Description |
|-------|-------------|
| `document_id` | UUID of the cited document |
| `doc_title` | Title of the cited document |
| `chunk_text` | The specific passage text that supports the answer |
| `score` | Relevance score of this chunk to the question |
| `chunk_index` | Position of the chunk within the document |
| `source_id` | Source the document belongs to |
| `page_number` | Page number where the passage appears (if available) |
| `section_heading` | Section heading where the passage appears (if available) |
| `language` | Language of the cited passage |

### What citations guarantee

- **Accessibility:** Every citation refers to a document the authenticated
  researcher can access.  Citations for documents outside the researcher's
  permitted sources are dropped before the response is returned.
- **Defence in depth:** Even if a misconfigured payload includes an
  inaccessible document ID, the API re-checks the source ACL per citation
  and strips any that fail.

### What to do if citations are missing or insufficient

If citations are absent from an `ask_corpus` response:

1. **Check the corpus scope.**  If the researcher has access to very few
   documents (or none), the RAG pipeline may not find enough relevant
   passages to generate citations.  Use `list_facets` to confirm what
   documents are available.
2. **Try a broader question.**  Very specific or narrow questions may not
   match any passages above the relevance threshold.  Rephrase the question
   more broadly and try again.
3. **Verify the Ollama model is loaded.**  If the Tomorrowland API returns
   a 503, the LLM model may not be available.  Check the API health
   endpoint or operator logs.
4. **Check the retrieved passages directly.**  Use `get_passages` on
   candidate documents and verify the content is indexed and searchable.

If the answer includes citations but they seem insufficient:

1. **Increase `top_k`.**  The default chunk retrieval may be too narrow.
   Pass a higher `top_k` value to retrieve more passages.
2. **Expand the corpus filter.**  If the researcher's access is limited to
   a narrow set of sources, broader access may yield better citations.
3. **Inspect the citations manually.**  Use `get_document` and
   `get_passages` on cited documents to verify the passage content is
   relevant.

## Known Limits & Deferred Capabilities

The MCP adapter and researcher API are under active development.  The
following capabilities are documented as known limits or deferred to future
issues:

### Write tools not available

There are **no write tools** in the current release.  The MCP adapter
exposes only the six read-only tools listed above.  Create, update, and
delete operations are not exposed to MCP clients.

### Deferred write capabilities (#565)

- **Notes and evidence-pack writes** are planned for [#565](/issues/565)
  but are not yet implemented.  Researchers cannot save annotations, notes,
  or evidence packs through the MCP tools.

### Audit and usage limits (#561)

- **Audit logging** and **usage limits** for MCP tool calls are being
  finalised in [#561](/issues/561).  Currently, MCP tool calls are not
  individually audited or rate-limited beyond the Tomorrowland API's
  standard authentication checks.

### Permission regression coverage (#562)

- Comprehensive **permission regression tests** covering the researcher API
  and MCP adapter are tracked in [#562](/issues/562).  Existing tests cover
  core ACL enforcement, but edge cases may not be fully exercised.

### Air-gapped behaviour (#564)

- Specific **air-gapped deployment** guidance and validation for the MCP
  adapter is tracked in [#564](/issues/564).  The adapter works in
  air-gapped mode (both processes on the same host), but formal validation
  and operator documentation are still in progress.

### No direct store access

The MCP adapter and researcher API will not gain direct database, Qdrant,
or Meilisearch access in any future release.  All tool calls go through the
permissioned `/api/agent/v1/*` API.

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
- Issue #563: Document Hermes researcher connection workflow — expanded
  `docs/operations/mcp-adapter.md` with researcher-facing tool guide,
  example Hermes prompts, citation behaviour documentation, known limits
  and deferred capabilities, and extended Hermes configuration.
- Issue #560: Hermes MCP adapter for researcher API — new
  `tomorrowland-mcp-server` binary exposes six read-only MCP tools
  (`search_documents`, `get_document`, `get_passages`, `ask_corpus`,
  `get_related_documents`, `list_facets`) that proxy to the permissioned
  `/api/agent/v1/*` endpoints from #558. Streamable HTTP transport on
  `localhost:8001`. No direct DB/Qdrant/Meilisearch access. Auth forwarded
  as Bearer token. No secrets in logs. 25+ unit tests.
```
