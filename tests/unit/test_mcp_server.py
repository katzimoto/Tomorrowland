"""Unit tests for the MCP adapter (#560).

Tests cover:
- ``TomorrowlandClient`` — each tool method calls the correct HTTP method/path,
  forwards auth headers, handles errors and timeouts.
- ``create_mcp_server`` — tool list, input validation, error translation.
- Log sanitisation: no Authorization header leakage.
- No direct store clients imported.
"""

from __future__ import annotations

from unittest.mock import ANY, MagicMock

import httpx
import pytest

from services.mcp.client import (
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
        # Should not raise
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
        client = TomorrowlandClient(api_url="http://nonexistent:8000")
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
        # FastMCP stores tools internally; we can inspect the tool names
        # through the _tool_manager attribute.
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
        # Verify settings are used by checking the client inside the tools
        # We can't easily inspect the closure, but we can verify no error occurs
        tool_names = {t.name for t in mcp._tool_manager.list_tools()}
        assert "tomorrowland_search_documents" in tool_names


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
        # Simulate a 401 error
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

    # These imports should fail if the adapter accidentally pulls in store
    # clients through transitive imports. We check the module's direct
    # imports rather than trying to run a full import chain.

    def test_client_module_does_not_import_store_clients(self) -> None:
        import sys

        # The client module should only import httpx, logging, json, typing
        client_module = sys.modules.get("services.mcp.client")
        if client_module is None:
            pytest.skip("Module not loaded; will be checked at import time")
        import_names = {name for name in dir(client_module) if not name.startswith("_")}
        # Check that store-related names aren't exposed
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
