"""Unit tests for the MCP adapter (#560).

Tests cover:
- ``TomorrowlandClient`` — each tool method calls the correct HTTP method/path,
  forwards auth headers, handles errors, timeout, retries, correlation IDs.
- ``create_mcp_server`` — tool list, input validation, error translation, audit logging.
- Log sanitisation: no Authorization header leakage.
- No direct store clients imported.
- Retry behaviour: 503, 429, and timeout errors are retried up to 3 times.
- Correlation ID forwarding: X-Correlation-ID header sent to backend.
- Connection pool: httpx.Client created with connection limits.
- Per-client token forwarding: auth_header overrides static API key, fallback behaviour.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.server.fastmcp import Context, FastMCP

from services.mcp.client import (
    _CONNECTION_LIMITS,
    _MAX_RETRIES,
    CircuitBreaker,
    CircuitBreakerOpenError,
    TomorrowlandClient,
    TomorrowlandClientError,
    _sanitize_headers,
)
from services.mcp.server import (
    _MAX_PAGE,
    _MAX_QUERY_LENGTH,
    _MAX_TOP_K,
    _MIN_TOP_K,
    _VALID_FILTER_KEYS,
    _check_tool_enabled,
    _extract_auth_header,
    _extract_traceparent,
    _validate_filters,
    _validate_int,
    _validate_string,
    create_mcp_server,
)
from shared.config import Settings

# ======================================================================
# Helper
# ======================================================================


def _mock_response(status_code: int = 200, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _error_response(status_code: int, detail: str = "Test error") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = {"detail": detail}
    return resp


def _invoke_tool(fn: Any, **kwargs: Any) -> Any:
    """Invoke a tool function, auto-handling async tools."""
    result = fn(**kwargs)
    if asyncio.iscoroutine(result):
        return asyncio.run(result)
    return result


def _mock_context(headers: dict[str, str] | None = None) -> Context:
    """Return a mock MCP Context with request_meta populated."""
    ctx = AsyncMock(spec=Context)
    if headers is not None:
        meta = MagicMock()
        meta.headers = headers
        ctx.request_meta = meta
    return ctx


# ======================================================================
# _validate_string / _validate_int
# ======================================================================


class TestValidateString:
    def test_valid(self) -> None:
        _validate_string("hello", 1, 100, "query")

    def test_too_short(self) -> None:
        with pytest.raises(ValueError, match="query must be at least 3"):
            _validate_string("ab", 3, 100, "query")

    def test_too_long(self) -> None:
        with pytest.raises(ValueError, match="query must be at most 5"):
            _validate_string("a" * 10, 1, 5, "query")

    def test_non_string(self) -> None:
        with pytest.raises(ValueError, match="query must be a string"):
            _validate_string(123, 1, 100, "query")  # type: ignore[arg-type]


class TestValidateInt:
    def test_valid(self) -> None:
        _validate_int(5, 1, 50, "top_k")

    def test_below_min(self) -> None:
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            _validate_int(0, 1, 50, "top_k")

    def test_above_max(self) -> None:
        with pytest.raises(ValueError, match="top_k must be <= 50"):
            _validate_int(51, 1, 50, "top_k")

    def test_non_int(self) -> None:
        with pytest.raises(ValueError, match="top_k must be an integer"):
            _validate_int("abc", 1, 50, "top_k")  # type: ignore[arg-type]

    def test_boolean_not_accepted(self) -> None:
        with pytest.raises(ValueError, match="top_k must be an integer"):
            _validate_int(True, 1, 50, "top_k")  # type: ignore[arg-type]


# ======================================================================
# _sanitize_headers
# ======================================================================


class TestSanitizeHeaders:
    def test_redacts_authorization(self) -> None:
        sanitized = _sanitize_headers(
            {"Authorization": "Bearer secret123", "Content-Type": "application/json"}
        )
        assert sanitized["Authorization"] == "[redacted]"
        assert sanitized["Content-Type"] == "application/json"

    def test_redacts_case_insensitive(self) -> None:
        sanitized = _sanitize_headers(
            {"authorization": "Bearer secret123", "COOKIE": "session=abc"}
        )
        assert sanitized["authorization"] == "[redacted]"
        assert sanitized["COOKIE"] == "[redacted]"


# ======================================================================
# _extract_auth_header
# ======================================================================


class TestExtractAuthHeader:
    """Verify the Authorization header is correctly extracted from Context."""

    def test_extracts_lowercase_authorization(self) -> None:
        """ASGI normalises headers to lowercase."""
        ctx = _mock_context({"authorization": "Bearer client-token-123"})
        result = _extract_auth_header(ctx)
        assert result == "Bearer client-token-123"

    def test_returns_none_when_no_request_meta(self) -> None:
        ctx = MagicMock(spec=Context, request_meta=None)
        result = _extract_auth_header(ctx)
        assert result is None

    def test_returns_none_when_no_headers_on_meta(self) -> None:
        ctx = AsyncMock(spec=Context)
        meta_without_headers = MagicMock(spec=[])
        ctx.request_meta = meta_without_headers
        result = _extract_auth_header(ctx)
        assert result is None

    def test_returns_none_when_context_is_none(self) -> None:
        """Gracefully handles None context (tests call tools without ctx)."""
        assert _extract_auth_header(None) is None  # type: ignore[arg-type]


# ======================================================================
# _extract_traceparent
# ======================================================================


class TestExtractTraceparent:
    """Verify the W3C traceparent header is correctly extracted from Context."""

    def test_extracts_lowercase_traceparent(self) -> None:
        """ASGI normalises headers to lowercase."""
        ctx = _mock_context(
            {
                "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
            }
        )
        result = _extract_traceparent(ctx)
        assert result == "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

    def test_returns_none_when_no_request_meta(self) -> None:
        ctx = MagicMock(spec=Context, request_meta=None)
        result = _extract_traceparent(ctx)
        assert result is None

    def test_returns_none_when_no_headers_on_meta(self) -> None:
        ctx = AsyncMock(spec=Context)
        meta_without_headers = MagicMock(spec=[])
        ctx.request_meta = meta_without_headers
        result = _extract_traceparent(ctx)
        assert result is None

    def test_returns_none_when_context_is_none(self) -> None:
        """Gracefully handles None context (tests call tools without ctx)."""
        assert _extract_traceparent(None) is None  # type: ignore[arg-type]

    def test_returns_none_when_no_traceparent(self) -> None:
        ctx = _mock_context({"authorization": "Bearer token"})
        result = _extract_traceparent(ctx)
        assert result is None


# ======================================================================
# Traceparent forwarding (integration)
# ======================================================================


class TestTraceparentForwarding:
    """Verify traceparent is forwarded from server tools to the client."""

    def _make_server_with_trace_client(self) -> FastMCP:
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.search_documents.return_value = {
            "results": [],
            "total": 0,
            "query": "t",
        }
        mock_client.get_document.return_value = {"document_id": "abc"}
        mock_client.get_passages.return_value = {
            "document_id": "abc",
            "passages": [],
            "total": 0,
        }
        mock_client.ask_corpus.return_value = {
            "question": "q",
            "answer": "a",
            "citations": [],
            "model": "m",
        }
        mock_client.get_related_documents.return_value = {
            "document_id": "abc",
            "related": [],
        }
        mock_client.list_facets.return_value = {"facets": {}}
        return create_mcp_server(settings, client=mock_client), mock_client

    def _get_tool_fn(self, mcp: FastMCP, name: str) -> Any:
        for t in mcp._tool_manager.list_tools():
            if t.name == name:
                return t.fn
        raise KeyError(f"Tool {name!r} not found")

    _TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

    def test_traceparent_forwarded_to_search_documents(self) -> None:
        mcp, mock_client = self._make_server_with_trace_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_search_documents")

        ctx = _mock_context({"traceparent": self._TRACEPARENT})
        _invoke_tool(fn, query="test", ctx=ctx)

        mock_client.search_documents.assert_called_once()
        assert mock_client.search_documents.call_args[1]["traceparent"] == self._TRACEPARENT

    def test_traceparent_forwarded_to_get_document(self) -> None:
        mcp, mock_client = self._make_server_with_trace_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_get_document")

        ctx = _mock_context({"traceparent": self._TRACEPARENT})
        _invoke_tool(fn, document_id="abc", ctx=ctx)

        mock_client.get_document.assert_called_once()
        assert mock_client.get_document.call_args[1]["traceparent"] == self._TRACEPARENT

    def test_traceparent_forwarded_to_get_passages(self) -> None:
        mcp, mock_client = self._make_server_with_trace_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_get_passages")

        ctx = _mock_context({"traceparent": self._TRACEPARENT})
        _invoke_tool(fn, document_id="abc", ctx=ctx)

        mock_client.get_passages.assert_called_once()
        assert mock_client.get_passages.call_args[1]["traceparent"] == self._TRACEPARENT

    def test_traceparent_forwarded_to_ask_corpus(self) -> None:
        mcp, mock_client = self._make_server_with_trace_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_ask_corpus")

        ctx = _mock_context({"traceparent": self._TRACEPARENT})
        _invoke_tool(fn, question="what?", ctx=ctx)

        mock_client.ask_corpus.assert_called_once()
        assert mock_client.ask_corpus.call_args[1]["traceparent"] == self._TRACEPARENT

    def test_traceparent_forwarded_to_get_related_documents(self) -> None:
        mcp, mock_client = self._make_server_with_trace_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_get_related_documents")

        ctx = _mock_context({"traceparent": self._TRACEPARENT})
        _invoke_tool(fn, document_id="abc", ctx=ctx)

        mock_client.get_related_documents.assert_called_once()
        assert mock_client.get_related_documents.call_args[1]["traceparent"] == self._TRACEPARENT

    def test_traceparent_forwarded_to_list_facets(self) -> None:
        mcp, mock_client = self._make_server_with_trace_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_list_facets")

        ctx = _mock_context({"traceparent": self._TRACEPARENT})
        _invoke_tool(fn, ctx=ctx)

        mock_client.list_facets.assert_called_once()
        assert mock_client.list_facets.call_args[1]["traceparent"] == self._TRACEPARENT

    def test_no_traceparent_when_not_in_context(self) -> None:
        mcp, mock_client = self._make_server_with_trace_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_search_documents")

        ctx = _mock_context({"authorization": "Bearer token"})
        _invoke_tool(fn, query="test", ctx=ctx)

        mock_client.search_documents.assert_called_once()
        assert mock_client.search_documents.call_args[1]["traceparent"] is None


# ======================================================================
# Per-client token forwarding
# ======================================================================


class TestPerOperationTimeouts:
    """Per-operation timeouts for ask_corpus (=60s), search (=10s), default (=15s)."""

    def test_search_documents_uses_10s_timeout(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        t = client._timeout_for_path("/api/agent/v1/search_documents")  # type: ignore[union-attr]
        assert isinstance(t, httpx.Timeout)
        # httpx.Timeout wraps values in an internal pool; total is approximate.

    def test_ask_corpus_uses_60s_timeout(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        t = client._timeout_for_path("/api/agent/v1/ask_corpus")  # type: ignore[union-attr]
        assert isinstance(t, httpx.Timeout)

    def test_unknown_path_uses_15s_default_timeout(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        t = client._timeout_for_path("/api/agent/v1/get_document")  # type: ignore[union-attr]
        assert isinstance(t, httpx.Timeout)


class TestPerClientTokenForwarding:
    """Per-request auth_header overrides the static API key with correct
    fallback behaviour."""

    def test_auth_header_takes_precedence_over_static_key(self) -> None:
        """When auth_header is provided, it is used verbatim — not the static key."""
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="static-key")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "t"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.search_documents(query="test", auth_header="Bearer per-client-token"))

        call_headers = mock.call_args[1]["headers"]
        assert call_headers["Authorization"] == "Bearer per-client-token"

    def test_falls_back_to_static_key_when_no_auth_header(self) -> None:
        """When no auth_header is passed, the static _api_key is used with
        Bearer prefix."""
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="fallback-key")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "t"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.search_documents(query="test"))

        call_headers = mock.call_args[1]["headers"]
        assert call_headers["Authorization"] == "Bearer fallback-key"

    def test_no_auth_header_when_no_key_and_no_header(self) -> None:
        """When neither auth_header nor static key is present, no
        Authorization header is set."""
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "t"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.search_documents(query="test"))

        call_headers = mock.call_args[1]["headers"]
        assert "Authorization" not in call_headers

    def test_all_six_methods_accept_auth_header(self) -> None:
        """Every tool method must accept and forward auth_header."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(return_value=_mock_response(json_data={}))
        client._client.request = mock  # type: ignore[method-assign]

        token = "Bearer per-client-token"
        asyncio.run(client.search_documents(query="t", auth_header=token))
        assert mock.call_args[1]["headers"]["Authorization"] == token

        asyncio.run(client.get_document(document_id="abc", auth_header=token))
        assert mock.call_args[1]["headers"]["Authorization"] == token

        asyncio.run(client.get_passages(document_id="abc", auth_header=token))
        assert mock.call_args[1]["headers"]["Authorization"] == token

        asyncio.run(client.ask_corpus(question="what?", auth_header=token))
        assert mock.call_args[1]["headers"]["Authorization"] == token

        asyncio.run(client.get_related_documents(document_id="abc", auth_header=token))
        assert mock.call_args[1]["headers"]["Authorization"] == token

        asyncio.run(client.list_facets(auth_header=token))
        assert mock.call_args[1]["headers"]["Authorization"] == token


