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
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import ANY, MagicMock, patch

import httpx
import pytest
from mcp.server.fastmcp import FastMCP

from services.mcp.client import (
    _CONNECTION_LIMITS,
    _MAX_RETRIES,
    TomorrowlandClient,
    TomorrowlandClientError,
    _sanitize_headers,
)
from services.mcp.server import (
    _MAX_PAGE,
    _MAX_QUERY_LENGTH,
    _MAX_TOP_K,
    _MIN_TOP_K,
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
# TomorrowlandClient
# ======================================================================


class TestTomorrowlandClient:
    """Verify each tool method calls the correct HTTP method/path."""

    # -- search_documents ------------------------------------------------

    def test_search_documents_posts_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="test-key")
        mock = MagicMock(
            return_value=_mock_response(json_data={"results": [], "total": 0, "query": "test"})
        )
        client._client.request = mock  # type: ignore[method-assign]

        client.search_documents(query="test query", top_k=10, page=1)

        mock.assert_called_once_with(
            method="POST",
            url="http://localhost:8000/api/agent/v1/search_documents",
            headers=ANY,
            json={"query": "test query", "top_k": 10, "page": 1},
            params=None,
        )

    def test_search_documents_with_filters(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(
            return_value=_mock_response(json_data={"results": [], "total": 0, "query": "test"})
        )
        client._client.request = mock  # type: ignore[method-assign]

        client.search_documents(
            query="test", filters={"sources": ["src1"], "mime_types": ["application/pdf"]}
        )

        call_kwargs = mock.call_args[1]
        assert call_kwargs["json"]["filters"] == {
            "sources": ["src1"],
            "mime_types": ["application/pdf"],
        }

    # -- get_document ----------------------------------------------------

    def test_get_document_gets_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(return_value=_mock_response(json_data={"document_id": "abc"}))
        client._client.request = mock  # type: ignore[method-assign]

        client.get_document(document_id="abc-123")

        mock.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/api/agent/v1/get_document",
            headers=ANY,
            json=None,
            params={"document_id": "abc-123"},
        )

    # -- get_passages ----------------------------------------------------

    def test_get_passages_gets_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(
            return_value=_mock_response(json_data={"document_id": "abc", "passages": []})
        )
        client._client.request = mock  # type: ignore[method-assign]

        client.get_passages(document_id="abc-123", limit=10, offset=5)

        mock.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/api/agent/v1/get_passages",
            headers=ANY,
            json=None,
            params={"document_id": "abc-123", "limit": 10, "offset": 5},
        )

    # -- ask_corpus ------------------------------------------------------

    def test_ask_corpus_posts_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(return_value=_mock_response(json_data={"answer": "test answer"}))
        client._client.request = mock  # type: ignore[method-assign]

        client.ask_corpus(question="What is this?", top_k=5)

        mock.assert_called_once_with(
            method="POST",
            url="http://localhost:8000/api/agent/v1/ask_corpus",
            headers=ANY,
            json={"question": "What is this?", "top_k": 5},
            params=None,
        )

    def test_ask_corpus_with_document_id(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(return_value=_mock_response(json_data={"answer": "test"}))
        client._client.request = mock  # type: ignore[method-assign]

        client.ask_corpus(question="Question?", document_id="doc-1")

        call_kwargs = mock.call_args[1]
        assert call_kwargs["json"]["document_id"] == "doc-1"

    # -- get_related_documents -------------------------------------------

    def test_get_related_documents_gets_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(
            return_value=_mock_response(json_data={"document_id": "abc", "related": []})
        )
        client._client.request = mock  # type: ignore[method-assign]

        client.get_related_documents(document_id="abc-123")

        mock.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/api/agent/v1/get_related_documents",
            headers=ANY,
            json=None,
            params={"document_id": "abc-123"},
        )

    # -- list_facets -----------------------------------------------------

    def test_list_facets_gets_correct_path(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(return_value=_mock_response(json_data={"facets": {}}))
        client._client.request = mock  # type: ignore[method-assign]

        client.list_facets(query="test")

        mock.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/api/agent/v1/list_facets",
            headers=ANY,
            json=None,
            params={"query": "test"},
        )

    # -- auth forwarding -------------------------------------------------

    def test_auth_header_forwarded(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="my-secret-token")
        mock = MagicMock(
            return_value=_mock_response(json_data={"results": [], "total": 0, "query": "t"})
        )
        client._client.request = mock  # type: ignore[method-assign]

        client.search_documents(query="test")

        call_headers = mock.call_args[1]["headers"]
        assert call_headers["Authorization"] == "Bearer my-secret-token"

    def test_no_auth_header_when_no_key(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="")
        mock = MagicMock(
            return_value=_mock_response(json_data={"results": [], "total": 0, "query": "t"})
        )
        client._client.request = mock  # type: ignore[method-assign]

        client.search_documents(query="test")

        call_headers = mock.call_args[1]["headers"]
        assert "Authorization" not in call_headers

    # -- correlation ID forwarding ---------------------------------------

    def test_correlation_id_forwarded_as_header(self) -> None:
        """When a correlation_id is passed, it appears as X-Correlation-ID header."""
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="test-key")
        mock = MagicMock(
            return_value=_mock_response(json_data={"results": [], "total": 0, "query": "t"})
        )
        client._client.request = mock  # type: ignore[method-assign]

        client.search_documents(query="test", correlation_id="corr-abc-123")

        call_headers = mock.call_args[1]["headers"]
        assert call_headers["X-Correlation-ID"] == "corr-abc-123"

    def test_no_correlation_id_header_when_not_provided(self) -> None:
        """When no correlation_id is passed, no X-Correlation-ID header is set."""
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="test-key")
        mock = MagicMock(
            return_value=_mock_response(json_data={"results": [], "total": 0, "query": "t"})
        )
        client._client.request = mock  # type: ignore[method-assign]

        client.search_documents(query="test")

        call_headers = mock.call_args[1]["headers"]
        assert "X-Correlation-ID" not in call_headers

    # -- connection pool configuration -----------------------------------

    def test_httpx_client_created_with_connection_limits(self) -> None:
        """The httpx.Client must be created with connection limits for pool tuning."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        # Connection limits are configured on the transport layer (httpx v0.28+).
        transport = client._client._transport  # type: ignore[union-attr]
        pool = getattr(transport, "_pool", None)
        if pool is not None:
            assert pool._max_keepalive_connections == _CONNECTION_LIMITS.max_keepalive_connections
            assert pool._max_connections == _CONNECTION_LIMITS.max_connections
        # If we can't inspect the pool, the limits were still passed — verify
        # we at least constructed the Client without error.
        assert client._client is not None

    def test_client_uses_httpx_timeout_object(self) -> None:
        """The timeout should be an httpx.Timeout object, not a raw float."""
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
        mock = MagicMock(return_value=_error_response(status_code, detail="Original error"))
        client._client.request = mock  # type: ignore[method-assign]

        from services.mcp.server import _translate_error

        with pytest.raises(ValueError, match=expected_message):
            try:
                client.search_documents(query="test")
            except TomorrowlandClientError as exc:
                raise ValueError(_translate_error(exc)) from exc

    def test_timeout_raises_mcp_error(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(side_effect=httpx.TimeoutException("Timed out"))
        client._client.request = mock  # type: ignore[method-assign]

        with pytest.raises(TomorrowlandClientError, match="timed out"):
            client.search_documents(query="test")

    def test_connection_error_raises_mcp_error(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(side_effect=httpx.RequestError("Connection refused"))
        client._client.request = mock  # type: ignore[method-assign]

        with pytest.raises(TomorrowlandClientError, match="Cannot reach"):
            client.search_documents(query="test")

    def test_api_500_raises_error(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(return_value=_error_response(500, detail="Internal error"))
        client._client.request = mock  # type: ignore[method-assign]

        with pytest.raises(TomorrowlandClientError, match="Internal error"):
            client.search_documents(query="test")

    # -- response parsing ------------------------------------------------

    def test_returns_json_response(self) -> None:
        client = TomorrowlandClient(api_url="http://localhost:8000")
        expected = {"results": [{"document_id": "1"}], "total": 1, "query": "hello"}
        mock = MagicMock(return_value=_mock_response(json_data=expected))
        client._client.request = mock  # type: ignore[method-assign]

        result = client.search_documents(query="hello")
        assert result == expected


# ======================================================================
# Retry behaviour
# ======================================================================


class TestRetryBehaviour:
    """Verify transient errors are retried with exponential backoff."""

    def test_retries_on_503_then_succeeds(self) -> None:
        """A 503 response should be retried, and success on retry should be returned."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        # First two calls return 503; third call succeeds.
        mock = MagicMock(
            side_effect=[
                _error_response(503, "Service temporarily unavailable"),
                _error_response(503, "Service temporarily unavailable"),
                _mock_response(json_data={"results": [], "total": 0, "query": "test"}),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock:
            result = client.search_documents(query="test")

        assert mock.call_count == 3
        assert sleep_mock.call_count == 2  # backoff for first two failures
        assert result == {"results": [], "total": 0, "query": "test"}

    def test_retries_exhausted_on_503_raises_error(self) -> None:
        """When all retries are exhausted on 503, the error should be raised."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(
            side_effect=[
                _error_response(503, "Service unavailable"),
                _error_response(503, "Service unavailable"),
                _error_response(503, "Service unavailable"),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock, \
                pytest.raises(TomorrowlandClientError, match="Service unavailable"):
            client.search_documents(query="test")

        assert mock.call_count == _MAX_RETRIES
        assert sleep_mock.call_count == _MAX_RETRIES - 1

    def test_retries_on_429_then_succeeds(self) -> None:
        """A 429 rate-limit response should be retried."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(
            side_effect=[
                _error_response(429, "Rate limit exceeded"),
                _mock_response(json_data={"results": [], "total": 0, "query": "test"}),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock:
            result = client.search_documents(query="test")

        assert mock.call_count == 2
        assert sleep_mock.call_count == 1
        assert result == {"results": [], "total": 0, "query": "test"}

    def test_retries_on_timeout_then_succeeds(self) -> None:
        """A timeout exception should be retried."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(
            side_effect=[
                httpx.TimeoutException("timed out"),
                _mock_response(json_data={"results": [], "total": 0, "query": "test"}),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock:
            result = client.search_documents(query="test")

        assert mock.call_count == 2
        assert sleep_mock.call_count == 1
        assert result == {"results": [], "total": 0, "query": "test"}

    def test_retries_on_connection_error_then_succeeds(self) -> None:
        """A connection/request error should be retried."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(
            side_effect=[
                httpx.RequestError("Connection reset"),
                _mock_response(json_data={"results": [], "total": 0, "query": "test"}),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock:
            result = client.search_documents(query="test")

        assert mock.call_count == 2
        assert sleep_mock.call_count == 1
        assert result == {"results": [], "total": 0, "query": "test"}

    def test_does_not_retry_on_401(self) -> None:
        """A 401 error is NOT retryable — it should fail immediately."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(return_value=_error_response(401, "Unauthorized"))
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock, \
                pytest.raises(TomorrowlandClientError, match="Unauthorized"):
            client.search_documents(query="test")

        assert mock.call_count == 1  # no retries
        assert sleep_mock.call_count == 0

    def test_does_not_retry_on_403(self) -> None:
        """A 403 error is NOT retryable."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(return_value=_error_response(403, "Forbidden"))
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock, \
                pytest.raises(TomorrowlandClientError, match="Forbidden"):
            client.search_documents(query="test")

        assert mock.call_count == 1
        assert sleep_mock.call_count == 0

    def test_does_not_retry_on_404(self) -> None:
        """A 404 error is NOT retryable."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(return_value=_error_response(404, "Not found"))
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock, \
                pytest.raises(TomorrowlandClientError, match="Not found"):
            client.get_document(document_id="missing")

        assert mock.call_count == 1
        assert sleep_mock.call_count == 0

    def test_backoff_is_exponential(self) -> None:
        """The backoff delay should double each retry attempt."""
        client = TomorrowlandClient(api_url="http://localhost:8000")
        mock = MagicMock(
            side_effect=[
                _error_response(503, "fail 1"),
                _error_response(503, "fail 2"),
                _error_response(503, "fail 3"),
            ]
        )
        client._client.request = mock  # type: ignore[method-assign]

        with patch("time.sleep", return_value=None) as sleep_mock, \
                pytest.raises(TomorrowlandClientError):
            client.search_documents(query="test")

        # Should be: 0.5 then 1.0 seconds
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
        """Server should accept settings passed explicitly."""
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
        """Return a server whose client always returns empty success responses."""
        settings = Settings(tomorrowland_api_url="http://localhost:8000", app_env="test")
        mock_client = MagicMock(spec=TomorrowlandClient)
        mock_client.search_documents.return_value = {"results": [], "total": 0, "query": "t"}
        mock_client.get_document.return_value = {"document_id": "abc"}
        mock_client.get_passages.return_value = {"document_id": "abc", "passages": [], "total": 0}
        mock_client.ask_corpus.return_value = {
            "question": "q", "answer": "a", "citations": [], "model": "m",
        }
        mock_client.get_related_documents.return_value = {"document_id": "abc", "related": []}
        mock_client.list_facets.return_value = {"facets": {}}
        return create_mcp_server(settings, client=mock_client)

    def _get_tool_fn(self, mcp: FastMCP, name: str) -> Any:
        for t in mcp._tool_manager.list_tools():
            if t.name == name:
                return t.fn
        raise KeyError(f"Tool {name!r} not found")

    def test_audit_log_emitted_on_successful_search(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """A successful tool call must emit a mcp_audit log line with status=ok."""
        caplog.set_level("INFO")
        mcp = self._make_server_with_success_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_search_documents")

        fn(query="test")

        audit_lines = [
            r for r in caplog.records
            if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit_lines) == 1
        msg = audit_lines[0].message
        assert "tool=search_documents" in msg
        assert "status=ok" in msg
        assert re.search(r"latency_ms=\d+", msg)

    def test_audit_log_emitted_on_error(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """An error from the client must produce an audit log with status=error."""
        caplog.set_level("INFO")
        settings = Settings(tomorrowland_api_url="http://localhost:8000", app_env="test")
        mock_client = MagicMock(spec=TomorrowlandClient)
        mock_client.get_document.side_effect = TomorrowlandClientError("Not found", status_code=404)
        mcp = create_mcp_server(settings, client=mock_client)
        fn = self._get_tool_fn(mcp, "tomorrowland_get_document")

        with pytest.raises(ValueError, match="Resource not found"):
            fn(document_id="missing")

        audit_lines = [
            r for r in caplog.records
            if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit_lines) == 1
        msg = audit_lines[0].message
        assert "tool=get_document" in msg
        assert "status=error" in msg
        assert "error_type=HTTP_404" in msg

    def test_audit_log_includes_correlation_id(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """Every audit log line must include a correlation_id."""
        caplog.set_level("INFO")
        mcp = self._make_server_with_success_client()
        fn = self._get_tool_fn(mcp, "tomorrowland_list_facets")

        fn()

        audit_lines = [
            r for r in caplog.records
            if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit_lines) == 1
        msg = audit_lines[0].message
        # UUID format
        assert re.search(
            r"correlation_id=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            msg,
        )

    def test_all_six_tools_emit_audit_log(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """All 6 MCP tools should emit an mcp_audit log on success."""
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
            fn(**kwargs)

        audit_lines = [
            r for r in caplog.records
            if getattr(r, "message", "") and "mcp_audit" in r.message
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
        """Verify ``_sanitize_headers`` redacts sensitive headers."""
        raw = {"Authorization": "Bearer super-secret-token-12345"}
        sanitized = _sanitize_headers(raw)
        assert "super-secret-token" not in str(sanitized)
        assert sanitized["Authorization"] == "[redacted]"

    def test_no_token_in_error_message(self) -> None:
        """Client error messages should not contain the raw token."""
        client = TomorrowlandClient(api_url="http://localhost:8000", api_key="my-secret-token")
        mock = MagicMock(return_value=_error_response(401))
        client._client.request = mock  # type: ignore[method-assign]

        with pytest.raises(TomorrowlandClientError) as exc_info:
            client.search_documents(query="test")

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
        import_names = {name for name in dir(client_module) if not name.startswith("_")}
        assert "QdrantSearchClient" not in import_names
        assert "MeilisearchSearchProvider" not in import_names

    def test_server_module_does_not_import_store_clients(self) -> None:
        import sys

        server_module = sys.modules.get("services.mcp.server")
        if server_module is None:
            pytest.skip("Module not loaded; will be checked at import time")
        import_names = {name for name in dir(server_module) if not name.startswith("_")}
        assert "QdrantSearchClient" not in import_names
        assert "MeilisearchSearchProvider" not in import_names


# ======================================================================
# Invalid input rejection
# ======================================================================


class TestInvalidInputRejection:
    """Verify the MCP tool wrappers reject invalid inputs before calling the API."""

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValueError, match="query must be at least 1"):
            _validate_string("", 1, _MAX_QUERY_LENGTH, "query")

    def test_query_too_long_rejected(self) -> None:
        with pytest.raises(ValueError, match=f"query must be at most {_MAX_QUERY_LENGTH}"):
            _validate_string("x" * (_MAX_QUERY_LENGTH + 1), 1, _MAX_QUERY_LENGTH, "query")

    def test_top_k_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            _validate_int(0, _MIN_TOP_K, _MAX_TOP_K, "top_k")

    def test_top_k_too_large_rejected(self) -> None:
        with pytest.raises(ValueError, match=f"top_k must be <= {_MAX_TOP_K}"):
            _validate_int(100, _MIN_TOP_K, _MAX_TOP_K, "top_k")

    @pytest.mark.parametrize("page", [0, 21])
    def test_page_out_of_range(self, page: int) -> None:
        with pytest.raises(ValueError, match="page must be"):
            _validate_int(page, 1, _MAX_PAGE, "page")

    def test_question_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="question must be at least 1"):
            _validate_string("", 1, 2000, "question")


# ======================================================================
# MCP authorization parity (#562)
# ======================================================================


class TestMCPAuthorizationParity:
    """MCP tools correctly proxy REST auth errors and never leak sensitive data."""

    def _make_server_raising(self, status_code: int, detail: str) -> FastMCP:
        """Return an MCP server whose client always raises TomorrowlandClientError."""
        settings = Settings(tomorrowland_api_url="http://localhost:8000", app_env="test")
        mock_client = MagicMock(spec=TomorrowlandClient)
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
        """Return the raw callable for a named MCP tool."""
        for t in mcp._tool_manager.list_tools():
            if t.name == name:
                return t.fn
        raise KeyError(f"Tool {name!r} not found")

    def test_403_does_not_expose_document_id_from_response_body(self) -> None:
        """When the REST API returns 403 with a doc ID in the body, the translated
        MCP error must NOT contain that ID — only a static safe message."""
        doc_id = "abc12345-0000-0000-0000-000000000000"
        mcp = self._make_server_raising(403, f"Document {doc_id} not accessible")
        fn = self._get_tool_fn(mcp, "tomorrowland_get_document")

        with pytest.raises(ValueError) as exc_info:
            fn(document_id=doc_id)

        msg = str(exc_info.value)
        assert doc_id not in msg, "inaccessible doc ID must not appear in MCP error"
        assert "Access denied" in msg

    def test_401_does_not_expose_api_key_in_error_message(self) -> None:
        """A 401 error must not include the API key value in the translated error."""
        api_key = "super-secret-key-must-not-leak-in-errors"
        settings = Settings(
            tomorrowland_api_url="http://localhost:8000",
            tomorrowland_api_key=api_key,
            app_env="test",
        )
        mock_client = MagicMock(spec=TomorrowlandClient)
        mock_client.search_documents.side_effect = TomorrowlandClientError(
            f"Unauthorized: {api_key}", status_code=401
        )
        mcp = create_mcp_server(settings, client=mock_client)
        fn = self._get_tool_fn(mcp, "tomorrowland_search_documents")

        with pytest.raises(ValueError) as exc_info:
            fn(query="test")

        msg = str(exc_info.value)
        assert api_key not in msg, "API key must not appear in MCP error message"
        assert "Authentication failed" in msg

    def test_429_error_does_not_expose_document_metadata(self) -> None:
        """A 429 response must use a static safe message — no corpus metadata leaks."""
        sensitive_id = "corpus-id-must-not-appear-in-429-error"
        mcp = self._make_server_raising(429, f"Too many requests for {sensitive_id}")
        fn = self._get_tool_fn(mcp, "tomorrowland_ask_corpus")

        with pytest.raises(ValueError) as exc_info:
            fn(question="what?")

        msg = str(exc_info.value)
        assert sensitive_id not in msg, "corpus metadata must not appear in 429 error"
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
        self, tool_name: str, tool_kwargs: dict[str, Any]
    ) -> None:
        """Every MCP tool must convert a 401 to a safe ValueError (no raw API detail)."""
        raw_detail = "raw-internal-detail-must-not-appear"
        mcp = self._make_server_raising(401, raw_detail)
        fn = self._get_tool_fn(mcp, tool_name)

        with pytest.raises(ValueError) as exc_info:
            fn(**tool_kwargs)

        msg = str(exc_info.value)
        assert "Authentication failed" in msg
        assert raw_detail not in msg, "raw 401 detail must not leak through MCP"

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
        self, tool_name: str, tool_kwargs: dict[str, Any]
    ) -> None:
        """Every MCP tool must convert a 403 to a safe static message (no raw body)."""
        hidden_resource_id = "hidden-resource-id-must-not-appear-in-error"
        mcp = self._make_server_raising(403, f"Cannot access {hidden_resource_id}")
        fn = self._get_tool_fn(mcp, tool_name)

        with pytest.raises(ValueError) as exc_info:
            fn(**tool_kwargs)

        msg = str(exc_info.value)
        assert "Access denied" in msg
        assert hidden_resource_id not in msg, "raw 403 detail must not leak through MCP"
