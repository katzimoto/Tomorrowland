"""HTTP client for the Tomorrowland researcher API (#558).

Wraps the ``/api/agent/v1/*`` endpoints so the MCP server never touches
the database, Qdrant, or Meilisearch directly.
"""

from __future__ import annotations

import json
import logging
import weakref
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

_LOG_SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "x-api-key"})


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
        self._client = httpx.Client(timeout=timeout)
        weakref.finalize(self, self._client.close)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request and return the parsed JSON response."""
        url = f"{self._base_url}{path}"
        req_headers = self._headers()

        logger.debug(
            "MCP → %s %s headers=%s",
            method,
            url,
            _sanitize_headers(req_headers),
        )

        try:
            response = self._client.request(
                method=method,
                url=url,
                headers=req_headers,
                json=json_body,
                params=params,
            )
        except httpx.TimeoutException:
            logger.warning("MCP request timed out method=%s path=%s", method, path)
            raise TomorrowlandClientError(
                "Request to Tomorrowland API timed out", status_code=504
            ) from None
        except httpx.RequestError as exc:
            logger.warning(
                "MCP connection error method=%s path=%s error=%s",
                method,
                path,
                exc,
            )
            raise TomorrowlandClientError(
                f"Cannot reach Tomorrowland API: {exc}", status_code=503
            ) from exc

        if response.status_code >= 400:
            detail = _extract_error_detail(response)
            log_level = logger.warning if response.status_code < 500 else logger.error
            log_level(
                "MCP API error method=%s path=%s status=%s detail=%s",
                method,
                path,
                response.status_code,
                detail or "(no detail)",
            )
            raise TomorrowlandClientError(
                detail or f"API returned HTTP {response.status_code}",
                status_code=response.status_code,
            ) from None

        return cast("dict[str, Any]", response.json())

    # ------------------------------------------------------------------
    # Tool methods (each matches one /api/agent/v1 endpoint)
    # ------------------------------------------------------------------

    def search_documents(
        self,
        query: str,
        top_k: int = 20,
        page: int = 1,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /api/agent/v1/search_documents"""
        body: dict[str, Any] = {"query": query, "top_k": top_k, "page": page}
        if filters:
            body["filters"] = filters
        return self._request("POST", "/api/agent/v1/search_documents", json_body=body)

    def get_document(self, document_id: str) -> dict[str, Any]:
        """GET /api/agent/v1/get_document"""
        return self._request(
            "GET", "/api/agent/v1/get_document", params={"document_id": document_id}
        )

    def get_passages(
        self,
        document_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /api/agent/v1/get_passages"""
        return self._request(
            "GET",
            "/api/agent/v1/get_passages",
            params={"document_id": document_id, "limit": limit, "offset": offset},
        )

    def ask_corpus(
        self,
        question: str,
        top_k: int | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/agent/v1/ask_corpus"""
        body: dict[str, Any] = {"question": question}
        if top_k is not None:
            body["top_k"] = top_k
        if document_id is not None:
            body["document_id"] = document_id
        return self._request("POST", "/api/agent/v1/ask_corpus", json_body=body)

    def get_related_documents(self, document_id: str) -> dict[str, Any]:
        """GET /api/agent/v1/get_related_documents"""
        return self._request(
            "GET",
            "/api/agent/v1/get_related_documents",
            params={"document_id": document_id},
        )

    def list_facets(self, query: str = "") -> dict[str, Any]:
        """GET /api/agent/v1/list_facets"""
        return self._request("GET", "/api/agent/v1/list_facets", params={"query": query})

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