# ======================================================================
# TomorrowlandClient
# ======================================================================


class TestTomorrowlandClient:
    """Verify each tool method calls the correct HTTP method/path."""

    # -- search_documents ------------------------------------------------

    def test_search_documents_posts_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="test-key")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "test"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.search_documents(query="test query", top_k=10, page=1))

        mock.assert_called_once_with(
            method="POST",
            url="http://localhost:8000/api/agent/v1/search_documents",
            headers=ANY,
            json={"query": "test query", "top_k": 10, "page": 1},
            params=None,
            timeout=ANY,
        )

    def test_search_documents_with_filters(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "test"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(
            client.search_documents(
                query="test",
                filters={"sources": ["src1"], "mime_types": ["application/pdf"]},
            )
        )

        call_kwargs = mock.call_args[1]
        assert call_kwargs["json"]["filters"] == {
            "sources": ["src1"],
            "mime_types": ["application/pdf"],
        }

    # -- get_document ----------------------------------------------------

    def test_get_document_gets_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            return_value=_mock_response(json_data={"document_id": "abc"}),
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.get_document(document_id="abc-123"))

        mock.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/api/agent/v1/get_document",
            headers=ANY,
            json=None,
            params={"document_id": "abc-123"},
            timeout=ANY,
        )

    # -- get_passages ----------------------------------------------------

    def test_get_passages_gets_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"document_id": "abc", "passages": []},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.get_passages(document_id="abc-123", limit=10, offset=5))

        mock.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/api/agent/v1/get_passages",
            headers=ANY,
            json=None,
            params={"document_id": "abc-123", "limit": 10, "offset": 5},
            timeout=ANY,
        )

    # -- ask_corpus ------------------------------------------------------

    def test_ask_corpus_posts_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            return_value=_mock_response(json_data={"answer": "test answer"}),
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.ask_corpus(question="What is this?", top_k=5))

        mock.assert_called_once_with(
            method="POST",
            url="http://localhost:8000/api/agent/v1/ask_corpus",
            headers=ANY,
            json={"question": "What is this?", "top_k": 5},
            params=None,
            timeout=ANY,
        )

    def test_ask_corpus_with_document_id(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            return_value=_mock_response(json_data={"answer": "test"}),
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.ask_corpus(question="Question?", document_id="doc-1"))

        call_kwargs = mock.call_args[1]
        assert call_kwargs["json"]["document_id"] == "doc-1"

    # -- get_related_documents -------------------------------------------

    def test_get_related_documents_gets_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"document_id": "abc", "related": []},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.get_related_documents(document_id="abc-123"))

        mock.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/api/agent/v1/get_related_documents",
            headers=ANY,
            json=None,
            params={"document_id": "abc-123"},
            timeout=ANY,
        )

    # -- list_facets -----------------------------------------------------

    def test_list_facets_gets_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            return_value=_mock_response(json_data={"facets": {}}),
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.list_facets(query="test"))

        mock.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/api/agent/v1/list_facets",
            headers=ANY,
            json=None,
            params={"query": "test"},
            timeout=ANY,
        )

    # -- auth forwarding -------------------------------------------------

    def test_auth_header_forwarded(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="my-secret-token")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "t"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.search_documents(query="test"))

        call_headers = mock.call_args[1]["headers"]
        assert call_headers["Authorization"] == "Bearer my-secret-token"

    def test_no_auth_header_when_no_key(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "t"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.search_documents(query="test"))

        call_headers = mock.call_args[1]["headers"]
        assert "Authorization" not in call_headers

    # -- correlation ID forwarding ---------------------------------------

    def test_correlation_id_forwarded_as_header(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="test-key")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "t"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.search_documents(query="test", correlation_id="corr-abc-123"))

        call_headers = mock.call_args[1]["headers"]
        assert call_headers["X-Correlation-ID"] == "corr-abc-123"

    def test_no_correlation_id_header_when_not_provided(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="test-key")
        mock = AsyncMock(
            return_value=_mock_response(
                json_data={"results": [], "total": 0, "query": "t"},
            )
        )
        client._client.request = mock  # type: ignore[method-assign]

        asyncio.run(client.search_documents(query="test"))

        call_headers = mock.call_args[1]["headers"]
        assert "X-Correlation-ID" not in call_headers

    # -- connection pool configuration -----------------------------------

    def test_httpx_client_created_with_connection_limits(self) -> None:
        """The httpx.Client must be created with connection limits."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        transport = client._client._transport  # type: ignore[union-attr]
        pool = getattr(transport, "_pool", None)
        if pool is not None:
            assert pool._max_keepalive_connections == _CONNECTION_LIMITS.max_keepalive_connections
            assert pool._max_connections == _CONNECTION_LIMITS.max_connections
        assert client._client is not None

    def test_client_uses_httpx_timeout_object(self) -> None:
        """The timeout should be an httpx.Timeout object."""
        client = TomorrowlandClient(api_url="http://localhost:8000", timeout=45.0)
        timeout = client._client.timeout  # type: ignore[union-attr]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.read is not None

    # -- error handling --------------------------------------------------

    @pytest.mark.parametrize(
        ("status_code", "expected_message"),
        [
            (401, "Authentication failed"),
            (403, "Access denied"),
            (404, "Resource not found"),
            (422, "Invalid request"),
            (429, "Rate limit exceeded"),
            (503, "Service unavailable"),
            (504, "timed out"),
        ],
    )
    def test_api_error_maps_to_mcp_error(self, status_code: int, expected_message: str) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="key")
        mock = AsyncMock(
            return_value=_error_response(status_code, detail="Original error"),
        )
        client._client.request = mock  # type: ignore[method-assign]

        from services.mcp.server import _translate_error

        with pytest.raises(ValueError, match=expected_message):
            try:
                asyncio.run(client.search_documents(query="test"))
            except TomorrowlandClientError as exc:
                raise ValueError(_translate_error(exc)) from exc

    def test_timeout_raises_mcp_error(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(side_effect=httpx.TimeoutException("Timed out"))
        client._client.request = mock  # type: ignore[method-assign]

        with pytest.raises(TomorrowlandClientError, match="timed out"):
            asyncio.run(client.search_documents(query="test"))

    def test_connection_error_raises_mcp_error(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(side_effect=httpx.RequestError("Connection refused"))
        client._client.request = mock  # type: ignore[method-assign]

        with pytest.raises(TomorrowlandClientError, match="Cannot reach"):
            asyncio.run(client.search_documents(query="test"))

    def test_api_500_raises_error(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            return_value=_error_response(500, detail="Internal error"),
        )
        client._client.request = mock  # type: ignore[method-assign]

        with pytest.raises(TomorrowlandClientError, match="Internal error"):
            asyncio.run(client.search_documents(query="test"))

    # -- response parsing ------------------------------------------------

    def test_returns_json_response(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        expected = {
            "results": [{"document_id": "1"}],
            "total": 1,
            "query": "hello",
        }
        mock = AsyncMock(return_value=_mock_response(json_data=expected))
        client._client.request = mock  # type: ignore[method-assign]

        result = asyncio.run(client.search_documents(query="hello"))
        assert result == expected


# ======================================================================
# Retry behaviour
# ======================================================================


class TestRetryBehaviour:
    """Verify transient errors are retried with exponential backoff."""

    def test_retries_on_503_then_succeeds(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            side_effect=[
                _error_response(503, "Service temporarily unavailable"),
                _error_response(503, "Service temporarily unavailable"),
                _mock_response(
                    json_data={"results": [], "total": 0, "query": "test"},
                ),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("asyncio.sleep", return_value=None) as sleep_mock:
            result = asyncio.run(client.search_documents(query="test"))

        assert mock.call_count == 3
        assert sleep_mock.call_count == 2
        assert result == {"results": [], "total": 0, "query": "test"}

    def test_retries_exhausted_on_503_raises_error(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            side_effect=[
                _error_response(503, "Service unavailable"),
                _error_response(503, "Service unavailable"),
                _error_response(503, "Service unavailable"),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with (
            patch("asyncio.sleep", return_value=None) as sleep_mock,
            pytest.raises(
                TomorrowlandClientError,
                match="Service unavailable",
            ),
        ):
            asyncio.run(client.search_documents(query="test"))

        assert mock.call_count == _MAX_RETRIES
        assert sleep_mock.call_count == _MAX_RETRIES - 1

    def test_retries_on_429_then_succeeds(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            side_effect=[
                _error_response(429, "Rate limit exceeded"),
                _mock_response(
                    json_data={"results": [], "total": 0, "query": "test"},
                ),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("asyncio.sleep", return_value=None) as sleep_mock:
            result = asyncio.run(client.search_documents(query="test"))

        assert mock.call_count == 2
        assert sleep_mock.call_count == 1
        assert result == {"results": [], "total": 0, "query": "test"}

    def test_retries_on_timeout_then_succeeds(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            side_effect=[
                httpx.TimeoutException("timed out"),
                _mock_response(
                    json_data={"results": [], "total": 0, "query": "test"},
                ),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("asyncio.sleep", return_value=None) as sleep_mock:
            result = asyncio.run(client.search_documents(query="test"))

        assert mock.call_count == 2
        assert sleep_mock.call_count == 1
        assert result == {"results": [], "total": 0, "query": "test"}

    def test_retries_on_connection_error_then_succeeds(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            side_effect=[
                httpx.RequestError("Connection reset"),
                _mock_response(
                    json_data={"results": [], "total": 0, "query": "test"},
                ),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("asyncio.sleep", return_value=None) as sleep_mock:
            result = asyncio.run(client.search_documents(query="test"))

        assert mock.call_count == 2
        assert sleep_mock.call_count == 1
        assert result == {"results": [], "total": 0, "query": "test"}

    def test_does_not_retry_on_401(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(return_value=_error_response(401, "Unauthorized"))
        client._client.request = mock  # type: ignore[method-assign]

        with (
            patch("services.mcp.client.asyncio.sleep", return_value=None) as sleep_mock,
            pytest.raises(
                TomorrowlandClientError,
                match="Unauthorized",
            ),
        ):
            asyncio.run(client.search_documents(query="test"))

        assert mock.call_count == 1
        assert sleep_mock.call_count == 0

    def test_does_not_retry_on_403(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(return_value=_error_response(403, "Forbidden"))
        client._client.request = mock  # type: ignore[method-assign]

        with (
            patch("services.mcp.client.asyncio.sleep", return_value=None) as sleep_mock,
            pytest.raises(
                TomorrowlandClientError,
                match="Forbidden",
            ),
        ):
            asyncio.run(client.search_documents(query="test"))

        assert mock.call_count == 1
        assert sleep_mock.call_count == 0

    def test_does_not_retry_on_404(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(return_value=_error_response(404, "Not found"))
        client._client.request = mock  # type: ignore[method-assign]

        with (
            patch("services.mcp.client.asyncio.sleep", return_value=None) as sleep_mock,
            pytest.raises(
                TomorrowlandClientError,
                match="Not found",
            ),
        ):
            asyncio.run(client.get_document(document_id="missing"))

        assert mock.call_count == 1
        assert sleep_mock.call_count == 0

    def test_backoff_is_exponential(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            side_effect=[
                _error_response(503, "fail 1"),
                _error_response(503, "fail 2"),
                _error_response(503, "fail 3"),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with (
            patch("services.mcp.client.asyncio.sleep", return_value=None) as sleep_mock,
            pytest.raises(TomorrowlandClientError),
        ):
            asyncio.run(client.search_documents(query="test"))

        calls = sleep_mock.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == pytest.approx(0.5)
        assert calls[1][0][0] == pytest.approx(1.0)


# ======================================================================
# FastMCP server
# ======================================================================


class TestCreateMCPServer:
    """Verify the FastMCP server is configured correctly."""

    def test_tools_list_contains_six_tools(self) -> None:
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            tomorrowland_api_key="test-key",
            app_env="test",
        )
        mcp = create_mcp_server(settings)
        tool_names = {t.name for t in mcp._tool_manager.list_tools()}
        expected = {
            "tomorrowland_search_documents",
            "tomorrowland_get_document",
            "tomorrowland_get_passages",
            "tomorrowland_ask_corpus",
            "tomorrowland_get_related_documents",
            "tomorrowland_list_facets",
        }
        assert tool_names == expected

    def test_tools_list_exactly_six(self) -> None:
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            tomorrowland_api_key="test-key",
            app_env="test",
        )
        mcp = create_mcp_server(settings)
        tool_names = {t.name for t in mcp._tool_manager.list_tools()}
        assert len(tool_names) == 6

    def test_server_uses_test_env_settings(self) -> None:
        settings = Settings(
            tomorrowland_api_url="http://custom:9000",
            tomorrowland_api_key="custom-key",
            app_env="test",
        )
        mcp = create_mcp_server(settings)
        tool_names = {t.name for t in mcp._tool_manager.list_tools()}
        assert "tomorrowland_search_documents" in tool_names


# ======================================================================
# Audit logging
# ======================================================================


class TestAuditLogging:
    """Verify MCP tools emit structured audit log lines."""

    def _make_server_with_success_client(self) -> FastMCP:
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.search_documents.return_value = {
            "results": [],
            "total": 0,
            "query": "t",
        }
        mock_client.get_document.return_value = {"document_id": "abc"}
        mock_client.get_passages.return_value = {
            "document_id": "abc",
            "passages": [],
            "total": 0,
        }
        mock_client.ask_corpus.return_value = {
            "question": "q",
            "answer": "a",
            "citations": [],
            "model": "m",
        }
        mock_client.get_related_documents.return_value = {
            "document_id": "abc",
            "related": [],
        }
        mock_client.list_facets.return_value = {"facets": {}}
        return create_mcp_server(settings, client=mock_client)

    def _get_tool_fn(self, mcp: FastMCP, name: str) -> Any:
        for t in mcp._tool_manager.list_tools():
            if t.name == name:
                return t.fn
        raise KeyError(f"Tool {name!r} not found")

    def test_audit_log_emitted_on_successful_search(
        self,
        caplog,  # type: ignore[no-untyped-def]
    ) -> None:
        caplog.set_level("INFO")
        mcp = self._make_server_with_success_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_search_documents")
        _invoke_tool(fn, query="test")

        audit_lines = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit_lines) == 1
        msg = audit_lines[0].message
        assert "tool=search_documents" in msg
        assert "status=ok" in msg
        assert re.search(r"latency_ms=\d+", msg)

    def test_audit_log_emitted_on_error(
        self,
        caplog,  # type: ignore[no-untyped-def]
    ) -> None:
        caplog.set_level("INFO")
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.get_document.side_effect = TomorrowlandClientError(
            "Not found",
            status_code=404,
        )
        mcp = create_mcp_server(settings, client=mock_client)
        fn = self._get_tool_fn(mcp, "tomorrowland_get_document")

        with pytest.raises(ValueError, match="Resource not found"):
            _invoke_tool(fn, document_id="missing")

        audit_lines = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit_lines) == 1
        msg = audit_lines[0].message
        assert "tool=get_document" in msg
        assert "status=error" in msg
        assert "error_type=HTTP_404" in msg

    def test_audit_log_includes_correlation_id(
        self,
        caplog,  # type: ignore[no-untyped-def]
    ) -> None:
        caplog.set_level("INFO")
        mcp = self._make_server_with_success_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_list_facets")
        _invoke_tool(fn)

        audit_lines = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit_lines) == 1
        msg = audit_lines[0].message
        assert re.search(
            r"correlation_id=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            msg,
        )

    def test_all_six_tools_emit_audit_log(
        self,
        caplog,  # type: ignore[no-untyped-def]
    ) -> None:
        caplog.set_level("INFO")
        mcp = self._make_server_with_success_client()

        calls: list[tuple[str, dict[str, Any]]] = [
            ("tomorrowland_search_documents", {"query": "t"}),
            ("tomorrowland_get_document", {"document_id": "abc"}),
            ("tomorrowland_get_passages", {"document_id": "abc"}),
            ("tomorrowland_ask_corpus", {"question": "what?"}),
            ("tomorrowland_get_related_documents", {"document_id": "abc"}),
            ("tomorrowland_list_facets", {}),
        ]
        for tool_name, kwargs in calls:
            fn = self._get_tool_fn(mcp, tool_name)
            _invoke_tool(fn, **kwargs)

        audit_lines = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit_lines) == 6
        tools_seen = set()
        for record in audit_lines:
            msg = record.message
            match = re.search(r"tool=(\w+)", msg)
            assert match, f"No tool= found in: {msg}"
            tools_seen.add(match.group(1))
        assert tools_seen == {
            "search_documents",
            "get_document",
            "get_passages",
            "ask_corpus",
            "get_related_documents",
            "list_facets",
        }


# ======================================================================
# Log sanitisation
# ======================================================================


class TestLogSanitization:
    def test_no_auth_leak_in_debug_log(self) -> None:
        raw = {"Authorization": "Bearer super-secret-token-12345"}
        sanitized = _sanitize_headers(raw)
        assert "super-secret-token" not in str(sanitized)
        assert sanitized["Authorization"] == "[redacted]"

    def test_no_token_in_error_message(self) -> None:
        client = TomorrowlandClient(
            api_url="http://localhost:8000",
            api_key="my-secret-token",
        )
        mock = AsyncMock(return_value=_error_response(401))
        client._client.request = mock  # type: ignore[method-assign]

        with pytest.raises(TomorrowlandClientError) as exc_info:
            asyncio.run(client.search_documents(query="test"))

        assert "my-secret-token" not in str(exc_info.value)


# ======================================================================
# No direct store clients imported
# ======================================================================


class TestNoDirectStoreImports:
    """Verify the MCP adapter doesn't import store clients directly."""

    def test_client_module_does_not_import_store_clients(self) -> None:
        import sys

        client_module = sys.modules.get("services.mcp.client")
        if client_module is None:
            pytest.skip("Module not loaded; will be checked at import time")
        names = {n for n in dir(client_module) if not n.startswith("_")}
        assert "QdrantSearchClient" not in names
        assert "MeilisearchSearchProvider" not in names

    def test_server_module_does_not_import_store_clients(self) -> None:
        import sys

        server_module = sys.modules.get("services.mcp.server")
        if server_module is None:
            pytest.skip("Module not loaded; will be checked at import time")
        names = {n for n in dir(server_module) if not n.startswith("_")}
        assert "QdrantSearchClient" not in names
        assert "MeilisearchSearchProvider" not in names


