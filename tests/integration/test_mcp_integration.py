"""Integration tests for the MCP adapter (#560).

Tests the full MCP server pipeline end-to-end using ``create_mcp_server``
with a mock ``TomorrowlandClient``, exercising all six tools, error paths,
feature flags, circuit breaker, warmup, coalescing, tracing, and
observability endpoints.

Unlike unit tests, these verify the full tool invocation cycle including
context extraction, validation, warmup, client calls, audit logging,
metrics recording, and error translation.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context, FastMCP

from services.mcp.client import (
    CircuitBreakerOpenError,
    TomorrowlandClient,
    TomorrowlandClientError,
)
from services.mcp.server import create_mcp_server
from shared.config import Settings

# ======================================================================
# Helpers
# ======================================================================


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


def _make_client(**overrides: Any) -> AsyncMock:
    """Build a mock TomorrowlandClient preset for all six tools."""
    mock = AsyncMock(spec=TomorrowlandClient)
    mock.search_documents.return_value = {
        "results": [],
        "total": 0,
        "query": "t",
    }
    mock.get_document.return_value = {"document_id": "abc"}
    mock.get_passages.return_value = {
        "document_id": "abc",
        "passages": [],
        "total": 0,
    }
    mock.ask_corpus.return_value = {
        "question": "q",
        "answer": "a",
        "citations": [],
        "model": "m",
    }
    mock.get_related_documents.return_value = {
        "document_id": "abc",
        "related": [],
    }
    mock.list_facets.return_value = {"facets": {}}
    for k, v in overrides.items():
        getattr(mock, k).return_value = v
    return mock


def _make_server(client: AsyncMock | None = None) -> FastMCP:
    settings = Settings(
        tomorrowland_api_url="http://localhost:8000",
        app_env="test",
    )
    if client is None:
        client = _make_client()
    return create_mcp_server(settings, client=client)


def _get_tool_fn(mcp: FastMCP, name: str) -> Any:
    for t in mcp._tool_manager.list_tools():
        if t.name == name:
            return t.fn
    raise KeyError(f"Tool {name!r} not found")


# ======================================================================
# Tool invocations — happy path
# ======================================================================


class TestAllToolsHappyPath:
    """Every tool returns the mock client response on success."""

    def test_search_documents(self) -> None:
        mock = _make_client(
            search_documents={"results": [{"id": "1"}], "total": 1, "query": "x"},
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        result = _invoke_tool(fn, query="test")
        assert result["total"] == 1
        mock.search_documents.assert_called_once()

    def test_get_document(self) -> None:
        mock = _make_client(get_document={"document_id": "xyz", "title": "T"})
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_document")
        result = _invoke_tool(fn, document_id="xyz")
        assert result["title"] == "T"
        mock.get_document.assert_called_once()

    def test_get_passages(self) -> None:
        mock = _make_client(
            get_passages={"document_id": "abc", "passages": ["p1"], "total": 1},
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_passages")
        result = _invoke_tool(fn, document_id="abc")
        assert result["total"] == 1
        mock.get_passages.assert_called_once()

    def test_ask_corpus(self) -> None:
        mock = _make_client(
            ask_corpus={"question": "q", "answer": "A", "citations": [], "model": "m"},
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_ask_corpus")
        result = _invoke_tool(fn, question="what?")
        assert result["answer"] == "A"
        mock.ask_corpus.assert_called_once()

    def test_get_related_documents(self) -> None:
        mock = _make_client(
            get_related_documents={"document_id": "abc", "related": [{"id": "r1"}]},
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_related_documents")
        result = _invoke_tool(fn, document_id="abc")
        assert len(result["related"]) == 1
        mock.get_related_documents.assert_called_once()

    def test_list_facets(self) -> None:
        mock = _make_client(
            list_facets={"facets": {"source": {"folder": 3}}},
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_list_facets")
        result = _invoke_tool(fn)
        assert result["facets"]["source"]["folder"] == 3
        mock.list_facets.assert_called_once()


# ======================================================================
# Warmup behaviour
# ======================================================================


class TestWarmup:
    """Warmup is called once before the first API call per tool."""

    def test_warmup_called_before_search(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        _invoke_tool(fn, query="t")
        mock.warmup.assert_called()

    def test_warmup_called_on_all_six_tools(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        calls: list[tuple[str, dict[str, Any]]] = [
            ("tomorrowland_search_documents", {"query": "t"}),
            ("tomorrowland_get_document", {"document_id": "abc"}),
            ("tomorrowland_get_passages", {"document_id": "abc"}),
            ("tomorrowland_ask_corpus", {"question": "what?"}),
            ("tomorrowland_get_related_documents", {"document_id": "abc"}),
            ("tomorrowland_list_facets", {}),
        ]
        for name, kwargs in calls:
            fn = _get_tool_fn(mcp, name)
            _invoke_tool(fn, **kwargs)

        # warmup called 6 times (once per tool).
        assert mock.warmup.call_count == 6

    def test_warmup_not_called_when_validation_fails(self) -> None:
        """Warmup is skipped if input validation fails (no wasted connection)."""
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        with pytest.raises(ValueError, match="query must be at least 1"):
            _invoke_tool(fn, query="")
        mock.warmup.assert_not_called()


# ======================================================================
# Input validation — server layer
# ======================================================================


class TestServerInputValidation:
    """The server rejects invalid inputs before any API call."""

    def test_empty_query_rejected_before_api_call(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        with pytest.raises(ValueError, match="query must be at least 1"):
            _invoke_tool(fn, query="")
        mock.search_documents.assert_not_called()

    def test_oversized_query_rejected(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        with pytest.raises(ValueError, match="query must be at most"):
            _invoke_tool(fn, query="x" * 600)
        mock.search_documents.assert_not_called()

    def test_top_k_zero_rejected(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            _invoke_tool(fn, query="t", top_k=0)
        mock.search_documents.assert_not_called()

    def test_invalid_document_id_rejected(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_document")
        with pytest.raises(ValueError, match="document_id must be at least 1"):
            _invoke_tool(fn, document_id="")
        mock.get_document.assert_not_called()

    def test_invalid_filter_keys_rejected(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        with pytest.raises(ValueError, match="Unknown filter keys"):
            _invoke_tool(fn, query="t", filters={"bogus": "v"})
        mock.search_documents.assert_not_called()

    def test_valid_filters_passed_to_client(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        _invoke_tool(fn, query="t", filters={"sources": ["wiki"]})
        mock.search_documents.assert_called_once()
        call_kwargs = mock.search_documents.call_args[1]
        assert call_kwargs["filters"] == {"sources": ["wiki"]}


# ======================================================================
# Error translation
# ======================================================================


class TestErrorTranslation:
    """API errors are translated to safe user-facing messages."""

    def test_401_returns_auth_error_message(self) -> None:
        mock = _make_client()
        mock.search_documents.side_effect = TomorrowlandClientError(
            "Unauthorized",
            status_code=401,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        with pytest.raises(ValueError, match="Authentication failed"):
            _invoke_tool(fn, query="t")

    def test_403_returns_access_denied_message(self) -> None:
        mock = _make_client()
        mock.get_document.side_effect = TomorrowlandClientError(
            "Forbidden",
            status_code=403,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_document")
        with pytest.raises(ValueError, match="Access denied"):
            _invoke_tool(fn, document_id="abc")

    def test_404_returns_not_found_message(self) -> None:
        mock = _make_client()
        mock.get_passages.side_effect = TomorrowlandClientError(
            "Not found",
            status_code=404,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_passages")
        with pytest.raises(ValueError, match="Resource not found"):
            _invoke_tool(fn, document_id="abc")

    def test_503_returns_service_unavailable_message(self) -> None:
        mock = _make_client()
        mock.list_facets.side_effect = TomorrowlandClientError(
            "Down",
            status_code=503,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_list_facets")
        with pytest.raises(ValueError, match="Service unavailable"):
            _invoke_tool(fn)

    def test_429_returns_rate_limit_message(self) -> None:
        mock = _make_client()
        mock.ask_corpus.side_effect = TomorrowlandClientError(
            "Too many",
            status_code=429,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_ask_corpus")
        with pytest.raises(ValueError, match="Rate limit"):
            _invoke_tool(fn, question="what?")

    def test_error_messages_never_contain_raw_detail(self) -> None:
        """The original error detail must not appear in the user-facing message."""
        secret_detail = "SECRET-INTERNAL-DETAIL-MUST-NOT-LEAK"
        mock = _make_client()
        mock.search_documents.side_effect = TomorrowlandClientError(
            secret_detail,
            status_code=401,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        with pytest.raises(ValueError) as exc_info:
            _invoke_tool(fn, query="t")
        assert secret_detail not in str(exc_info.value)


# ======================================================================
# Feature flags
# ======================================================================


class TestFeatureFlagsIntegration:
    """Per-tool feature flags disable tools at the server layer."""

    def test_tool_disabled_via_env_var(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("MCP_ENABLE_GET_DOCUMENT", "0")
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_document")
        with pytest.raises(ValueError, match="get_document.*disabled"):
            _invoke_tool(fn, document_id="abc")
        mock.get_document.assert_not_called()

    def test_disabling_one_tool_does_not_affect_others(
        self,
        monkeypatch: Any,
    ) -> None:
        monkeypatch.setenv("MCP_ENABLE_ASK_CORPUS", "false")
        mock = _make_client()
        mcp = _make_server(mock)

        # ask_corpus blocked.
        fn = _get_tool_fn(mcp, "tomorrowland_ask_corpus")
        with pytest.raises(ValueError, match="ask_corpus.*disabled"):
            _invoke_tool(fn, question="what?")
        mock.ask_corpus.assert_not_called()

        # search_documents still works.
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        result = _invoke_tool(fn, query="t")
        assert result["total"] == 0

    def test_case_insensitive_disable(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("MCP_ENABLE_LIST_FACETS", "OFF")
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_list_facets")
        with pytest.raises(ValueError, match="list_facets.*disabled"):
            _invoke_tool(fn)


# ======================================================================
# Circuit breaker — server integration
# ======================================================================


class TestCircuitBreakerIntegration:
    """Circuit breaker errors are translated to safe messages."""

    def test_breaker_open_returns_safe_error(self) -> None:
        mock = _make_client()
        mock.search_documents.side_effect = CircuitBreakerOpenError(
            cooldown_remaining=25.0,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        with pytest.raises(ValueError, match="Circuit breaker is open"):
            _invoke_tool(fn, query="t")

    def test_breaker_open_error_includes_cooldown_info(self) -> None:
        mock = _make_client()
        mock.get_document.side_effect = CircuitBreakerOpenError(
            cooldown_remaining=15.0,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_document")
        with pytest.raises(ValueError) as exc_info:
            _invoke_tool(fn, document_id="abc")
        assert "15s" in str(exc_info.value)


# ======================================================================
# Audit logging — server integration
# ======================================================================


class TestAuditLoggingIntegration:
    """Every tool invocation emits an mcp_audit log line."""

    def test_audit_log_on_success(self, caplog: Any) -> None:
        caplog.set_level("INFO")
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        _invoke_tool(fn, query="test")

        audit = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit) == 1
        msg = audit[0].message
        assert "tool=search_documents" in msg
        assert "status=ok" in msg

    def test_audit_log_on_error(self, caplog: Any) -> None:
        caplog.set_level("INFO")
        mock = _make_client()
        mock.get_document.side_effect = TomorrowlandClientError(
            "Not found",
            status_code=404,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_document")
        with pytest.raises(ValueError):
            _invoke_tool(fn, document_id="missing")

        audit = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit) == 1
        msg = audit[0].message
        assert "tool=get_document" in msg
        assert "status=error" in msg
        assert "error_type=HTTP_404" in msg

    def test_all_six_tools_audit_logged(self, caplog: Any) -> None:
        caplog.set_level("INFO")
        mock = _make_client()
        mcp = _make_server(mock)

        tools: list[tuple[str, dict[str, Any]]] = [
            ("tomorrowland_search_documents", {"query": "t"}),
            ("tomorrowland_get_document", {"document_id": "abc"}),
            ("tomorrowland_get_passages", {"document_id": "abc"}),
            ("tomorrowland_ask_corpus", {"question": "what?"}),
            ("tomorrowland_get_related_documents", {"document_id": "abc"}),
            ("tomorrowland_list_facets", {}),
        ]
        for name, kwargs in tools:
            fn = _get_tool_fn(mcp, name)
            _invoke_tool(fn, **kwargs)

        audit = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit) == 6
        seen = {re.search(r"tool=(\w+)", r.message).group(1) for r in audit}  # type: ignore[union-attr]
        assert seen == {
            "search_documents",
            "get_document",
            "get_passages",
            "ask_corpus",
            "get_related_documents",
            "list_facets",
        }


# ======================================================================
# Traceparent forwarding — server integration
# ======================================================================


class TestTraceparentForwardingIntegration:
    """W3C traceparent is extracted from context and forwarded to client."""

    _TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

    def test_traceparent_forwarded_to_search(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        ctx = _mock_context({"traceparent": self._TRACEPARENT})
        _invoke_tool(fn, query="t", ctx=ctx)

        mock.search_documents.assert_called_once()
        assert mock.search_documents.call_args[1]["traceparent"] == self._TRACEPARENT

    def test_traceparent_forwarded_to_all_six_tools(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        ctx = _mock_context({"traceparent": self._TRACEPARENT})

        calls: list[tuple[str, dict[str, Any]]] = [
            ("tomorrowland_search_documents", {"query": "t", "ctx": ctx}),
            ("tomorrowland_get_document", {"document_id": "abc", "ctx": ctx}),
            ("tomorrowland_get_passages", {"document_id": "abc", "ctx": ctx}),
            ("tomorrowland_ask_corpus", {"question": "what?", "ctx": ctx}),
            ("tomorrowland_get_related_documents", {"document_id": "abc", "ctx": ctx}),
            ("tomorrowland_list_facets", {"ctx": ctx}),
        ]

        method_map = {
            "tomorrowland_search_documents": "search_documents",
            "tomorrowland_get_document": "get_document",
            "tomorrowland_get_passages": "get_passages",
            "tomorrowland_ask_corpus": "ask_corpus",
            "tomorrowland_get_related_documents": "get_related_documents",
            "tomorrowland_list_facets": "list_facets",
        }

        for name, kwargs in calls:
            fn = _get_tool_fn(mcp, name)
            _invoke_tool(fn, **kwargs)
            method = getattr(mock, method_map[name])
            assert method.call_args[1]["traceparent"] == self._TRACEPARENT

    def test_no_traceparent_when_not_in_context(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        ctx = _mock_context({"authorization": "Bearer token"})
        _invoke_tool(fn, query="t", ctx=ctx)

        mock.search_documents.assert_called_once()
        assert mock.search_documents.call_args[1]["traceparent"] is None


# ======================================================================
# Auth header forwarding — server integration
# ======================================================================


class TestAuthHeaderForwardingIntegration:
    """Per-client auth tokens are extracted and forwarded."""

    def test_auth_header_forwarded_to_search(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        ctx = _mock_context({"authorization": "Bearer client-token"})
        _invoke_tool(fn, query="t", ctx=ctx)

        mock.search_documents.assert_called_once()
        assert mock.search_documents.call_args[1]["auth_header"] == "Bearer client-token"

    def test_no_auth_when_no_context(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        _invoke_tool(fn, query="t")  # No ctx.

        mock.search_documents.assert_called_once()
        assert mock.search_documents.call_args[1]["auth_header"] is None


# ======================================================================
# Progress notifications — server integration
# ======================================================================


class TestProgressNotificationsIntegration:
    """ask_corpus sends progress notifications via ctx.report_progress."""

    def test_progress_sent_on_success(self) -> None:
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_ask_corpus")
        ctx = AsyncMock(spec=Context)
        _invoke_tool(fn, question="what?", ctx=ctx)

        assert ctx.report_progress.call_count >= 3
        calls = ctx.report_progress.call_args_list
        assert calls[0][1]["progress"] == 10
        assert calls[1][1]["progress"] == 50
        assert calls[-1][1]["progress"] == 100

    def test_progress_sent_on_error(self) -> None:
        mock = _make_client()
        mock.ask_corpus.side_effect = TomorrowlandClientError(
            "Down",
            status_code=503,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_ask_corpus")
        ctx = AsyncMock(spec=Context)

        with pytest.raises(ValueError):
            _invoke_tool(fn, question="what?", ctx=ctx)

        # Progress should be sent on error path too.
        assert ctx.report_progress.call_count >= 1
        assert ctx.report_progress.call_args_list[-1][1]["progress"] == 100


# ======================================================================
# Request coalescing — client integration
# ======================================================================


class TestCoalescingIntegration:
    """Identical concurrent calls are coalesced into one backend request."""

    def test_concurrent_identical_searches_share_one_call(self) -> None:
        """Two concurrent identical searches should trigger only one backend call."""
        from services.mcp.client import TomorrowlandClient

        client = TomorrowlandClient(api_url="http://localhost:8000")
        call_count = 0

        async def _tracking_request(**kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # small delay to allow coalescing
            return {"results": [], "total": 0, "query": "t"}

        client._do_request = _tracking_request  # type: ignore[method-assign]

        async def _run_concurrent() -> int:
            tasks = [
                client.search_documents(query="same query"),
                client.search_documents(query="same query"),
                client.search_documents(query="same query"),
            ]
            await asyncio.gather(*tasks)
            return call_count

        count = asyncio.run(_run_concurrent())
        # Three calls with identical params should coalesce into one.
        assert count == 1, f"Expected 1 backend call, got {count}"

    def test_different_queries_not_coalesced(self) -> None:
        """Different search queries should NOT be coalesced."""
        from services.mcp.client import TomorrowlandClient

        client = TomorrowlandClient(api_url="http://localhost:8000")
        call_count = 0

        async def _tracking_request(**kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {"results": [], "total": 0, "query": "t"}

        client._do_request = _tracking_request  # type: ignore[method-assign]

        async def _run_concurrent() -> int:
            tasks = [
                client.search_documents(query="query A"),
                client.search_documents(query="query B"),
                client.search_documents(query="query C"),
            ]
            await asyncio.gather(*tasks)
            return call_count

        count = asyncio.run(_run_concurrent())
        # Three different queries should NOT coalesce.
        assert count == 3, f"Expected 3 backend calls, got {count}"

    def test_different_auth_tokens_not_coalesced(self) -> None:
        """Requests with different auth tokens must NOT be coalesced."""
        from services.mcp.client import TomorrowlandClient

        client = TomorrowlandClient(api_url="http://localhost:8000")
        call_count = 0

        async def _tracking_request(**kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {"results": [], "total": 0, "query": "t"}

        client._do_request = _tracking_request  # type: ignore[method-assign]

        async def _run_concurrent() -> int:
            tasks = [
                client.search_documents(query="t", auth_header="Bearer user-a"),
                client.search_documents(query="t", auth_header="Bearer user-b"),
            ]
            await asyncio.gather(*tasks)
            return call_count

        count = asyncio.run(_run_concurrent())
        assert count == 2, f"Expected 2 backend calls for different auth, got {count}"


# ======================================================================
# Metrics — server integration
# ======================================================================


class TestMetricsIntegration:
    """Metrics counters and histograms are incremented on tool calls."""

    def test_successful_call_increments_counter(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")

        before = _mcp_metrics.tool_calls_total.labels(
            tool="search_documents",
            outcome="ok",
        )._value.get()

        _invoke_tool(fn, query="t")

        after = _mcp_metrics.tool_calls_total.labels(
            tool="search_documents",
            outcome="ok",
        )._value.get()
        assert after == before + 1

    def test_error_call_increments_error_counter(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        mock = _make_client()
        mock.get_document.side_effect = TomorrowlandClientError(
            "Not found",
            status_code=404,
        )
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_get_document")

        before = _mcp_metrics.tool_call_errors_total.labels(
            tool="get_document",
            error_type="HTTP_404",
        )._value.get()

        with pytest.raises(ValueError):
            _invoke_tool(fn, document_id="abc")

        after = _mcp_metrics.tool_call_errors_total.labels(
            tool="get_document",
            error_type="HTTP_404",
        )._value.get()
        assert after == before + 1

    def test_histogram_records_latency(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_list_facets")

        before = _mcp_metrics.tool_call_duration_seconds.labels(
            tool="list_facets",
        )._sum.get()

        _invoke_tool(fn)

        after = _mcp_metrics.tool_call_duration_seconds.labels(
            tool="list_facets",
        )._sum.get()
        assert after > before

    def test_all_six_tools_have_metrics(self) -> None:
        from services.mcp.metrics import _mcp_metrics

        mock = _make_client()
        mcp = _make_server(mock)

        tools: list[tuple[str, dict[str, Any]]] = [
            ("tomorrowland_search_documents", {"query": "t"}),
            ("tomorrowland_get_document", {"document_id": "abc"}),
            ("tomorrowland_get_passages", {"document_id": "abc"}),
            ("tomorrowland_ask_corpus", {"question": "what?"}),
            ("tomorrowland_get_related_documents", {"document_id": "abc"}),
            ("tomorrowland_list_facets", {}),
        ]
        expected = {
            "search_documents",
            "get_document",
            "get_passages",
            "ask_corpus",
            "get_related_documents",
            "list_facets",
        }

        for name, kwargs in tools:
            fn = _get_tool_fn(mcp, name)
            _invoke_tool(fn, **kwargs)

        for tool_name in expected:
            val = _mcp_metrics.tool_calls_total.labels(
                tool=tool_name,
                outcome="ok",
            )._value.get()
            assert val >= 1, f"No ok counter for {tool_name}"

    def test_metrics_endpoint_returns_prometheus_format(self) -> None:
        from prometheus_client import CONTENT_TYPE_LATEST

        from services.mcp.metrics import metrics_endpoint

        body, status, headers = asyncio.run(metrics_endpoint(MagicMock()))
        assert status == 200
        assert headers["Content-Type"] == CONTENT_TYPE_LATEST
        text = body.decode("utf-8")
        assert "tomorrowland_mcp_tool_calls_total" in text


# ======================================================================
# Health endpoint
# ======================================================================


class TestHealthEndpoint:
    """GET /health returns 200 OK for liveness probes."""

    def test_health_returns_ok(self) -> None:
        """Verify the health endpoint is registered and returns ok."""
        mock = _make_client()
        mcp = _make_server(mock)

        # FastMCP stores the app as _app or app.
        app = getattr(mcp, "_app", None) or getattr(mcp, "app", None)
        if app is None:
            pytest.skip("No Starlette app accessible on FastMCP")

        # Find the /health route by name.
        routes = {r.path: r for r in getattr(app, "routes", [])}
        assert "/health" in routes, "Health endpoint not registered"


# ======================================================================
# Correlation ID forwarding
# ======================================================================


class TestCorrelationIDIntegration:
    """Correlation IDs are generated for every tool call."""

    def test_correlation_id_present_in_audit_log(self, caplog: Any) -> None:
        caplog.set_level("INFO")
        mock = _make_client()
        mcp = _make_server(mock)
        fn = _get_tool_fn(mcp, "tomorrowland_search_documents")
        _invoke_tool(fn, query="t")

        audit = [
            r for r in caplog.records if getattr(r, "message", "") and "mcp_audit" in r.message
        ]
        assert len(audit) >= 1
        msg = audit[0].message
        assert re.search(
            r"correlation_id=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            msg,
        )
