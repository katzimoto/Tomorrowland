"""Atlassian Server/Data Center connectors for Confluence and Jira."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import random
import re
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from services.connectors.base import ConnectorDocument, ConnectorField

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 30
_DEFAULT_LIMIT = 50
_CHUNK_SIZE = 65536  # 64 KiB read chunks for streaming downloads
_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_BACKOFF_BASE = 0.5
_BACKOFF_MAX = 30.0

# Space key validation: alphanumeric and underscores only, 1-255 chars
_VALID_SPACE_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,255}$")

# Config key defaults
_CFG_AUTH_MODE = "auth_mode"
_CFG_SPACE_KEY = "space_key"
_CFG_SPACE_KEYS = "space_keys"
_CFG_RETRY_COUNT = "retry_count"
_CFG_REQUEST_TIMEOUT = "request_timeout_seconds"
_CFG_MAX_ATTACHMENT_MB = "max_attachment_mb"
_CFG_ATTACHMENT_MIME_ALLOWLIST = "attachment_mime_allowlist"
_CFG_ATTACHMENT_MIME_BLOCKLIST = "attachment_mime_blocklist"


class _ConfigHelperMixin:
    """Helper methods for reading typed config values from a connector's config dict."""

    _config: dict[str, Any]

    def _config_str(self, key: str, default: str = "") -> str:
        return str(self._config.get(key, default)).strip()

    def _config_int(self, key: str, default: int) -> int:
        raw = self._config.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    def _config_list(self, key: str) -> list[str]:
        raw = self._config.get(key)
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(v).strip() for v in raw if v]
        return []

    def _config_bool(self, key: str, default: bool) -> bool:
        raw = self._config.get(key)
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in {"1", "true", "yes", "on"}
        return bool(raw)