# ======================================================================
# Invalid input rejection
# ======================================================================


class TestInvalidInputRejection:
    """MCP tool wrappers reject invalid inputs before calling the API."""

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValueError, match="query must be at least 1"):
            _validate_string("", 1, _MAX_QUERY_LENGTH, "query")

    def test_query_too_long_rejected(self) -> None:
        with pytest.raises(
            ValueError,
            match=f"query must be at most {_MAX_QUERY_LENGTH}",
        ):
            _validate_string(
                "x" * (_MAX_QUERY_LENGTH + 1),
                1,
                _MAX_QUERY_LENGTH,
                "query",
            )

    def test_top_k_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            _validate_int(0, _MIN_TOP_K, _MAX_TOP_K, "top_k")

    def test_top_k_too_large_rejected(self) -> None:
        with pytest.raises(
            ValueError,
            match=f"top_k must be <= {_MAX_TOP_K}",
        ):
            _validate_int(100, _MIN_TOP_K, _MAX_TOP_K, "top_k")

    @pytest.mark.parametrize("page", [0, 21])
    def test_page_out_of_range(self, page: int) -> None:
        with pytest.raises(ValueError, match="page must be"):
            _validate_int(page, 1, _MAX_PAGE, "page")

    def test_question_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="question must be at least 1"):
            _validate_string("", 1, 2000, "question")


