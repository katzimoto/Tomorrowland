"""HTTP client for the Tomorrowland researcher API (#558).

Wraps the ``/api/agent/v1/*`` endpoints so the MCP server never touches
the database, Qdrant, or Meilisearch directly.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

_LOG_SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "x-api-key"})

# Retry configuration for transient backend failures.
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5  # seconds; doubles each attempt
_RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})

# Per-operation HTTP timeouts (seconds).  ask_corpus may take 30+ seconds
# for RAG over a large corpus; search should fail fast.
_OP_TIMEOUTS: dict[str, float] = {
    "/api/agent/v1/ask_corpus": 60.0,
    "/api/agent/v1/search_documents": 10.0,
}
_DEFAULT_OP_TIMEOUT: float = 15.0

# httpx connection pool limits — prevents exhaustion under concurrent
# MCP clients.
_CONNECTION_LIMITS = httpx.Limits(
    max_keepalive_connections=10,
    max_connections=20,
    keepalive_expiry=30.0,
)


class TomorrowlandClientError(Exception):
    """Error raised when the Tomorrowland API returns a non-2xx status."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.status_code = status_code
        super().__init__(message)


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of *headers* with sensitive values redacted."""
    return {
        k: "[redacted]" if k.lower() in _LOG_SENSITIVE_HEADERS else v for k, v in headers.items()
    }


def _extract_error_detail(response: httpx.Response) -> str | None:
    """Try to extract a ``detail`` field from a JSON error response."""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail")
            if detail is not None and isinstance(detail, str):
                return detail
            if isinstance(detail, list):
                parts = [str(d) for d in detail if isinstance(d, dict)]
                if parts:
                    return "; ".join(parts)
        return None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


class TomorrowlandClient:
    """Thin HTTP client wrapping ``/api/agent/v1`` researcher endpoints.

    Every method maps to exactly one endpoint and preserves the request /
    response schema established by #558.  Authentication is forwarded as a
    Bearer token — the adapter never inspects or interprets the token.

    Connection pooling is tuned for concurrent MCP client workloads.
    Transient failures (5xx, 429, timeouts) are retried with exponential
    backoff up to 3 attempts.

    Per-operation timeouts are applied per endpoint:
    ``ask_corpus`` = 60 s, ``search_documents`` = 10 s, others = 15 s.

    Per-client token forwarding is supported via the *auth_header* parameter
    on every tool method.  When an MCP client sends its own Bearer token,
    the adapter forwards it verbatim.  Falls back to the static
    ``TOMORROWLAND_API_KEY`` environment variable when no per-request header
    is present.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = api_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        # The global timeout on the pool is a safety ceiling; per-operation
        # timeouts are applied via the *timeout_override* path below.
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            limits=_CONNECTION_LIMITS,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(
        self,
        correlation_id: str | None = None,
        auth_header: str | None = None,
    ) -> dict[str, str]:
        """Build request headers.

        *auth_header*, when provided, is forwarded verbatim as the
        ``Authorization`` header (per-client token forwarding).  Falls back
        to the static ``self._api_key`` when no per-request header is
        present.
        """
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        elif self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        return headers

    def _timeout_for_path(self, path: str) -> httpx.Timeout:
        """Return the per-operation timeout for *path*."""
        seconds = _OP_TIMEOUTS.get(path, _DEFAULT_OP_TIMEOUT)
        return httpx.Timeout(seconds)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request and return the parsed JSON response.

        Retries on transient failures (5xx, 429, timeouts) with exponential
        backoff up to ``_MAX_RETRIES`` attempts.  Uses per-operation timeout.
        """
        url = f"{self._base_url}{path}"
        req_headers = self._headers(
            correlation_id=correlation_id,
            auth_header=auth_header,
        )

        logger.debug(
            "MCP → %s %s headers=%s",
            method,
            url,
            _sanitize_headers(req_headers),
        )

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    headers=req_headers,
                    json=json_body,
                    params=params,
                    timeout=self._timeout_for_path(path),
                )
            except httpx.TimeoutException:
                logger.warning(
                    "MCP request timed out method=%s path=%s attempt=%d/%d",
                    method,
                    path,
                    attempt,
                    _MAX_RETRIES,
                )
                last_exc = TomorrowlandClientError(
                    "Request to Tomorrowland API timed out", status_code=504
                )
                if attempt < _MAX_RETRIES:
                    backoff = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)
                    continue
                raise last_exc from None
            except httpx.RequestError as exc:
                logger.warning(
                    "MCP connection error method=%s path=%s attempt=%d/%d error=%s",
                    method,
                    path,
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                last_exc = TomorrowlandClientError(
                    f"Cannot reach Tomorrowland API: {exc}", status_code=503
                )
                if attempt < _MAX_RETRIES:
                    backoff = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)
                    continue
                raise last_exc from exc

            if response.status_code >= 400:
                detail = _extract_error_detail(response)
                log_level = logger.warning if response.status_code < 500 else logger.error
                log_level(
                    "MCP API error method=%s path=%s status=%s detail=%s attempt=%d/%d",
                    method,
                    path,
                    response.status_code,
                    detail or "(no detail)",
                    attempt,
                    _MAX_RETRIES,
                )
                last_exc = TomorrowlandClientError(
                    detail or f"API returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )
                if response.status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                    backoff = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)
                    continue
                raise last_exc from None

            return cast("dict[str, Any]", response.json())

        # Should be unreachable — all paths either return or raise above.
        assert last_exc is not None
        raise last_exc  # pragma: no cover

    # ------------------------------------------------------------------
    # Tool methods (each matches one /api/agent/v1 endpoint)
    # ------------------------------------------------------------------

    def search_documents(
        self,
        query: str,
        top_k: int = 20,
        page: int = 1,
        filters: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/agent/v1/search_documents"""
        body: dict[str, Any] = {"query": query, "top_k": top_k, "page": page}
        if filters:
            body["filters"] = filters
        return self._request(
            "POST",
            "/api/agent/v1/search_documents",
            json_body=body,
            correlation_id=correlation_id,
            auth_header=auth_header,
        )

    def get_document(
        self,
        document_id: str,
        correlation_id: str | None = None,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/agent/v1/get_document"""
        return self._request(
            "GET",
            "/api/agent/v1/get_document",
            params={"document_id": document_id},
            correlation_id=correlation_id,
            auth_header=auth_header,
        )

    def get_passages(
        self,
        document_id: str,
        limit: int = 50,
        offset: int = 0,
        correlation_id: str | None = None,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/agent/v1/get_passages"""
        return self._request(
            "GET",
            "/api/agent/v1/get_passages",
            params={"document_id": document_id, "limit": limit, "offset": offset},
            correlation_id=correlation_id,
            auth_header=auth_header,
        )

    def ask_corpus(
        self,
        question: str,
        top_k: int | None = None,
        document_id: str | None = None,
        correlation_id: str | None = None,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/agent/v1/ask_corpus"""
        body: dict[str, Any] = {"question": question}
        if top_k is not None:
            body["top_k"] = top_k
        if document_id is not None:
            body["document_id"] = document_id
        return self._request(
            "POST",
            "/api/agent/v1/ask_corpus",
            json_body=body,
            correlation_id=correlation_id,
            auth_header=auth_header,
        )

    def get_related_documents(
        self,
        document_id: str,
        correlation_id: str | None = None,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/agent/v1/get_related_documents"""
        return self._request(
            "GET",
            "/api/agent/v1/get_related_documents",
            params={"document_id": document_id},
            correlation_id=correlation_id,
            auth_header=auth_header,
        )

    def list_facets(
        self,
        query: str = "",
        correlation_id: str | None = None,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/agent/v1/list_facets"""
        return self._request(
            "GET",
            "/api/agent/v1/list_facets",
            params={"query": query},
            correlation_id=correlation_id,
            auth_header=auth_header,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