class _TextExtractor(HTMLParser):
    """Small HTML-to-text parser used for API-provided page content."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        """Return the parsed text content."""
        return "\n".join(self._chunks)


@dataclass(frozen=True, slots=True)
class _DownloadedAttachment:
    """Downloaded attachment metadata ready for pipeline ingestion."""

    path: str
    sha256: str


class _AtlassianConnectorBase(_ConfigHelperMixin):
    """Shared HTTP and validation helpers for Atlassian Server/Data Center APIs."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._base_url = str(config.get("base_url", "")).rstrip("/")
        self._api_token = str(config.get("api_token", ""))
        self._username = str(config.get("username", ""))
        self._verify_not_cloud_url(self._base_url)

    def validate(self) -> None:
        """Raise ``ValueError`` when required Atlassian config is missing or unsupported."""
        if not self._base_url:
            raise ValueError("Atlassian connector requires base_url")
        parsed = urlparse(self._base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Atlassian connector base_url must be an http(s) URL")
        self._verify_not_cloud_url(self._base_url)
        if not self._api_token:
            raise ValueError("Atlassian connector requires api_token")

    def _effective_timeout(self) -> int:
        """Return the configured request timeout, or the default."""
        return self._config_int(_CFG_REQUEST_TIMEOUT, _REQUEST_TIMEOUT_SECONDS)

    def _effective_retry_count(self) -> int:
        """Return the configured retry count, or the default."""
        return self._config_int(_CFG_RETRY_COUNT, 3)

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        """Exponential backoff with jitter: 0.5s, 1.0s, 2.0s, ... capped at 30s."""
        delay = min(_BACKOFF_BASE * (2.0 ** attempt), _BACKOFF_MAX)
        return delay + random.uniform(0, 0.5 * _BACKOFF_BASE)

    @staticmethod
    def _verify_not_cloud_url(base_url: str) -> None:
        host = urlparse(base_url).hostname or ""
        if host == "atlassian.net" or host.endswith(".atlassian.net"):
            raise ValueError(
                "Atlassian Cloud (*.atlassian.net) is not supported; use Server/Data Center"
            )

    def _request_json(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON object from an authenticated Atlassian REST request.

        Retries on transient HTTP errors (429, 5xx) and network failures.
        Does not retry permanent client errors (401, 403, 404).
        """
        url = self._url(path, query=query)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(self._auth_headers())
        request = Request(url, data=data, headers=headers, method=method)
        timeout = self._effective_timeout()
        max_retries = self._effective_retry_count()

        for attempt in range(max_retries + 1):
            try:
                with urlopen(request, timeout=timeout) as response:  # noqa: S310
                    payload = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                if attempt < max_retries and exc.code in _RETRYABLE_STATUSES:
                    delay = self._backoff_seconds(attempt)
                    logger.info(
                        "Atlassian request HTTP %s on attempt %d, retrying in %.1fs: %s",
                        exc.code,
                        attempt + 1,
                        delay,
                        url,
                    )
                    time.sleep(delay)
                    continue
                raise ValueError(
                    f"Atlassian request failed with HTTP {exc.code}: {url}"
                ) from exc
            except URLError as exc:
                if attempt < max_retries:
                    delay = self._backoff_seconds(attempt)
                    logger.info(
                        "Atlassian request network error on attempt %d, retrying in %.1fs: %s",
                        attempt + 1,
                        delay,
                        url,
                    )
                    time.sleep(delay)
                    continue
                raise ValueError(f"Atlassian request failed: {exc.reason}") from exc

        parsed = json.loads(payload) if payload else {}
        if not isinstance(parsed, dict):
            raise ValueError("Atlassian API returned a non-object JSON payload")
        return parsed

    def _stream_to_file(
        self,
        response: Any,
        dest_path: str,
        filename: str,
        max_bytes: int | None = None,
    ) -> _DownloadedAttachment:
        """Stream *response* body to *dest_path* with incremental SHA256 and size check."""
        digest = hashlib.sha256()
        bytes_written = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                f.write(chunk)
                bytes_written += len(chunk)
                if max_bytes is not None and bytes_written > max_bytes:
                    raise ValueError(
                        f"Attachment {filename} exceeds maximum size of "
                        f"{max_bytes} bytes ({max_bytes / (1024*1024):.0f} MiB)"
                    )
        return _DownloadedAttachment(path=dest_path, sha256=digest.hexdigest())

    def _download_attachment(
        self,
        download_url: str,
        filename: str,
        *,
        storage_root: Path | None = None,
        max_bytes: int | None = None,
    ) -> _DownloadedAttachment:
        """Download an attachment with streaming, incremental SHA256, and size enforcement.

        The attachment bytes are streamed in ``_CHUNK_SIZE`` blocks rather than
        loaded into memory all at once.  The SHA256 digest is computed
        incrementally during the stream.

        When *storage_root* is provided the file is written directly there,
        bypassing the system temp directory entirely.

        When *max_bytes* is set, the download is aborted (and the partial file
        cleaned up) if the stream exceeds that limit.

        Retries on transient HTTP errors (429, 5xx) and network failures.
        """
        url = (
            download_url
            if download_url.startswith(("http://", "https://"))
            else urljoin(f"{self._base_url}/", download_url.lstrip("/"))
        )
        request = Request(url, headers=self._auth_headers(), method="GET")
        suffix = Path(filename).suffix
        timeout = self._effective_timeout()
        max_retries = self._effective_retry_count()

        for attempt in range(max_retries + 1):
            dest_path: str | None = None
            try:
                with urlopen(request, timeout=timeout) as response:  # noqa: S310
                    if storage_root is not None:
                        storage_root.mkdir(parents=True, exist_ok=True)
                        dest = storage_root / f"{uuid4()}{suffix}"
                        dest_path = str(dest)
                    else:
                        with tempfile.NamedTemporaryFile(
                            prefix="tomorrowland-atlassian-",
                            suffix=suffix,
                            delete=False,
                        ) as tmp:
                            dest_path = tmp.name

                    try:
                        return self._stream_to_file(
                            response, dest_path, filename, max_bytes=max_bytes
                        )
                    except ValueError:
                        with contextlib.suppress(OSError):
                            os.unlink(dest_path)
                        raise
            except HTTPError as exc:
                if attempt < max_retries and exc.code in _RETRYABLE_STATUSES:
                    delay = self._backoff_seconds(attempt)
                    logger.info(
                        "Atlassian attachment download HTTP %s on attempt %d, "
                        "retrying in %.1fs: %s",
                        exc.code,
                        attempt + 1,
                        delay,
                        url,
                    )
                    time.sleep(delay)
                    continue
                raise ValueError(
                    f"Atlassian attachment download failed with HTTP {exc.code}: {url}"
                ) from exc
            except URLError as exc:
                if attempt < max_retries:
                    delay = self._backoff_seconds(attempt)
                    logger.info(
                        "Atlassian attachment download network error on attempt %d, "
                        "retrying in %.1fs: %s",
                        attempt + 1,
                        delay,
                        url,
                    )
                    time.sleep(delay)
                    continue
                raise ValueError(f"Atlassian attachment download failed: {exc.reason}") from exc

        # Should not be reached (last attempt either returns or raises)
        raise RuntimeError("Unreachable: attachment download exhausted retries without result")

    def _mime_is_allowed(self, media_type: str) -> bool:
        """Check whether a MIME type passes the allowlist/blocklist filters.

        Blocklist wins over allowlist.  Blocklist entries ending in ``/`` are
        treated as prefix matches (e.g. ``video/`` blocks ``video/mp4``).
        If the allowlist is empty or missing, all MIME types not on the
        blocklist are allowed.
        """
        allowlist = self._config_list(_CFG_ATTACHMENT_MIME_ALLOWLIST)
        blocklist = self._config_list(_CFG_ATTACHMENT_MIME_BLOCKLIST)

        # Blocklist check first — blocklist wins over allowlist
        for blocked in blocklist:
            if blocked.endswith("/"):
                if media_type.startswith(blocked):
                    logger.debug(
                        "Attachment MIME type %s blocked by prefix rule %s",
                        media_type,
                        blocked,
                    )
                    return False
            elif media_type == blocked:
                logger.debug(
                    "Attachment MIME type %s blocked by exact rule %s",
                    media_type,
                    blocked,
                )
                return False

        # Allowlist check — empty/missing means allow all
        if not allowlist:
            return True

        for allowed in allowlist:
            if media_type == allowed:
                return True

        logger.debug(
            "Attachment MIME type %s not in allowlist; skipping",
            media_type,
        )
        return False

    def _auth_headers(self) -> dict[str, str]:
        if self._username:
            token = base64.b64encode(f"{self._username}:{self._api_token}".encode())
            return {"Authorization": f"Basic {token.decode('ascii')}"}
        return {"Authorization": f"Bearer {self._api_token}"}

    def _url(self, path: str, *, query: dict[str, Any] | None = None) -> str:
        url = urljoin(f"{self._base_url}/", path.lstrip("/"))
        if query:
            url = f"{url}?{urlencode(query)}"
        return url

    @staticmethod
    def _html_to_text(html: str) -> str:
        parser = _TextExtractor()
        parser.feed(html)
        return parser.text()

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = payload.get(key, [])
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]


class ConfluenceConnector(_AtlassianConnectorBase):
    """Poll Confluence Server/Data Center pages and attachments.

    Config options:
        auth_mode (str): Must be ``"service_account"`` (default when omitted).
        space_keys (list[str]): Restrict sync to specific space keys. Omitted
            or empty means all spaces visible to the service account.
        space_key (str): Legacy single-space config; behaves like
            ``space_keys: ["<value>"]``.
        max_attachment_mb (int): Max attachment size in MiB (default 50).
            Attachments exceeding this size are skipped.
        attachment_mime_allowlist (list[str]): If non-empty, only these MIME
            types are downloaded.
        attachment_mime_blocklist (list[str]): MIME types to skip.  Entries
            ending in ``/`` are prefix-matched.
        retry_count (int): Max retries for transient HTTP errors (default 3).
        request_timeout_seconds (int): HTTP request timeout (default 30).
    """

    supported_versions: dict[str, list[str]] = {
        "en": ["7.x", "8.x", "9.x"],
        "fr": ["7.x", "8.x"],
        "de": ["7.x", "8.x"],
        "es": ["7.x"],
        "ar": ["7.x", "8.x"],
        "zh": ["8.x", "9.x"],
        "he": ["7.x", "8.x"],
    }

    @classmethod
    def fields(cls) -> list[ConnectorField]:
        """Return admin UI field metadata for Confluence source configuration."""
        return [
            ConnectorField(
                key="base_url", label="Confluence base URL", placeholder="https://wiki.local"
            ),
            ConnectorField(key="username", label="Username (optional)", required=False),
            ConnectorField(key="api_token", label="API token or password", sensitive=True),
            ConnectorField(key="space_key", label="Space key (optional)", required=False),
            ConnectorField(
                key="updated_since",
                label="Updated since (optional)",
                required=False,
                placeholder="2026-05-01 00:00",
            ),
        ]

    def validate(self) -> None:
        """Validate Confluence connector configuration and perform a real API check.

        Steps:
        1. Validate base config (base_url, api_token, no cloud URLs).
        2. Validate auth_mode is ``"service_account"`` (default when omitted).
        3. Validate and normalize space_keys / space_key.
        4. Perform a lightweight API request to confirm connectivity and auth.
        """
        # Step 1: Base config validation
        super().validate()

        # Step 2: auth_mode validation
        auth_mode = self._config_str(_CFG_AUTH_MODE, "service_account")
        if auth_mode != "service_account":
            raise ValueError(
                f"Unsupported Confluence auth_mode: {auth_mode!r}. "
                f"Only 'service_account' is supported."
            )

        # Step 3: Validate space keys
        self._validate_space_keys()

        # Step 4: Real API check — authenticate and query a space/page
        self._check_confluence_reachability()

    def _validate_space_keys(self) -> None:
        """Validate and normalize space key config.

        Legacy ``space_key`` is mapped to ``space_keys``.  Each key must
        match the pattern ``^[A-Za-z0-9_]{{1,255}}$``.

        Note: raw config values are read directly rather than via
        ``_config_list`` so that explicit empty strings are not silently
        dropped before validation.
        """
        raw_keys = self._config.get(_CFG_SPACE_KEYS)
        space_keys: list[str] = []
        if isinstance(raw_keys, list):
            for v in raw_keys:
                if isinstance(v, str):
                    space_keys.append(v.strip())

        legacy_key = self._config_str(_CFG_SPACE_KEY)
        if not space_keys and legacy_key:
            space_keys = [legacy_key]

        for key in space_keys:
            if not key or not _VALID_SPACE_KEY_RE.match(key):
                raise ValueError(
                    f"Invalid Confluence space key: {key!r}. "
                    f"Space keys must be alphanumeric (underscores allowed), "
                    f"1-255 characters."
                )

    def _check_confluence_reachability(self) -> None:
        """Perform a lightweight API check against the Confluence instance.

        Makes a small query (limit=1) to verify:
        - The server is reachable
        - Authentication succeeds
        - The service account has access to at least one space/page
        """
        try:
            # Try to authenticate and list a space
            space_keys = self._resolve_space_keys()
            if space_keys:
                # Verify first space key exists and is accessible
                space_key = space_keys[0]
                payload = self._request_json(
                    f"/rest/api/space/{quote(space_key)}",
                    query={"expand": "homePage"},
                )
                if not isinstance(payload, dict) or not payload.get("key"):
                    raise ValueError(
                        f"Could not access Confluence space {space_key!r}. "
                        f"Check the space key and service account permissions."
                    )
            else:
                # Any space will do — just verify we can authenticate
                payload = self._request_json(
                    "/rest/api/space",
                    query={"limit": 1},
                )
                results = self._as_list(payload, "results")
                if not results:
                    # Auth works but no spaces — log a warning but don't fail
                    # (the service account may have no spaces but still be valid)
                    logger.warning(
                        "Confluence authentication succeeded but no spaces were "
                        "found for the configured service account. Sync will yield "
                        "no documents."
                    )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(
                f"Confluence connection validation failed: {exc}"
            ) from exc

    def _resolve_space_keys(self) -> list[str]:
        """Resolve the effective space keys list.

        Supports legacy ``space_key`` for backward compatibility:
        - ``space_keys`` takes precedence over ``space_key`` when both are set.
        - If ``space_keys`` is omitted/empty and ``space_key`` is set, use
          ``space_key`` as a single-element list.
        - If both are omitted or empty, return an empty list (all spaces).
        """
        space_keys = self._config_list(_CFG_SPACE_KEYS)
        legacy_key = self._config_str(_CFG_SPACE_KEY)

        if space_keys:
            return space_keys
        if legacy_key:
            logger.warning(
                "Confluence config uses legacy 'space_key' field. "
                "Consider migrating to 'space_keys' (a list). "
                "Legacy space_key=%r is treated as space_keys=[%r].",
                legacy_key,
                legacy_key,
            )
            return [legacy_key]
        return []

    def fetch_documents(self, *, storage_root: Path | None = None) -> Iterator[ConnectorDocument]:
        """Yield updated Confluence pages and their attachments."""
        self.validate()
        max_bytes = self._config_int(_CFG_MAX_ATTACHMENT_MB, 50) * 1024 * 1024
        for page in self._fetch_pages():
            page_id = str(page.get("id", ""))
            title = str(page.get("title") or f"Confluence page {page_id}")
            body = page.get("body")
            storage = body.get("storage", {}) if isinstance(body, dict) else {}
            html = str(storage.get("value", "")) if isinstance(storage, dict) else ""
            text = self._html_to_text(html)
            yield ConnectorDocument(
                external_id=f"confluence:{page_id}",
                title=title,
                mime_type="text/html",
                sha256=self._sha256_text(text),
                source_language=None,
                metadata={"atlassian_type": "confluence_page", "page_id": page_id},
                text_content=text,
            )
            yield from self._fetch_attachments(
                page_id=page_id,
                page_title=title,
                storage_root=storage_root,
                max_bytes=max_bytes,
            )

    def _fetch_pages(self) -> Iterator[dict[str, Any]]:
        cql_parts = ["type=page"]
        space_keys = self._resolve_space_keys()
        for key in space_keys:
            cql_parts.append(f"space={key}")
        updated_since = str(
            self._config.get("updated_since") or self._config.get("last_sync_at") or ""
        ).strip()
        if updated_since:
            cql_parts.append(f'lastmodified >= "{updated_since}"')
        cql = " AND ".join(cql_parts)
        start = 0
        while True:
            payload = self._request_json(
                "/rest/api/content/search",
                query={
                    "cql": cql,
                    "expand": "body.storage,version,space",
                    "limit": _DEFAULT_LIMIT,
                    "start": start,
                },
            )
            results = self._as_list(payload, "results")
            yield from results
            if len(results) < _DEFAULT_LIMIT:
                break
            start += _DEFAULT_LIMIT

    def _fetch_attachments(
        self,
        *,
        page_id: str,
        page_title: str,
        storage_root: Path | None = None,
        max_bytes: int | None = None,
    ) -> Iterator[ConnectorDocument]:
        start = 0
        skipped_count = 0
        while True:
            payload = self._request_json(
                f"/rest/api/content/{quote(page_id)}/child/attachment",
                query={"limit": _DEFAULT_LIMIT, "start": start, "expand": "version"},
            )
            attachments = self._as_list(payload, "results")
            for attachment in attachments:
                attachment_id = str(attachment.get("id", ""))
                title = str(attachment.get("title") or attachment_id)

                # Extract MIME type before downloading so filters can skip
                # early without incurring the download cost.
                metadata = attachment.get("metadata", {})
                media_type = "application/octet-stream"
                if isinstance(metadata, dict) and isinstance(metadata.get("mediaType"), str):
                    media_type = str(metadata["mediaType"])

                # MIME filter check (before download)
                if not self._mime_is_allowed(media_type):
                    skipped_count += 1
                    logger.info(
                        "Skipped attachment %s (MIME type %s blocked by filter)",
                        title,
                        media_type,
                    )
                    continue

                links = attachment.get("_links", {})
                download_link = links.get("download") if isinstance(links, dict) else None
                if not isinstance(download_link, str) or not download_link:
                    skipped_count += 1
                    continue

                try:
                    downloaded = self._download_attachment(
                        download_link, title, storage_root=storage_root, max_bytes=max_bytes
                    )
                except ValueError as exc:
                    skipped_count += 1
                    logger.warning(
                        "Skipping attachment %s (page %s): %s",
                        title,
                        page_id,
                        str(exc),
                    )
                    continue

                yield ConnectorDocument(
                    external_id=f"confluence:{page_id}:att:{attachment_id}",
                    title=f"{page_title} / {title}",
                    mime_type=media_type,
                    sha256=downloaded.sha256,
                    source_language=None,
                    metadata={
                        "atlassian_type": "confluence_attachment",
                        "page_id": page_id,
                        "attachment_id": attachment_id,
                    },
                    path=downloaded.path,
                )
            if len(attachments) < _DEFAULT_LIMIT:
                break
            start += _DEFAULT_LIMIT

        if skipped_count > 0:
            logger.info(
                "Skipped %d attachment(s) for page %s (%s)",
                skipped_count,
                page_id,
                page_title,
            )


class JiraConnector(_AtlassianConnectorBase):
    """Poll Jira Server/Data Center issues and attachments."""

    @classmethod
    def fields(cls) -> list[ConnectorField]:
        """Return admin UI field metadata for Jira source configuration."""
        return [
            ConnectorField(key="base_url", label="Jira base URL", placeholder="https://jira.local"),
            ConnectorField(key="username", label="Username (optional)", required=False),
            ConnectorField(key="api_token", label="API token or password", sensitive=True),
            ConnectorField(key="project_key", label="Project key (optional)", required=False),
            ConnectorField(key="jql", label="JQL override (optional)", required=False),
            ConnectorField(
                key="updated_since",
                label="Updated since (optional)",
                required=False,
                placeholder="2026-05-01 00:00",
            ),
        ]

    def fetch_documents(self, *, storage_root: Path | None = None) -> Iterator[ConnectorDocument]:
        """Yield updated Jira issues and their attachments."""
        self.validate()
        for issue in self._fetch_issues():
            key = str(issue.get("key", ""))
            fields = issue.get("fields", {}) if isinstance(issue.get("fields"), dict) else {}
            summary = str(fields.get("summary") or key)
            text = self._issue_text(summary=summary, fields=fields)
            yield ConnectorDocument(
                external_id=f"jira:{key}",
                title=summary,
                mime_type="text/plain",
                sha256=self._sha256_text(text),
                source_language=None,
                metadata={"atlassian_type": "jira_issue", "issue_key": key},
                text_content=text,
            )
            yield from self._fetch_attachments(
                issue_key=key, fields=fields, storage_root=storage_root
            )

    def _fetch_issues(self) -> Iterator[dict[str, Any]]:
        start_at = 0
        while True:
            payload = self._request_json(
                "/rest/api/2/search",
                method="POST",
                body={
                    "jql": self._jql(),
                    "fields": ["summary", "description", "comment", "attachment", "updated"],
                    "startAt": start_at,
                    "maxResults": _DEFAULT_LIMIT,
                },
            )
            issues = self._as_list(payload, "issues")
            yield from issues
            total_raw = payload.get("total", 0)
            total = total_raw if isinstance(total_raw, int) else 0
            start_at += len(issues)
            if not issues or start_at >= total:
                break

    def _jql(self) -> str:
        configured = str(self._config.get("jql", "")).strip()
        if configured:
            return configured
        parts: list[str] = []
        project_key = str(self._config.get("project_key", "")).strip()
        if project_key:
            parts.append(f"project = {project_key}")
        updated_since = str(
            self._config.get("updated_since") or self._config.get("last_sync_at") or ""
        ).strip()
        if updated_since:
            parts.append(f'updated >= "{updated_since}"')
        parts.append("ORDER BY updated ASC")
        return " AND ".join(parts[:-1] or ["updated is not EMPTY"]) + f" {parts[-1]}"

    def _issue_text(self, *, summary: str, fields: dict[str, Any]) -> str:
        chunks = [summary]
        description = fields.get("description")
        if description:
            chunks.append(self._jira_field_to_text(description))
        comments = fields.get("comment", {})
        comment_list = comments.get("comments", []) if isinstance(comments, dict) else []
        if isinstance(comment_list, list):
            for comment in comment_list:
                if isinstance(comment, dict) and comment.get("body"):
                    chunks.append(self._jira_field_to_text(comment["body"]))
        return "\n\n".join(chunk for chunk in chunks if chunk)

    def _fetch_attachments(
        self,
        *,
        issue_key: str,
        fields: dict[str, Any],
        storage_root: Path | None = None,
    ) -> Iterator[ConnectorDocument]:
        attachments = fields.get("attachment", [])
        if not isinstance(attachments, list):
            return
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            attachment_id = str(attachment.get("id", ""))
            filename = str(attachment.get("filename") or attachment_id)
            content_url = attachment.get("content")
            if not isinstance(content_url, str) or not content_url:
                continue
            downloaded = self._download_attachment(content_url, filename, storage_root=storage_root)
            mime_type = str(attachment.get("mimeType") or "application/octet-stream")
            yield ConnectorDocument(
                external_id=f"jira:{issue_key}:att:{attachment_id}",
                title=f"{issue_key} / {filename}",
                mime_type=mime_type,
                sha256=downloaded.sha256,
                source_language=None,
                metadata={
                    "atlassian_type": "jira_attachment",
                    "issue_key": issue_key,
                    "attachment_id": attachment_id,
                },
                path=downloaded.path,
            )

    @classmethod
    def _jira_field_to_text(cls, value: Any) -> str:
        if isinstance(value, str):
            return cls._html_to_text(value) if "<" in value and ">" in value else value
        if isinstance(value, dict):
            content = value.get("content")
            if isinstance(content, list):
                return "\n".join(cls._jira_field_to_text(item) for item in content)
            text = value.get("text")
            if isinstance(text, str):
                return text
        if isinstance(value, list):
            return "\n".join(cls._jira_field_to_text(item) for item in value)
        return ""