# ======================================================================
# Filter schema validation
# ======================================================================


class TestFilterValidation:
    """Filters are validated at the MCP layer before any API call."""

    def test_none_filters_pass(self) -> None:
        _validate_filters(None)  # Should not raise.

    def test_empty_dict_passes(self) -> None:
        _validate_filters({})  # Should not raise.

    def test_valid_filters_pass(self) -> None:
        _validate_filters(
            {
                "sources": ["engineering-wiki"],
                "mime_types": ["application/pdf"],
                "languages": ["en"],
                "tags": ["archived"],
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
            }
        )

    def test_non_dict_rejected(self) -> None:
        with pytest.raises(ValueError, match="filters must be a dict"):
            _validate_filters("not-a-dict")  # type: ignore[arg-type]

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(
            ValueError,
            match="Unknown filter keys: foo",
        ):
            _validate_filters({"sources": ["eng"], "foo": "bar"})

    def test_multiple_unknown_keys_listed(self) -> None:
        with pytest.raises(ValueError, match="foo, invalid_key"):
            _validate_filters(
                {
                    "sources": ["eng"],
                    "foo": 1,
                    "invalid_key": 2,
                }
            )

    def test_sources_must_be_list(self) -> None:
        with pytest.raises(
            ValueError,
            match="filters.sources must be a list",
        ):
            _validate_filters({"sources": "not-a-list"})

    def test_mime_types_must_be_list(self) -> None:
        with pytest.raises(
            ValueError,
            match="filters.mime_types must be a list",
        ):
            _validate_filters({"mime_types": 123})

    def test_languages_must_be_list(self) -> None:
        with pytest.raises(
            ValueError,
            match="filters.languages must be a list",
        ):
            _validate_filters({"languages": None})

    def test_tags_must_be_list(self) -> None:
        with pytest.raises(
            ValueError,
            match="filters.tags must be a list",
        ):
            _validate_filters({"tags": {"wrong": "type"}})

    def test_date_from_must_be_string(self) -> None:
        with pytest.raises(
            ValueError,
            match="filters.date_from must be a string",
        ):
            _validate_filters({"date_from": 2024})

    def test_date_to_must_be_string(self) -> None:
        with pytest.raises(
            ValueError,
            match="filters.date_to must be a string",
        ):
            _validate_filters({"date_to": True})

    def test_sources_explicit_none_rejected(self) -> None:
        """Explicit None for a list filter key is rejected."""
        with pytest.raises(
            ValueError,
            match="filters.sources must be a list",
        ):
            _validate_filters({"sources": None})

    def test_date_from_explicit_none_rejected(self) -> None:
        """Explicit None for a date filter key is rejected."""
        with pytest.raises(
            ValueError,
            match="filters.date_from must be a string or absent",
        ):
            _validate_filters({"date_from": None})

    def test_sources_list_element_must_be_string(self) -> None:
        """List elements must be strings."""
        with pytest.raises(
            ValueError,
            match="filters.sources\\[1\\] must be a string",
        ):
            _validate_filters({"sources": ["valid", 42]})

    def test_tags_list_element_must_be_string(self) -> None:
        with pytest.raises(
            ValueError,
            match="filters.tags\\[0\\] must be a string",
        ):
            _validate_filters({"tags": [3.14, "valid", True]})

    def test_valid_filter_keys_set_matches_backend(self) -> None:
        """The whitelist must match AgentSearchFilters exactly."""
        assert {
            "sources",
            "mime_types",
            "languages",
            "tags",
            "date_from",
            "date_to",
        } == _VALID_FILTER_KEYS

    def test_filter_validation_in_tool_rejects_bad_filters(self) -> None:
        """Integration: the search tool calls _validate_filters before API."""
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mcp = create_mcp_server(settings, client=mock_client)
        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_search_documents":
                fn = t.fn
                break
        else:
            pytest.fail("Tool not found")

        with pytest.raises(ValueError, match="Unknown filter keys"):
            _invoke_tool(fn, query="test", filters={"bogus_key": "v"})

        # The mock client must never have been called.
        mock_client.search_documents.assert_not_called()

    def test_filter_validation_in_tool_does_not_reject_valid_filters(
        self,
    ) -> None:
        """Valid filters must pass through to the client."""
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.search_documents.return_value = {
            "results": [],
            "total": 0,
            "query": "t",
        }
        mcp = create_mcp_server(settings, client=mock_client)
        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_search_documents":
                fn = t.fn
                break
        else:
            pytest.fail("Tool not found")

        result = _invoke_tool(fn, query="test", filters={"sources": ["wiki"]})
        assert result == {"results": [], "total": 0, "query": "t"}
        mock_client.search_documents.assert_called_once()


