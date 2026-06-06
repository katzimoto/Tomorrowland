"""MCP server exposing Tomorrowland researcher tools (#560).

Uses the ``FastMCP`` class from the MCP Python SDK (v1.x) to register six
read-only tools that proxy to the ``/api/agent/v1/*`` endpoints established
in #558.

The server runs with **Streamable HTTP** transport (``/mcp`` endpoint) by
default and can also be started with stdio transport for local/air-gapped
workflows.

Observability
-------------
* Every tool invocation emits a structured ``mcp_audit`` log line (INFO).
* Prometheus metrics are recorded per tool: call counts by outcome,
  latency histograms, and error counts by error type.
* A circuit breaker (5 failures / 30 s cooldown) protects the backend
  from cascading failure; state is exposed as a Prometheus gauge.
* ``GET /health`` returns ``{"status": "ok"}`` for liveness probes.
* ``GET /metrics`` exposes Prometheus text format for monitoring.

Security
--------
* No direct database, Qdrant, or Meilisearch access.
* No duplicated ACL logic — every tool call goes through the permissioned
  researcher API from #558.
* Bearer tokens are forwarded from the MCP client to Tomorrowland per-request
  via the ``Authorization`` header extracted from the MCP request context.
  Falls back to the static ``TOMORROWLAND_API_KEY`` env var when the client
  does not send its own token.
* The adapter never inspects or logs the token value.
* No write tools are exposed.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from services.mcp.client import (
    CircuitBreakerOpenError,
    TomorrowlandClient,
    TomorrowlandClientError,
)
from services.mcp.metrics import _mcp_metrics, metrics_endpoint
from shared.config import Settings
from shared.correlation import get_correlation_id

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
        return "Authentication failed (HTTP 401). Check your Bearer token or TOMORROWLAND_API_KEY."
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


def _extract_auth_header(ctx: Context[Any, Any]) -> str | None:
    """Extract the ``Authorization`` header from the MCP request context."""
    meta = getattr(ctx, "request_meta", None)
    if meta is None:
        return None
    headers: dict[str, str] | None = getattr(meta, "headers", None)
    if headers is None:
        return None
    return headers.get("authorization")


def _mcp_audit_log(
    *,
    tool: str,
    correlation_id: str,
    latency_ms: float,
    status: str = "ok",
    error_type: str | None = None,
) -> None:
    """Emit a structured audit log line for an MCP tool invocation."""
    logger.info(
        "mcp_audit tool=%s correlation_id=%s latency_ms=%.1f status=%s%s",
        tool,
        correlation_id,
        latency_ms,
        status,
        f" error_type={error_type}" if error_type else "",
    )


def _record_circuit_breaker_error(
    tool: str, elapsed: float, correlation_id: str,
) -> None:
    """Record metrics and audit log for a circuit breaker open error."""
    _mcp_audit_log(
        tool=tool,
        correlation_id=correlation_id,
        latency_ms=elapsed * 1000,
        status="error",
        error_type="circuit_breaker_open",
    )
    _mcp_metrics.tool_calls_total.labels(
        tool=tool, outcome="error",
    ).inc()
    _mcp_metrics.tool_call_duration_seconds.labels(
        tool=tool,
    ).observe(elapsed)
    _mcp_metrics.tool_call_errors_total.labels(
        tool=tool, error_type="circuit_breaker_open",
    ).inc()


def create_mcp_server(
    settings: Settings | None = None,
    client: TomorrowlandClient | None = None,
) -> FastMCP:
    """Create and configure the MCP server."""
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
            "Returns document results with snippets, relevance scores, "
            "document IDs, sources, MIME types, and languages. "
            "Use when a researcher asks to find documents about a topic, "
            "browse what is available, or narrow results by filters."
        ),
    )
    def tomorrowland_search_documents(
        query: Annotated[
            str,
            Field(description="Free-text search query (1-500 characters)"),
        ],
        top_k: Annotated[
            int,
            Field(description="Number of results per page (1-50, default 20)"),
        ] = 20,
        page: Annotated[
            int,
            Field(description="Page number for pagination (1-20, default 1)"),
        ] = 1,
        filters: Annotated[
            dict[str, Any] | None,
            Field(
                description=(
                    "Optional filter dict with sources, mime_types, "
                    "languages, tags, date_from, date_to"
                ),
            ),
        ] = None,
        ctx: Context[Any, Any] | None = None,
    ) -> dict[str, Any]:
        correlation_id = get_correlation_id()
        auth_header = _extract_auth_header(ctx) if ctx else None
        t0 = time.perf_counter()
        _validate_string(query, 1, _MAX_QUERY_LENGTH, "query")
        _validate_int(top_k, _MIN_TOP_K, _MAX_TOP_K, "top_k")
        _validate_int(page, _MIN_PAGE, _MAX_PAGE, "page")

        try:
            result = client.search_documents(
                query=query,
                top_k=top_k,
                page=page,
                filters=filters,
                correlation_id=correlation_id,
                auth_header=auth_header,
            )
            elapsed = time.perf_counter() - t0
            _mcp_audit_log(
                tool="search_documents",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="search_documents",
                outcome="ok",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="search_documents",
            ).observe(elapsed)
            return result
        except TomorrowlandClientError as exc:
            elapsed = time.perf_counter() - t0
            error_type = f"HTTP_{exc.status_code}"
            _mcp_audit_log(
                tool="search_documents",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
                status="error",
                error_type=error_type,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="search_documents",
                outcome="error",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="search_documents",
            ).observe(elapsed)
            _mcp_metrics.tool_call_errors_total.labels(
                tool="search_documents",
                error_type=error_type,
            ).inc()
            raise ValueError(_translate_error(exc)) from exc
        except CircuitBreakerOpenError as exc:
            elapsed = time.perf_counter() - t0
            _record_circuit_breaker_error(
                "search_documents", elapsed, correlation_id,
            )
            raise ValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.get_document
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Get metadata for a single document by its ID. "
            "Returns title, source, MIME type, languages, tags, "
            "summary, version information, and timestamps. "
            "Use after search_documents to inspect a document's full "
            "metadata, or before calling get_passages or "
            "get_related_documents to verify the document is correct."
        ),
    )
    def tomorrowland_get_document(
        document_id: Annotated[
            str,
            Field(description="UUID of the document (1-64 characters)"),
        ],
        ctx: Context[Any, Any] | None = None,
    ) -> dict[str, Any]:
        correlation_id = get_correlation_id()
        auth_header = _extract_auth_header(ctx) if ctx else None
        t0 = time.perf_counter()
        _validate_string(document_id, 1, 64, "document_id")

        try:
            result = client.get_document(
                document_id=document_id,
                correlation_id=correlation_id,
                auth_header=auth_header,
            )
            elapsed = time.perf_counter() - t0
            _mcp_audit_log(
                tool="get_document",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="get_document",
                outcome="ok",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="get_document",
            ).observe(elapsed)
            return result
        except TomorrowlandClientError as exc:
            elapsed = time.perf_counter() - t0
            error_type = f"HTTP_{exc.status_code}"
            _mcp_audit_log(
                tool="get_document",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
                status="error",
                error_type=error_type,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="get_document",
                outcome="error",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="get_document",
            ).observe(elapsed)
            _mcp_metrics.tool_call_errors_total.labels(
                tool="get_document",
                error_type=error_type,
            ).inc()
            raise ValueError(_translate_error(exc)) from exc
        except CircuitBreakerOpenError as exc:
            elapsed = time.perf_counter() - t0
            _record_circuit_breaker_error(
                "get_document", elapsed, correlation_id,
            )
            raise ValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.get_passages
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Get text passages (chunks) for a document. "
            "Returns ordered passages with chunk IDs, text content, "
            "page numbers, section headings, and language metadata. "
            "Use to read the actual content of a document, inspect "
            "specific sections, or review citations."
        ),
    )
    def tomorrowland_get_passages(
        document_id: Annotated[
            str,
            Field(description="UUID of the document (1-64 characters)"),
        ],
        limit: Annotated[
            int,
            Field(description="Maximum passages to return (1-100, default 50)"),
        ] = 50,
        offset: Annotated[
            int,
            Field(description="Pagination offset (0-10000, default 0)"),
        ] = 0,
        ctx: Context[Any, Any] | None = None,
    ) -> dict[str, Any]:
        correlation_id = get_correlation_id()
        auth_header = _extract_auth_header(ctx) if ctx else None
        t0 = time.perf_counter()
        _validate_string(document_id, 1, 64, "document_id")
        _validate_int(limit, _MIN_LIMIT, _MAX_LIMIT, "limit")
        _validate_int(offset, _MIN_OFFSET, _MAX_OFFSET, "offset")

        try:
            result = client.get_passages(
                document_id=document_id,
                limit=limit,
                offset=offset,
                correlation_id=correlation_id,
                auth_header=auth_header,
            )
            elapsed = time.perf_counter() - t0
            _mcp_audit_log(
                tool="get_passages",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="get_passages",
                outcome="ok",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="get_passages",
            ).observe(elapsed)
            return result
        except TomorrowlandClientError as exc:
            elapsed = time.perf_counter() - t0
            error_type = f"HTTP_{exc.status_code}"
            _mcp_audit_log(
                tool="get_passages",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
                status="error",
                error_type=error_type,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="get_passages",
                outcome="error",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="get_passages",
            ).observe(elapsed)
            _mcp_metrics.tool_call_errors_total.labels(
                tool="get_passages",
                error_type=error_type,
            ).inc()
            raise ValueError(_translate_error(exc)) from exc
        except CircuitBreakerOpenError as exc:
            elapsed = time.perf_counter() - t0
            _record_circuit_breaker_error(
                "get_passages", elapsed, correlation_id,
            )
            raise ValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.ask_corpus
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Ask a natural-language question over the accessible document "
            "corpus. Returns a generated answer backed by citations to "
            "specific documents and passages. Each citation includes "
            "document ID, title, chunk text, page number, and relevance "
            "score. Use for factual questions that need evidence from "
            "source documents. Can be narrowed to a single document."
        ),
    )
    def tomorrowland_ask_corpus(
        question: Annotated[
            str,
            Field(description="Natural-language question (1-2000 characters)"),
        ],
        top_k: Annotated[
            int | None,
            Field(description="Number of chunks to retrieve (1-20, optional)"),
        ] = None,
        document_id: Annotated[
            str | None,
            Field(description="Restrict to a single document UUID (optional)"),
        ] = None,
        ctx: Context[Any, Any] | None = None,
    ) -> dict[str, Any]:
        correlation_id = get_correlation_id()
        auth_header = _extract_auth_header(ctx) if ctx else None
        t0 = time.perf_counter()
        _validate_string(question, 1, _MAX_QUESTION_LENGTH, "question")

        if top_k is not None:
            _validate_int(top_k, _MIN_TOP_K, _MAX_TOP_K, "top_k")
        if document_id is not None:
            _validate_string(document_id, 1, 64, "document_id")

        try:
            result = client.ask_corpus(
                question=question,
                top_k=top_k,
                document_id=document_id,
                correlation_id=correlation_id,
                auth_header=auth_header,
            )
            elapsed = time.perf_counter() - t0
            _mcp_audit_log(
                tool="ask_corpus",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="ask_corpus",
                outcome="ok",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="ask_corpus",
            ).observe(elapsed)
            return result
        except TomorrowlandClientError as exc:
            elapsed = time.perf_counter() - t0
            error_type = f"HTTP_{exc.status_code}"
            _mcp_audit_log(
                tool="ask_corpus",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
                status="error",
                error_type=error_type,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="ask_corpus",
                outcome="error",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="ask_corpus",
            ).observe(elapsed)
            _mcp_metrics.tool_call_errors_total.labels(
                tool="ask_corpus",
                error_type=error_type,
            ).inc()
            raise ValueError(_translate_error(exc)) from exc
        except CircuitBreakerOpenError as exc:
            elapsed = time.perf_counter() - t0
            _record_circuit_breaker_error(
                "ask_corpus", elapsed, correlation_id,
            )
            raise ValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.get_related_documents
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "Get documents related to a given document. "
            "Returns related document IDs, titles, relevance scores, "
            "and relation reasons. Use to discover semantically or "
            "topically related material from a key document."
        ),
    )
    def tomorrowland_get_related_documents(
        document_id: Annotated[
            str,
            Field(description="UUID of the seed document (1-64 characters)"),
        ],
        ctx: Context[Any, Any] | None = None,
    ) -> dict[str, Any]:
        correlation_id = get_correlation_id()
        auth_header = _extract_auth_header(ctx) if ctx else None
        t0 = time.perf_counter()
        _validate_string(document_id, 1, 64, "document_id")

        try:
            result = client.get_related_documents(
                document_id=document_id,
                correlation_id=correlation_id,
                auth_header=auth_header,
            )
            elapsed = time.perf_counter() - t0
            _mcp_audit_log(
                tool="get_related_documents",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="get_related_documents",
                outcome="ok",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="get_related_documents",
            ).observe(elapsed)
            return result
        except TomorrowlandClientError as exc:
            elapsed = time.perf_counter() - t0
            error_type = f"HTTP_{exc.status_code}"
            _mcp_audit_log(
                tool="get_related_documents",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
                status="error",
                error_type=error_type,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="get_related_documents",
                outcome="error",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="get_related_documents",
            ).observe(elapsed)
            _mcp_metrics.tool_call_errors_total.labels(
                tool="get_related_documents",
                error_type=error_type,
            ).inc()
            raise ValueError(_translate_error(exc)) from exc
        except CircuitBreakerOpenError as exc:
            elapsed = time.perf_counter() - t0
            _record_circuit_breaker_error(
                "get_related_documents", elapsed, correlation_id,
            )
            raise ValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # tomorrowland.list_facets
    # ------------------------------------------------------------------
    @mcp.tool(
        description=(
            "List facet distributions (sources, MIME types, languages, "
            "tags) over documents the caller can access. Returns a "
            "dictionary of facet categories and their value counts. "
            "Use to understand the shape of the accessible corpus "
            "before searching or to discover available sources, "
            "languages, and document types."
        ),
    )
    def tomorrowland_list_facets(
        query: Annotated[
            str,
            Field(description="Optional free-text query to filter facet counts (0-500 chars)"),
        ] = "",
        ctx: Context[Any, Any] | None = None,
    ) -> dict[str, Any]:
        correlation_id = get_correlation_id()
        auth_header = _extract_auth_header(ctx) if ctx else None
        t0 = time.perf_counter()
        _validate_string(query, 0, _MAX_QUERY_LENGTH, "query")

        try:
            result = client.list_facets(
                query=query,
                correlation_id=correlation_id,
                auth_header=auth_header,
            )
            elapsed = time.perf_counter() - t0
            _mcp_audit_log(
                tool="list_facets",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="list_facets",
                outcome="ok",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="list_facets",
            ).observe(elapsed)
            return result
        except TomorrowlandClientError as exc:
            elapsed = time.perf_counter() - t0
            error_type = f"HTTP_{exc.status_code}"
            _mcp_audit_log(
                tool="list_facets",
                correlation_id=correlation_id,
                latency_ms=elapsed * 1000,
                status="error",
                error_type=error_type,
            )
            _mcp_metrics.tool_calls_total.labels(
                tool="list_facets",
                outcome="error",
            ).inc()
            _mcp_metrics.tool_call_duration_seconds.labels(
                tool="list_facets",
            ).observe(elapsed)
            _mcp_metrics.tool_call_errors_total.labels(
                tool="list_facets",
                error_type=error_type,
            ).inc()
            raise ValueError(_translate_error(exc)) from exc
        except CircuitBreakerOpenError as exc:
            elapsed = time.perf_counter() - t0
            _record_circuit_breaker_error(
                "list_facets", elapsed, correlation_id,
            )
            raise ValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Health and metrics endpoints
    # ------------------------------------------------------------------
    _register_observability_endpoints(mcp)

    return mcp


def _register_observability_endpoints(mcp: FastMCP) -> None:
    """Register ``/health`` and ``/metrics`` endpoints on the FastMCP server."""
    try:
        from starlette.responses import JSONResponse, Response

        app = getattr(mcp, "_app", None) or getattr(mcp, "app", None)
        if app is None:
            logger.debug(
                "No Starlette app accessible on FastMCP; skipping /health and /metrics endpoints"
            )
            return

        # Health endpoint
        async def health(request):  # type: ignore[no-untyped-def]  # noqa: ARG001
            return JSONResponse({"status": "ok"})

        app.add_route("/health", health, methods=["GET"])
        logger.debug("Registered /health endpoint on FastMCP server")

        # Metrics endpoint. metrics_endpoint returns a (body, status, headers)
        # tuple; adapt it to a Starlette Response so the route serves correctly
        # (a bare tuple is not a valid ASGI response and would 500 the scrape).
        async def metrics(request):  # type: ignore[no-untyped-def]  # noqa: ARG001
            body, status, headers = await metrics_endpoint(request)
            return Response(content=body, status_code=status, headers=headers)

        app.add_route("/metrics", metrics, methods=["GET"])
        logger.debug("Registered /metrics endpoint on FastMCP server")
    except Exception:
        logger.debug(
            "Could not register observability endpoints; falling back to TCP probe",
            exc_info=True,
        )


def run_server(settings: Settings | None = None) -> None:
    """Run the MCP server with Streamable HTTP transport."""
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
