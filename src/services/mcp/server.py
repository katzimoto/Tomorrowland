"""MCP server exposing Tomorrowland researcher tools (#560).

Uses the ``FastMCP`` class from the MCP Python SDK (v1.x) to register six
read-only tools that proxy to the ``/api/agent/v1/*`` endpoints established
in #558.

The server runs with **Streamable HTTP** transport (``/mcp`` endpoint) by
default and can also be started with stdio transport for local/air-gapped
workflows.

Security
--------
* No direct database, Qdrant, or Meilisearch access.
* No duplicated ACL logic — every tool call goes through the permissioned
  researcher API from #558.
* Bearer tokens are forwarded from the MCP client to Tomorrowland; the
  adapter never inspects or logs the token value.
* No write tools are exposed.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from services.mcp.client import TomorrowlandClient, TomorrowlandClientError
from shared.config import Settings

logger = logging.getLogger(__name__)

# Maximum lengths enforced by #558 agent endpoint schemas.
_MAX_QUERY_LENGTH = 500
_MAX_QUESTION_LENGTH = 2000
_MAX_TOP_K = 50
_MIN_TOP_K = 1
_MAX_PAGE = 20
_MIN_PAGE = 1
_MAX_LIMIT = 100
_MIN_LIMIT = 1
_MAX_OFFSET = 10000
_MIN_OFFSET = 0


def _validate_string(value: str, min_len: int, max_len: int, name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    if len(value) < min_len:
        raise ValueError(f"{name} must be at least {min_len} character(s), got {len(value)}")
    if len(value) > max_len:
        raise ValueError(f"{name} must be at most {max_len} character(s), got {len(value)}")


def _validate_int(value: int, min_val: int, max_val: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got {type(value).__name__}")
    if value < min_val:
        raise ValueError(f"{name} must be >= {min_val}, got {value}")
    if value > max_val:
        raise ValueError(f"{name} must be <= {max_val}, got {value}")


def _translate_error(exc: TomorrowlandClientError) -> str:
    """Map API HTTP status codes to descriptive error messages."""
    status = exc.status_code
    if status == 401:
        return "Authentication failed (HTTP 401). Check your TOMORROWLAND_API_KEY."
    if status == 403:
        return "Access denied (HTTP 403). Your token lacks permissions for this resource."
    if status == 404:
        return "Resource not found (HTTP 404)."
    if status == 422:
        return f"Invalid request (HTTP 422): {exc}"
    if status == 429:
        return "Rate limit exceeded (HTTP 429). Please retry later."
    if status == 503:
        return f"Service unavailable (HTTP 503): {exc}"
    if status == 504:
        return f"Request timed out (HTTP 504): {exc}"
    return str(exc)


def create_mcp_server(
    settings: Settings | None = None,
    client: TomorrowlandClient | None = None,
) -> FastMCP:
    """Create and configure the MCP server.

    Parameters
    ----------
    settings:
        Application settings.  If omitted, loaded from environment.
    client:
        Pre-configured Tomorrowland API client.  If omitted, created from
        *settings*.

    Returns
    -------
    FastMCP
        The configured MCP server instance (not yet running).
    """
    if settings is None:
        settings = Settings()

    if client is None:
        client = TomorrowlandClient(
            api_url=settings.tomorrowland_api_url,
            api_key=settings.tomorrowland_api_key or "",
            timeout=settings.tomorrowland_api_timeout,
        )

    mcp = FastMCP(
        "Tomorrowland",
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=str(settings.log_level).upper(),  # type: ignore[arg-type]
        json_response=True,
    )

    # ------------------------------------------------------------------
    # tomorrowland.search_documents
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Search documents using hybrid (BM25 + vector) search. "
            "Returns document results with snippets and relevance scores."
        )
    )
    def tomorrowland_search_documents(
        query: str,
        top_k: int = 20,
        page: int = 1,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search documents via the Tomorrowland researcher API."""
        _validate_string(query, 1, _MAX_QUERY_LENGTH, "query")
        _validate_int(top_k, _MIN_TOP_K, _MAX_TOP_K, "top_k")
        _validate_int(page, _MIN_PAGE, _MAX_PAGE, "page")

        try:
            return client.search_documents(query=query, top_k=top_k, page=page, filters=filters)
        except TomorrowlandClientError as exc:
            raise ValueError(_translate_error(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.get_document
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Get metadata for a single document by its ID. "
            "Returns title, source, MIME type, languages, tags, summary."
        )
    )
    def tomorrowland_get_document(document_id: str) -> dict[str, Any]:
        """Get document metadata via the Tomorrowland researcher API."""
        _validate_string(document_id, 1, 64, "document_id")

        try:
            return client.get_document(document_id=document_id)
        except TomorrowlandClientError as exc:
            raise ValueError(_translate_error(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.get_passages
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Get text passages (chunks) for a document. "
            "Returns ordered passages with page numbers and section headings."
        )
    )
    def tomorrowland_get_passages(
        document_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get document passages via the Tomorrowland researcher API."""
        _validate_string(document_id, 1, 64, "document_id")
        _validate_int(limit, _MIN_LIMIT, _MAX_LIMIT, "limit")
        _validate_int(offset, _MIN_OFFSET, _MAX_OFFSET, "offset")

        try:
            return client.get_passages(document_id=document_id, limit=limit, offset=offset)
        except TomorrowlandClientError as exc:
            raise ValueError(_translate_error(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.ask_corpus
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Ask a question over the accessible document corpus. "
            "Returns an answer with citations to supporting documents."
        )
    )
    def tomorrowland_ask_corpus(
        question: str,
        top_k: int | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        """Ask a question over the corpus via the Tomorrowland researcher API."""
        _validate_string(question, 1, _MAX_QUESTION_LENGTH, "question")

        if top_k is not None:
            _validate_int(top_k, _MIN_TOP_K, _MAX_TOP_K, "top_k")
        if document_id is not None:
            _validate_string(document_id, 1, 64, "document_id")

        try:
            return client.ask_corpus(question=question, top_k=top_k, document_id=document_id)
        except TomorrowlandClientError as exc:
            raise ValueError(_translate_error(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.get_related_documents
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Get documents related to a given document. "
            "Returns related document IDs, titles, and relevance scores."
        )
    )
    def tomorrowland_get_related_documents(document_id: str) -> dict[str, Any]:
        """Get related documents via the Tomorrowland researcher API."""
        _validate_string(document_id, 1, 64, "document_id")

        try:
            return client.get_related_documents(document_id=document_id)
        except TomorrowlandClientError as exc:
            raise ValueError(_translate_error(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.list_facets
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "List facet distributions (sources, MIME types, languages, etc.) "
            "over documents the caller can access."
        )
    )
    def tomorrowland_list_facets(query: str = "") -> dict[str, Any]:
        """List facet distributions via the Tomorrowland researcher API."""
        _validate_string(query, 0, _MAX_QUERY_LENGTH, "query")

        try:
            return client.list_facets(query=query)
        except TomorrowlandClientError as exc:
            raise ValueError(_translate_error(exc)) from exc

    return mcp


def run_server(settings: Settings | None = None) -> None:
    """Run the MCP server with Streamable HTTP transport.

    Parameters
    ----------
    settings:
        Application settings.  If omitted, loaded from environment.
    """
    if settings is None:
        settings = Settings()

    mcp = create_mcp_server(settings)
    logger.info(
        "Starting MCP server on %s:%s with transport=streamable-http",
        settings.mcp_host,
        settings.mcp_port,
    )
    mcp.run(transport="streamable-http")


def main() -> None:
    """CLI entry point for ``tomorrowland-mcp-server``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_server()


if __name__ == "__main__":
    main()