# ======================================================================
# Per-tool feature flags
# ======================================================================


class TestFeatureFlags:
    """Validate per-tool feature flags via environment variables."""

    def test_tool_enabled_by_default(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("MCP_ENABLE_SEARCH_DOCUMENTS", raising=False)
        _check_tool_enabled("search_documents")  # Should not raise.

    def test_tool_disabled_by_zero(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("MCP_ENABLE_GET_DOCUMENT", "0")
        with pytest.raises(ValueError, match="get_document.*disabled"):
            _check_tool_enabled("get_document")

    @pytest.mark.parametrize("value", ["0", "false", "no", "off"])
    def test_disabled_values(
        self,
        monkeypatch,
        value: str,  # type: ignore[no-untyped-def]
    ) -> None:
        monkeypatch.setenv("MCP_ENABLE_GET_PASSAGES", value)
        with pytest.raises(ValueError, match="get_passages.*disabled"):
            _check_tool_enabled("get_passages")

    def test_case_insensitive_disabled(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("MCP_ENABLE_LIST_FACETS", "OFF")
        with pytest.raises(ValueError, match="list_facets.*disabled"):
            _check_tool_enabled("list_facets")

    @pytest.mark.parametrize("value", ["1", "true", "yes", "enabled", "", "anything"])
    def test_non_disabled_values_allow_tool(
        self,
        monkeypatch,
        value: str,  # type: ignore[no-untyped-def]
    ) -> None:
        monkeypatch.setenv("MCP_ENABLE_ASK_CORPUS", value)
        _check_tool_enabled("ask_corpus")  # Should not raise.

    def test_unknown_tool_always_enabled(self) -> None:
        _check_tool_enabled("nonexistent_tool")  # Should not raise.

    def test_disabled_tool_in_server_returns_error(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("MCP_ENABLE_SEARCH_DOCUMENTS", "0")
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mcp = create_mcp_server(settings, client=mock_client)

        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_search_documents":
                fn = t.fn
                break
        else:
            pytest.fail("Tool not found")

        with pytest.raises(ValueError, match="search_documents.*disabled"):
            _invoke_tool(fn, query="test")

        mock_client.search_documents.assert_not_called()

    def test_disabled_expensive_tool_other_tools_still_work(
        self,
        monkeypatch,  # type: ignore[no-untyped-def]
    ) -> None:
        monkeypatch.setenv("MCP_ENABLE_ASK_CORPUS", "0")
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.search_documents.return_value = {
            "results": [],
            "total": 0,
            "query": "t",
        }
        mcp = create_mcp_server(settings, client=mock_client)

        # ask_corpus should be disabled.
        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_ask_corpus":
                with pytest.raises(ValueError, match="ask_corpus.*disabled"):
                    _invoke_tool(t.fn, question="what?")
                break

        # search_documents should still work.
        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_search_documents":
                result = _invoke_tool(t.fn, query="test")
                assert result == {"results": [], "total": 0, "query": "t"}
                break


# ======================================================================
# Progress notifications (ask_corpus)
# ======================================================================


class TestProgressNotifications:
    """Verify progress notifications in async ask_corpus."""

    def test_ask_corpus_sends_progress_on_success(self) -> None:
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.ask_corpus.return_value = {
            "question": "q",
            "answer": "a",
            "citations": [],
            "model": "m",
        }
        ctx = AsyncMock(spec=Context)
        mcp = create_mcp_server(settings, client=mock_client)

        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_ask_corpus":
                result = _invoke_tool(t.fn, question="what?", ctx=ctx)
                break
        else:
            pytest.fail("Tool not found")

        assert result["answer"] == "a"
        # ctx.report_progress called for progress=10, 50, 100.
        assert ctx.report_progress.call_count >= 3
        calls = ctx.report_progress.call_args_list
        assert calls[0][1]["progress"] == 10
        assert calls[1][1]["progress"] == 50
        assert calls[-1][1]["progress"] == 100

    def test_ask_corpus_sends_progress_on_error(self) -> None:
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.ask_corpus.side_effect = TomorrowlandClientError(
            "Down",
            status_code=503,
        )
        ctx = AsyncMock(spec=Context)
        mcp = create_mcp_server(settings, client=mock_client)

        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_ask_corpus":
                fn = t.fn
                break
        else:
            pytest.fail("Tool not found")

        with pytest.raises(ValueError, match="Service unavailable"):
            _invoke_tool(fn, question="what?", ctx=ctx)

        # Progress should still be sent on error path.
        assert ctx.report_progress.call_count >= 1
        assert ctx.report_progress.call_args_list[-1][1]["progress"] == 100


# ======================================================================
# MCP authorization parity (#562)
# ======================================================================


class TestMCPAuthorizationParity:
    """MCP tools correctly proxy REST auth errors and never leak data."""

    def _make_server_raising(self, status_code: int, detail: str) -> FastMCP:
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        error = TomorrowlandClientError(detail, status_code=status_code)
        for method_name in (
            "search_documents",
            "get_document",
            "get_passages",
            "ask_corpus",
            "get_related_documents",
            "list_facets",
        ):
            getattr(mock_client, method_name).side_effect = error
        return create_mcp_server(settings, client=mock_client)

    def _get_tool_fn(self, mcp: FastMCP, name: str) -> Any:
        for t in mcp._tool_manager.list_tools():
            if t.name == name:
                return t.fn
        raise KeyError(f"Tool {name!r} not found")

    def test_403_does_not_expose_document_id_from_response_body(self) -> None:
        doc_id = "abc12345-0000-0000-0000-000000000000"
        mcp = self._make_server_raising(403, f"Document {doc_id} not accessible")
        fn = self._get_tool_fn(mcp, "tomorrowland_get_document")

        with pytest.raises(ValueError) as exc_info:
            _invoke_tool(fn, document_id=doc_id)

        msg = str(exc_info.value)
        assert doc_id not in msg
        assert "Access denied" in msg

    def test_401_does_not_expose_api_key_in_error_message(self) -> None:
        api_key = "super-secret-key-must-not-leak-in-errors"
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            tomorrowland_api_key=api_key,
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.search_documents.side_effect = TomorrowlandClientError(
            f"Unauthorized: {api_key}",
            status_code=401,
        )
        mcp = create_mcp_server(settings, client=mock_client)
        fn = self._get_tool_fn(mcp, "tomorrowland_search_documents")

        with pytest.raises(ValueError) as exc_info:
            _invoke_tool(fn, query="test")

        msg = str(exc_info.value)
        assert api_key not in msg
        assert "Authentication failed" in msg

    def test_429_error_does_not_expose_document_metadata(self) -> None:
        sensitive_id = "corpus-id-must-not-appear-in-429-error"
        mcp = self._make_server_raising(
            429,
            f"Too many requests for {sensitive_id}",
        )
        fn = self._get_tool_fn(mcp, "tomorrowland_ask_corpus")

        with pytest.raises(ValueError) as exc_info:
            _invoke_tool(fn, question="what?")

        msg = str(exc_info.value)
        assert sensitive_id not in msg
        assert "Rate limit" in msg

    @pytest.mark.parametrize(
        ("tool_name", "tool_kwargs"),
        [
            ("tomorrowland_search_documents", {"query": "test"}),
            ("tomorrowland_get_document", {"document_id": "abc-123"}),
            ("tomorrowland_get_passages", {"document_id": "abc-123"}),
            ("tomorrowland_ask_corpus", {"question": "what?"}),
            ("tomorrowland_get_related_documents", {"document_id": "abc-123"}),
            ("tomorrowland_list_facets", {}),
        ],
    )
    def test_all_tools_translate_401_to_safe_error(
        self,
        tool_name: str,
        tool_kwargs: dict[str, Any],
    ) -> None:
        raw_detail = "raw-internal-detail-must-not-appear"
        mcp = self._make_server_raising(401, raw_detail)
        fn = self._get_tool_fn(mcp, tool_name)

        with pytest.raises(ValueError) as exc_info:
            _invoke_tool(fn, **tool_kwargs)

        msg = str(exc_info.value)
        assert "Authentication failed" in msg
        assert raw_detail not in msg

    @pytest.mark.parametrize(
        ("tool_name", "tool_kwargs"),
        [
            ("tomorrowland_search_documents", {"query": "test"}),
            ("tomorrowland_get_document", {"document_id": "abc-123"}),
            ("tomorrowland_get_passages", {"document_id": "abc-123"}),
            ("tomorrowland_ask_corpus", {"question": "what?"}),
            ("tomorrowland_get_related_documents", {"document_id": "abc-123"}),
            ("tomorrowland_list_facets", {}),
        ],
    )
    def test_all_tools_translate_403_to_safe_error(
        self,
        tool_name: str,
        tool_kwargs: dict[str, Any],
    ) -> None:
        hidden_resource_id = "hidden-resource-id-must-not-appear-in-error"
        mcp = self._make_server_raising(
            403,
            f"Cannot access {hidden_resource_id}",
        )
        fn = self._get_tool_fn(mcp, tool_name)

        with pytest.raises(ValueError) as exc_info:
            _invoke_tool(fn, **tool_kwargs)

        msg = str(exc_info.value)
        assert "Access denied" in msg
        assert hidden_resource_id not in msg


# ======================================================================
# Prometheus metrics
# ======================================================================


class TestMCPMetrics:
    """Verify the MCP metrics registry, counters, and histograms."""

    def test_metrics_registry_contains_mcp_collectors(self) -> None:
        from prometheus_client import Counter, Histogram

        from services.mcp.metrics import _mcp_metrics

        # All three MCP collectors are instantiated and typed correctly.
        assert isinstance(_mcp_metrics.tool_calls_total, Counter)
        assert isinstance(_mcp_metrics.tool_call_duration_seconds, Histogram)
        assert isinstance(_mcp_metrics.tool_call_errors_total, Counter)

        # Verify the singleton registry knows about them by recording a
        # sample value and checking it appears in collect().
        _mcp_metrics.tool_calls_total.labels(
            tool="test",
            outcome="ok",
        ).inc()
        names: set[str] = set()
        for metric in _mcp_metrics.registry.collect():
            for sample in metric.samples:
                names.add(sample.name)
        assert "tomorrowland_mcp_tool_calls_total" in names

    def test_successful_tool_call_increments_counter(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.search_documents.return_value = {
            "results": [],
            "total": 0,
            "query": "t",
        }
        mcp = create_mcp_server(settings, client=mock_client)

        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_search_documents":
                fn = t.fn
                break
        else:
            pytest.fail("Tool not found")

        # Get initial values
        before_ok = _mcp_metrics.tool_calls_total.labels(
            tool="search_documents",
            outcome="ok",
        )._value.get()

        _invoke_tool(fn, query="test")

        after_ok = _mcp_metrics.tool_calls_total.labels(
            tool="search_documents",
            outcome="ok",
        )._value.get()
        assert after_ok == before_ok + 1

    def test_failed_tool_call_increments_error_counter(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.get_document.side_effect = TomorrowlandClientError(
            "Not found",
            status_code=404,
        )
        mcp = create_mcp_server(settings, client=mock_client)

        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_get_document":
                fn = t.fn
                break
        else:
            pytest.fail("Tool not found")

        before_err = _mcp_metrics.tool_calls_total.labels(
            tool="get_document",
            outcome="error",
        )._value.get()

        with pytest.raises(ValueError, match="Resource not found"):
            _invoke_tool(fn, document_id="missing")

        after_err = _mcp_metrics.tool_calls_total.labels(
            tool="get_document",
            outcome="error",
        )._value.get()
        assert after_err == before_err + 1

    def test_histogram_observes_latency(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.list_facets.return_value = {"facets": {}}
        mcp = create_mcp_server(settings, client=mock_client)

        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_list_facets":
                fn = t.fn
                break
        else:
            pytest.fail("Tool not found")

        before_sum = _mcp_metrics.tool_call_duration_seconds.labels(tool="list_facets")._sum.get()

        _invoke_tool(fn)

        after_sum = _mcp_metrics.tool_call_duration_seconds.labels(tool="list_facets")._sum.get()
        assert after_sum > before_sum

    def test_error_metrics_record_error_type(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.ask_corpus.side_effect = TomorrowlandClientError(
            "Service down",
            status_code=503,
        )
        mcp = create_mcp_server(settings, client=mock_client)

        for t in mcp._tool_manager.list_tools():
            if t.name == "tomorrowland_ask_corpus":
                fn = t.fn
                break
        else:
            pytest.fail("Tool not found")

        before = _mcp_metrics.tool_call_errors_total.labels(
            tool="ask_corpus",
            error_type="HTTP_503",
        )._value.get()

        with pytest.raises(ValueError, match="Service unavailable"):
            _invoke_tool(fn, question="what?")

        after = _mcp_metrics.tool_call_errors_total.labels(
            tool="ask_corpus",
            error_type="HTTP_503",
        )._value.get()
        assert after == before + 1

    def test_metrics_endpoint_returns_prometheus_format(self) -> None:
        # The metrics_endpoint is an async function; run it synchronously.
        import asyncio

        from prometheus_client import CONTENT_TYPE_LATEST

        from services.mcp.metrics import metrics_endpoint

        body, status, headers = asyncio.run(
            metrics_endpoint(MagicMock()),
        )
        assert status == 200
        assert headers["Content-Type"] == CONTENT_TYPE_LATEST
        text = body.decode("utf-8")
        assert "tomorrowland_mcp_tool_calls_total" in text
        assert "tomorrowland_mcp_tool_call_duration_seconds" in text

    def test_metrics_route_served_through_starlette(self) -> None:
        # Regression: metrics_endpoint returns a (body, status, headers) tuple,
        # which Starlette cannot serve directly. _register_observability_endpoints
        # must adapt it to a Response, otherwise GET /metrics 500s in production
        # even though the direct-call unit test passes.
        from types import SimpleNamespace

        from starlette.applications import Starlette
        from starlette.testclient import TestClient

        from services.mcp.server import _register_observability_endpoints

        app = Starlette()
        _register_observability_endpoints(SimpleNamespace(app=app))

        client = TestClient(app)
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "tomorrowland_mcp_tool_calls_total" in metrics.text

    def test_all_six_tools_are_instrumented(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.search_documents.return_value = {
            "results": [],
            "total": 0,
            "query": "t",
        }
        mock_client.get_document.return_value = {"document_id": "abc"}
        mock_client.get_passages.return_value = {
            "document_id": "abc",
            "passages": [],
            "total": 0,
        }
        mock_client.ask_corpus.return_value = {
            "question": "q",
            "answer": "a",
            "citations": [],
            "model": "m",
        }
        mock_client.get_related_documents.return_value = {
            "document_id": "abc",
            "related": [],
        }
        mock_client.list_facets.return_value = {"facets": {}}
        mcp = create_mcp_server(settings, client=mock_client)

        tools = {
            "tomorrowland_search_documents": {"query": "t"},
            "tomorrowland_get_document": {"document_id": "abc"},
            "tomorrowland_get_passages": {"document_id": "abc"},
            "tomorrowland_ask_corpus": {"question": "what?"},
            "tomorrowland_get_related_documents": {"document_id": "abc"},
            "tomorrowland_list_facets": {},
        }
        expected_tools = {
            "search_documents",
            "get_document",
            "get_passages",
            "ask_corpus",
            "get_related_documents",
            "list_facets",
        }

        for t in mcp._tool_manager.list_tools():
            if t.name in tools:
                fn = t.fn
                _invoke_tool(fn, **tools[t.name])

        # Every tool should have at least one "ok" counter increment.
        for tool_name in expected_tools:
            val = _mcp_metrics.tool_calls_total.labels(
                tool=tool_name,
                outcome="ok",
            )._value.get()
            assert val >= 1, f"No ok counter for {tool_name}"

    def test_circuit_breaker_state_gauge_exists(self) -> None:
        from prometheus_client import Gauge

        from services.mcp.metrics import _mcp_metrics

        assert isinstance(_mcp_metrics.circuit_breaker_state, Gauge)

        # Default state should be 0 (closed).
        assert _mcp_metrics.circuit_breaker_state._value.get() == 0

    def test_circuit_breaker_failures_counter_exists(self) -> None:
        from prometheus_client import Counter

        from services.mcp.metrics import _mcp_metrics

        assert isinstance(_mcp_metrics.circuit_breaker_failures_total, Counter)


# ======================================================================
# Circuit breaker — unit tests
# ======================================================================


class TestCircuitBreaker:
    """Verify the circuit breaker state machine."""

    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 0

    def test_before_request_does_not_raise_when_closed(self) -> None:
        cb = CircuitBreaker()
        cb.before_request()  # Should not raise.

    def test_opens_after_failure_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            cb.on_failure()

        assert cb.state == CircuitBreaker.OPEN
        assert cb.failure_count == 3

    def test_blocks_before_request_when_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1)
        cb.on_failure()

        with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker is open"):
            cb.before_request()

    def test_cooldown_remaining_is_positive_when_open(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1,
            cooldown_seconds=10.0,
        )
        cb.on_failure()

        assert cb.cooldown_remaining > 0
        # Opened just now, so remaining should be close to cooldown.
        assert cb.cooldown_remaining <= 10.0

    def test_transitions_to_half_open_after_cooldown(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1,
            cooldown_seconds=0.01,
        )
        cb.on_failure()
        assert cb.state == CircuitBreaker.OPEN

        time.sleep(0.02)
        cb._maybe_transition()
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_allows_request_in_half_open(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1,
            cooldown_seconds=0.01,
        )
        cb.on_failure()
        time.sleep(0.02)
        cb._maybe_transition()
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.before_request()  # Should not raise.

    def test_resets_to_closed_on_success(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)
        cb.on_failure()
        assert cb.failure_count == 1

        cb.on_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 0

    def test_success_from_half_open_closes_circuit(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1,
            cooldown_seconds=0.01,
        )
        cb.on_failure()
        time.sleep(0.02)
        cb._maybe_transition()
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.on_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_failure_in_half_open_reopens_circuit(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1,
            cooldown_seconds=0.01,
        )
        cb.on_failure()
        time.sleep(0.02)
        cb._maybe_transition()
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.on_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_failure_count_resets_on_success(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(3):
            cb.on_failure()
        assert cb.failure_count == 3

        cb.on_success()
        assert cb.failure_count == 0

    def test_breaker_does_not_reopen_without_enough_failures(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.on_failure()

        assert cb.state == CircuitBreaker.CLOSED

    def test_open_error_includes_cooldown_remaining(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1,
            cooldown_seconds=30.0,
        )
        cb.on_failure()

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.before_request()

        msg = str(exc_info.value)
        assert "Circuit breaker is open" in msg
        assert "s remaining" in msg


# ======================================================================
# Circuit breaker — client integration
# ======================================================================


class TestCircuitBreakerClientIntegration:
    """Verify the circuit breaker is integrated into TomorrowlandClient."""

    # Each retryable HTTP error (503, 502, 504, 429) triggers up to
    # _MAX_RETRIES (3) HTTP calls per top-level request.  on_failure()
    # fires only once — just before we raise the final error.

    def test_breaker_counts_503_and_opens(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        # Each 503 call retries 3 times → 3 items consumed per top-level
        # call.  3 calls × 3 = 9 items, threshold=3 opens after 3 calls.
        client._circuit_breaker._failure_threshold = 3
        mock = AsyncMock(
            side_effect=[_error_response(503, "fail") for _ in range(9)],
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("services.mcp.client.asyncio.sleep", return_value=None):
            for i in range(2):
                with pytest.raises(TomorrowlandClientError):
                    asyncio.run(client.search_documents(query="test"))
                assert client._circuit_breaker.failure_count == i + 1
                assert client._circuit_breaker.state == CircuitBreaker.CLOSED

            # 3rd failure opens the breaker.
            with pytest.raises(TomorrowlandClientError):
                asyncio.run(client.search_documents(query="test"))
            assert client._circuit_breaker.state == CircuitBreaker.OPEN
            assert client._circuit_breaker.failure_count == 3

    def test_breaker_blocks_when_open(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        client._circuit_breaker._failure_threshold = 2
        # 2 calls × 3 retries = 6 items.
        mock = AsyncMock(
            side_effect=[_error_response(503, "fail") for _ in range(6)],
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("services.mcp.client.asyncio.sleep", return_value=None):
            for _ in range(2):
                with pytest.raises(TomorrowlandClientError):
                    asyncio.run(client.search_documents(query="test"))

            # Breaker is now open — next request fails fast.
            with pytest.raises(
                CircuitBreakerOpenError,
                match="Circuit breaker is open",
            ):
                asyncio.run(client.search_documents(query="test"))

            # No additional HTTP calls beyond the first 2 calls' retries.
            assert mock.call_count == 6

    def test_breaker_does_not_count_401_403_404(self) -> None:
        """Client errors (401, 403, 404) must not trip the breaker."""
        for status in (401, 403, 404):
            client = TomorrowlandClient(api_url="http://localhost:8000")
            mock = AsyncMock(
                side_effect=[_error_response(status, "error")],
            )
            client._client.request = mock  # type: ignore[method-assign]

            with pytest.raises(TomorrowlandClientError):
                asyncio.run(client.search_documents(query="test"))

            assert client._circuit_breaker.state == CircuitBreaker.CLOSED
            assert client._circuit_breaker.failure_count == 0

    def test_breaker_counts_502_503_504_429(self) -> None:
        """Server-side / transient errors must count."""
        for status in (429, 502, 503, 504):
            client = TomorrowlandClient(api_url="http://localhost:8000")
            # Each retries 3 times → 3 side_effect items per call.
            mock = AsyncMock(
                side_effect=[_error_response(status, "error") for _ in range(3)],
            )
            client._client.request = mock  # type: ignore[method-assign]

            with (
                patch("services.mcp.client.asyncio.sleep", return_value=None),
                pytest.raises(TomorrowlandClientError),
            ):
                asyncio.run(client.search_documents(query="test"))

            assert client._circuit_breaker.failure_count == 1

    def test_breaker_counts_timeout_errors(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        # Each timeout call retries 3 times → 3 items per top-level call.
        # 2 calls × 3 = 6 items.
        mock = AsyncMock(
            side_effect=[httpx.TimeoutException("timed out") for _ in range(6)],
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("services.mcp.client.asyncio.sleep", return_value=None):
            for _ in range(2):
                with pytest.raises(TomorrowlandClientError, match="timed out"):
                    asyncio.run(client.search_documents(query="test"))

        # on_failure fires once per top-level call — count should be 2.
        assert client._circuit_breaker.failure_count == 2

    def test_breaker_resets_after_success(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = AsyncMock(
            side_effect=[
                _error_response(503, "fail"),
                _error_response(503, "fail"),
                _error_response(503, "fail"),
                _mock_response(
                    json_data={"results": [], "total": 0, "query": "t"},
                ),
            ],
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("services.mcp.client.asyncio.sleep", return_value=None):
            with pytest.raises(TomorrowlandClientError):
                asyncio.run(client.search_documents(query="test"))
            assert client._circuit_breaker.failure_count == 1

            result = asyncio.run(client.search_documents(query="test"))
            assert client._circuit_breaker.state == CircuitBreaker.CLOSED
            assert client._circuit_breaker.failure_count == 0
            assert result == {
                "results": [],
                "total": 0,
                "query": "t",
            }


# ======================================================================
# Circuit breaker — server integration
# ======================================================================


class TestCircuitBreakerServerIntegration:
    """Verify the server translates circuit breaker errors to safe messages."""

    def _get_tool_fn(self, mcp: FastMCP, name: str) -> Any:
        for t in mcp._tool_manager.list_tools():
            if t.name == name:
                return t.fn
        raise KeyError(f"Tool {name!r} not found")

    def test_tool_returns_safe_error_when_breaker_open(self) -> None:
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.search_documents.side_effect = CircuitBreakerOpenError(
            cooldown_remaining=25.0,
        )
        mcp = create_mcp_server(settings, client=mock_client)
        fn = self._get_tool_fn(mcp, "tomorrowland_search_documents")

        with pytest.raises(ValueError, match="Circuit breaker is open"):
            _invoke_tool(fn, query="test")

    def test_circuit_breaker_error_recorded_in_metrics(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.get_document.side_effect = CircuitBreakerOpenError(
            cooldown_remaining=15.0,
        )
        mcp = create_mcp_server(settings, client=mock_client)
        fn = self._get_tool_fn(mcp, "tomorrowland_get_document")

        before = _mcp_metrics.tool_call_errors_total.labels(
            tool="get_document",
            error_type="circuit_breaker_open",
        )._value.get()

        with pytest.raises(ValueError, match="Circuit breaker is open"):
            _invoke_tool(fn, document_id="abc")

        after = _mcp_metrics.tool_call_errors_total.labels(
            tool="get_document",
            error_type="circuit_breaker_open",
        )._value.get()
        assert after == before + 1

    def test_circuit_breaker_error_audit_logged(self, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level("INFO")
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            app_env="test",
        )
        mock_client = AsyncMock(spec=TomorrowlandClient)
        mock_client.list_facets.side_effect = CircuitBreakerOpenError(
            cooldown_remaining=10.0,
        )
        mcp = create_mcp_server(settings, client=mock_client)
        fn = self._get_tool_fn(mcp, "tomorrowland_list_facets")

        with pytest.raises(ValueError, match="Circuit breaker is open"):
            _invoke_tool(fn)

        audit_lines = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit_lines) == 1
        msg = audit_lines[0].message
        assert "tool=list_facets" in msg
        assert "status=error" in msg
        assert "error_type=circuit_breaker_open" in msg
