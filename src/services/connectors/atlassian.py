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

# Jira-specific config key defaults
_CFG_PROJECT_KEYS = "project_keys"
_CFG_PROJECT_KEY = "project_key"
_CFG_JQL = "jql"
_CFG_INCLUDE_COMMENTS = "include_comments"
_CFG_COMMENTS_MODE = "comments_mode"
_CFG_MAX_COMMENTS_PER_ISSUE = "max_comments_per_issue"
_CFG_COMMENT_BODY_FORMAT = "comment_body_format"
_CFG_INCLUDE_CHANGELOG = "include_changelog"
_CFG_CHANGELOG_FIELDS = "changelog_fields"
_CFG_INCLUDE_WORKLOGS = "include_worklogs"
_CFG_UPDATED_SINCE = "updated_since"

# Jira project key validation: alphanumeric and underscores only, 1-255 chars
_VALID_PROJECT_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,255}$")


def _subtask_metadata(subtask: dict[str, Any]) -> dict[str, Any]:
    """Extract key, summary and status from a Jira subtask object."""
    sub_fields = subtask.get("fields")
    sub_fields = sub_fields if isinstance(sub_fields, dict) else {}
    status = sub_fields.get("status")
    status = status if isinstance(status, dict) else {}
    return {
        "key": subtask.get("key"),
        "summary": sub_fields.get("summary"),
        "status": status.get("name"),
    }


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
        delay = min(_BACKOFF_BASE * (2.0**attempt), _BACKOFF_MAX)
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
                raise ValueError(f"Atlassian request failed with HTTP {exc.code}: {url}") from exc
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
                        f"{max_bytes} bytes ({max_bytes / (1024 * 1024):.0f} MiB)"
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
            raise ValueError(f"Confluence connection validation failed: {exc}") from exc

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
    """Poll Jira Server/Data Center issues and attachments with rich metadata.

    Config options:
        auth_mode (str): Must be ``"service_account"`` (default when omitted).
        project_keys (list[str]): Restrict sync to specific project keys. Omitted
            or empty means all issues visible to the service account.
        project_key (str): Legacy single-project config; behaves like
            ``project_keys: ["<value>"]``.
        jql (str): Advanced JQL override. When set, wins over ``project_keys``,
            ``project_key``, and ``updated_since``.
        updated_since (str): RFC-3339 or Jira-friendly datetime string.
        include_comments (bool): Include comments in issue text (default True).
        comments_mode (str): ``"inline"`` (default) — render into issue text.
        max_comments_per_issue (int): Max comments to include (default 200).
        comment_body_format (str): ``"plain"`` (default) — plain text extracted.
        max_attachment_mb (int): Max attachment size in MiB (default 50).
        attachment_mime_allowlist (list[str]): If non-empty, only these MIME
            types are downloaded.
        attachment_mime_blocklist (list[str]): MIME types to skip. Entries
            ending in ``/`` are prefix-matched.
        retry_count (int): Max retries for transient HTTP errors (default 3).
        request_timeout_seconds (int): HTTP request timeout (default 30).
        include_changelog (bool): Include changelog in metadata (default False).
        changelog_fields (list[str]): Changelog fields to track (default:
            ``["status", "assignee", "priority", "resolution"]``).
        include_worklogs (bool): Include worklogs (default False).
    """

    _JIRA_SEARCH_FIELDS: list[str] = [
        "summary",
        "description",
        "comment",
        "attachment",
        "project",
        "issuetype",
        "status",
        "priority",
        "resolution",
        "labels",
        "components",
        "fixVersions",
        "versions",
        "created",
        "updated",
        "resolutiondate",
        "assignee",
        "reporter",
        "creator",
        "parent",
        "subtasks",
        "issuelinks",
    ]

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

    # ── Validation ────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate Jira connector configuration and perform a real API check.

        Steps:
        1. Validate base config (base_url, api_token, no cloud URLs).
        2. Validate auth_mode is ``"service_account"`` (default when omitted).
        3. Validate and normalize project_keys / project_key.
        4. Perform a lightweight API request to confirm connectivity and auth.
        """
        # Step 1: Base config validation
        super().validate()

        # Step 2: auth_mode validation
        auth_mode = self._config_str(_CFG_AUTH_MODE, "service_account")
        if auth_mode != "service_account":
            raise ValueError(
                f"Unsupported Jira auth_mode: {auth_mode!r}. Only 'service_account' is supported."
            )

        # Step 3: Validate project keys
        self._validate_project_keys()

        # Step 4: Real API check — authenticate and query projects/issues
        self._check_jira_reachability()

    def _validate_project_keys(self) -> None:
        """Validate and normalize project key config.

        Legacy ``project_key`` is mapped to ``project_keys``. Each key must
        match the pattern ``^[A-Za-z0-9_]{{1,255}}$``.

        Note: raw config values are read directly rather than via
        ``_config_list`` so that explicit empty strings are not silently
        dropped before validation.
        """
        raw_keys = self._config.get(_CFG_PROJECT_KEYS)
        project_keys: list[str] = []
        if isinstance(raw_keys, list):
            for v in raw_keys:
                if isinstance(v, str):
                    project_keys.append(v.strip())

        legacy_key = self._config_str(_CFG_PROJECT_KEY)
        if not project_keys and legacy_key:
            project_keys = [legacy_key]

        for key in project_keys:
            if not key or not _VALID_PROJECT_KEY_RE.match(key):
                raise ValueError(
                    f"Invalid Jira project key: {key!r}. "
                    f"Project keys must be alphanumeric (underscores allowed), "
                    f"1-255 characters."
                )

    def _resolve_project_keys(self) -> list[str]:
        """Resolve the effective project keys list.

        Supports legacy ``project_key`` for backward compatibility:
        - ``project_keys`` takes precedence over ``project_key`` when both are set.
        - If ``project_keys`` is omitted/empty and ``project_key`` is set, use
          ``project_key`` as a single-element list.
        - If both are omitted or empty, return an empty list (all projects).
        """
        project_keys = self._config_list(_CFG_PROJECT_KEYS)
        legacy_key = self._config_str(_CFG_PROJECT_KEY)

        if project_keys:
            return project_keys
        if legacy_key:
            logger.warning(
                "Jira config uses legacy 'project_key' field. "
                "Consider migrating to 'project_keys' (a list). "
                "Legacy project_key=%r is treated as project_keys=[%r].",
                legacy_key,
                legacy_key,
            )
            return [legacy_key]
        return []

    def _check_jira_reachability(self) -> None:
        """Perform a lightweight API check against the Jira instance.

        Makes a small query to verify:
        - The server is reachable
        - Authentication succeeds
        - The service account has access to configured projects (if any)
        """
        try:
            # First verify basic auth by calling /rest/api/2/myself
            myself = self._request_json("/rest/api/2/myself")
            if not isinstance(myself, dict) or not myself.get("name"):
                raise ValueError(
                    "Jira authentication succeeded but returned an unexpected response."
                )

            # If project_keys are configured, verify they exist and are accessible
            project_keys = self._resolve_project_keys()
            if project_keys:
                for project_key in project_keys:
                    payload = self._request_json(
                        f"/rest/api/2/project/{quote(project_key)}",
                    )
                    if not isinstance(payload, dict) or not payload.get("key"):
                        raise ValueError(
                            f"Could not access Jira project {project_key!r}. "
                            f"Check the project key and service account permissions."
                        )
            else:
                # No specific projects — just verify we can search at least one issue
                payload = self._request_json(
                    "/rest/api/2/search",
                    method="POST",
                    body={
                        "jql": "ORDER BY updated ASC",
                        "maxResults": 1,
                        "fields": ["summary"],
                    },
                )
                if not isinstance(payload, dict):
                    raise ValueError("Jira search returned an unexpected response.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Jira connection validation failed: {exc}") from exc

    # ── Document fetching ─────────────────────────────────────────────────

    def fetch_documents(self, *, storage_root: Path | None = None) -> Iterator[ConnectorDocument]:
        """Yield updated Jira issues and their attachments with rich metadata."""
        self.validate()
        max_bytes = self._config_int(_CFG_MAX_ATTACHMENT_MB, 50) * 1024 * 1024
        for issue in self._fetch_issues():
            key = str(issue.get("key", ""))
            fields = issue.get("fields", {}) if isinstance(issue.get("fields"), dict) else {}
            summary = str(fields.get("summary") or key)
            text = self._issue_text(summary=summary, fields=fields)
            metadata = self._build_issue_metadata(key=key, fields=fields)
            yield ConnectorDocument(
                external_id=f"jira:{key}",
                title=summary,
                mime_type="text/plain",
                sha256=self._sha256_text(text),
                source_language=None,
                metadata=metadata,
                text_content=text,
            )
            yield from self._fetch_attachments(
                issue_key=key,
                fields=fields,
                storage_root=storage_root,
                max_bytes=max_bytes,
            )

    def _fetch_issues(self) -> Iterator[dict[str, Any]]:
        start_at = 0
        while True:
            payload = self._request_json(
                "/rest/api/2/search",
                method="POST",
                body={
                    "jql": self._jql(),
                    "fields": self._JIRA_SEARCH_FIELDS,
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
        """Build the JQL query string.

        Rules:
        - If ``jql`` is configured and non-empty, it wins over everything.
        - Otherwise build safe default JQL from ``project_keys`` / ``project_key``
          and ``updated_since`` / ``last_sync_at``.
        - Always apply ``ORDER BY updated ASC`` unless a custom query already
          defines ordering (check for ``ORDER BY`` in the configured JQL).
        """
        configured = self._config_str(_CFG_JQL)
        if configured:
            # If a custom JQL already has ordering, leave it; otherwise append
            if "ORDER BY" not in configured.upper():
                return f"{configured} ORDER BY updated ASC"
            return configured

        parts: list[str] = []
        project_keys = self._resolve_project_keys()
        if project_keys:
            if len(project_keys) == 1:
                parts.append(f"project = {project_keys[0]}")
            else:
                keys = ", ".join(project_keys)
                parts.append(f"project IN ({keys})")

        updated_since = self._config_str(
            _CFG_UPDATED_SINCE,
            default=str(self._config.get("last_sync_at") or ""),
        )
        if updated_since:
            parts.append(f'updated >= "{updated_since}"')

        parts.append("ORDER BY updated ASC")
        return " AND ".join(parts[:-1] or ["updated is not EMPTY"]) + f" {parts[-1]}"

    # ── Issue text and metadata ───────────────────────────────────────────

    def _issue_text(self, *, summary: str, fields: dict[str, Any]) -> str:
        """Build rich searchable issue text from Jira issue fields."""
        lines: list[str] = []

        # Summary line
        lines.append(f"Summary: {summary}")

        # Description
        description = fields.get("description")
        if description:
            desc_text = self._jira_field_to_text(description)
            if desc_text:
                lines.append("")
                lines.append("Description:")
                lines.append(desc_text)

        # Project
        project = fields.get("project")
        if isinstance(project, dict):
            pkey = project.get("key", "")
            pname = project.get("name", "")
            if pkey or pname:
                lines.append("")
                lines.append(f"Project: {pkey or pname}{f' ({pname})' if pkey and pname else ''}")

        # Issue type
        issuetype = fields.get("issuetype")
        if isinstance(issuetype, dict):
            it_name = issuetype.get("name", "")
            if it_name:
                lines.append(f"Issue Type: {it_name}")

        # Status
        status = fields.get("status")
        if isinstance(status, dict):
            s_name = status.get("name", "")
            if s_name:
                lines.append(f"Status: {s_name}")

        # Priority
        priority = fields.get("priority")
        if isinstance(priority, dict):
            p_name = priority.get("name", "")
            if p_name:
                lines.append(f"Priority: {p_name}")

        # Resolution
        resolution = fields.get("resolution")
        if isinstance(resolution, dict):
            r_name = resolution.get("name", "")
            if r_name:
                lines.append(f"Resolution: {r_name}")

        # Labels
        labels = fields.get("labels")
        if isinstance(labels, list) and labels:
            lines.append(f"Labels: {', '.join(labels)}")

        # Components
        components = fields.get("components")
        if isinstance(components, list):
            comp_names = [c.get("name", "") for c in components if isinstance(c, dict)]
            if comp_names:
                lines.append(f"Components: {', '.join(comp_names)}")

        # Fix versions
        fix_versions = fields.get("fixVersions")
        if isinstance(fix_versions, list):
            fv_names = [v.get("name", "") for v in fix_versions if isinstance(v, dict)]
            if fv_names:
                lines.append(f"Fix Versions: {', '.join(fv_names)}")

        # Affects versions
        versions = fields.get("versions")
        if isinstance(versions, list):
            v_names = [v.get("name", "") for v in versions if isinstance(v, dict)]
            if v_names:
                lines.append(f"Affects Versions: {', '.join(v_names)}")

        # Dates
        created = fields.get("created")
        if created:
            lines.append(f"Created: {created}")
        updated = fields.get("updated")
        if updated:
            lines.append(f"Updated: {updated}")
        resolutiondate = fields.get("resolutiondate")
        if resolutiondate:
            lines.append(f"Resolution Date: {resolutiondate}")

        # People fields
        assignee = fields.get("assignee")
        if isinstance(assignee, dict) and assignee.get("displayName"):
            lines.append(f"Assignee: {assignee['displayName']}")
        reporter = fields.get("reporter")
        if isinstance(reporter, dict) and reporter.get("displayName"):
            lines.append(f"Reporter: {reporter['displayName']}")
        creator = fields.get("creator")
        if isinstance(creator, dict) and creator.get("displayName"):
            lines.append(f"Creator: {creator['displayName']}")

        # Parent
        parent = fields.get("parent")
        if isinstance(parent, dict):
            parent_key = parent.get("key", "")
            parent_fields = parent.get("fields", {})
            if not isinstance(parent_fields, dict):
                parent_fields = {}
            parent_summary = parent_fields.get("summary", "")
            if parent_key:
                parent_label = parent_key
                if parent_summary:
                    parent_label += f" ({parent_summary})"
                lines.append(f"Parent: {parent_label}")

        # Subtasks
        subtasks = fields.get("subtasks")
        if isinstance(subtasks, list) and subtasks:
            sub_lines: list[str] = []
            for sub in subtasks:
                if isinstance(sub, dict):
                    sub_key = sub.get("key", "")
                    sub_fields = sub.get("fields", {})
                    if not isinstance(sub_fields, dict):
                        sub_fields = {}
                    sub_summary = sub_fields.get("summary", "")
                    sub_status = sub_fields.get("status", {})
                    if not isinstance(sub_status, dict):
                        sub_status = {}
                    sub_status_name = sub_status.get("name", "")
                    part = sub_key
                    if sub_summary:
                        part += f" ({sub_summary})"
                    if sub_status_name:
                        part += f" [{sub_status_name}]"
                    sub_lines.append(f"  - {part}")
            if sub_lines:
                lines.append("Subtasks:")
                lines.extend(sub_lines)

        # Issue links
        issuelinks = fields.get("issuelinks")
        if isinstance(issuelinks, list) and issuelinks:
            link_lines: list[str] = []
            for link in issuelinks:
                if not isinstance(link, dict):
                    continue
                link_type = link.get("type", {})
                if not isinstance(link_type, dict):
                    continue
                type_name = link_type.get("name", "related to")

                inward_issue = link.get("inwardIssue")
                outward_issue = link.get("outwardIssue")

                if isinstance(inward_issue, dict):
                    linked_key = inward_issue.get("key", "")
                    linked_fields = inward_issue.get("fields", {})
                    linked_summary = ""
                    linked_status = ""
                    if isinstance(linked_fields, dict):
                        linked_summary = linked_fields.get("summary", "")
                        linked_status_obj = linked_fields.get("status", {})
                        linked_status = ""
                        if isinstance(linked_status_obj, dict):
                            linked_status = linked_status_obj.get("name", "")
                    direction = link_type.get("inward", type_name)
                    part = linked_key
                    if linked_summary:
                        part += f" ({linked_summary})"
                    if linked_status:
                        part += f" [{linked_status}]"
                    link_lines.append(f"  - {direction}  {part}")

                if isinstance(outward_issue, dict):
                    linked_key = outward_issue.get("key", "")
                    linked_fields = outward_issue.get("fields", {})
                    linked_summary = ""
                    linked_status = ""
                    if isinstance(linked_fields, dict):
                        linked_summary = linked_fields.get("summary", "")
                        linked_status_obj = linked_fields.get("status", {})
                        linked_status = ""
                        if isinstance(linked_status_obj, dict):
                            linked_status = linked_status_obj.get("name", "")
                    direction = link_type.get("outward", type_name)
                    part = linked_key
                    if linked_summary:
                        part += f" ({linked_summary})"
                    if linked_status:
                        part += f" [{linked_status}]"
                    link_lines.append(f"  - {direction}  {part}")

            if link_lines:
                lines.append("Issue Links:")
                lines.extend(link_lines)

        # Comments
        include_comments = self._config_bool(_CFG_INCLUDE_COMMENTS, True)
        max_comments = self._config_int(_CFG_MAX_COMMENTS_PER_ISSUE, 200)

        if include_comments:
            comments = fields.get("comment", {})
            comment_list = comments.get("comments", []) if isinstance(comments, dict) else []
            if isinstance(comment_list, list) and comment_list:
                rendered_comments: list[str] = []
                for comment in comment_list[:max_comments]:
                    if not isinstance(comment, dict):
                        continue
                    body = comment.get("body")
                    if not body:
                        continue
                    # Author
                    author = comment.get("author", {})
                    author_name = ""
                    if isinstance(author, dict):
                        author_name = author.get("displayName", "") or author.get("name", "")
                    # Timestamp
                    created_ts = comment.get("created", "")
                    if not author_name:
                        author_name = "Unknown"
                    header = author_name
                    if created_ts:
                        header += f" ({created_ts})"

                    body_text = self._jira_field_to_text(body)

                    rendered_comments.append(f"---\n{header}:\n{body_text}")

                if rendered_comments:
                    lines.append("")
                    lines.append("Comments:")
                    lines.extend(rendered_comments)

        return "\n".join(lines)

    def _build_issue_metadata(self, key: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Build structured metadata dict from Jira issue fields."""
        metadata: dict[str, Any] = {
            "atlassian_type": "jira_issue",
            "issue_key": key,
        }

        # Project
        project = fields.get("project")
        if isinstance(project, dict):
            metadata["project_key"] = project.get("key")
            metadata["project_name"] = project.get("name")

        # Issue type
        issuetype = fields.get("issuetype")
        if isinstance(issuetype, dict):
            metadata["issuetype"] = issuetype.get("name")

        # Status
        status = fields.get("status")
        if isinstance(status, dict):
            metadata["status"] = status.get("name")
            status_category = status.get("statusCategory", {})
            if isinstance(status_category, dict):
                metadata["status_category"] = status_category.get("name")

        # Priority
        priority = fields.get("priority")
        if isinstance(priority, dict):
            metadata["priority"] = priority.get("name")

        # Resolution
        resolution = fields.get("resolution")
        if isinstance(resolution, dict):
            metadata["resolution"] = resolution.get("name")

        # Labels
        labels = fields.get("labels")
        if isinstance(labels, list):
            metadata["labels"] = labels

        # Components
        components = fields.get("components")
        if isinstance(components, list):
            metadata["components"] = [c.get("name") for c in components if isinstance(c, dict)]

        # Fix versions
        fix_versions = fields.get("fixVersions")
        if isinstance(fix_versions, list):
            metadata["fixVersions"] = [v.get("name") for v in fix_versions if isinstance(v, dict)]

        # Affects versions
        versions = fields.get("versions")
        if isinstance(versions, list):
            metadata["versions"] = [v.get("name") for v in versions if isinstance(v, dict)]

        # Dates
        created = fields.get("created")
        if created:
            metadata["created"] = str(created)
        updated = fields.get("updated")
        if updated:
            metadata["updated"] = str(updated)
        resolutiondate = fields.get("resolutiondate")
        if resolutiondate:
            metadata["resolutiondate"] = str(resolutiondate)

        # People fields
        assignee = fields.get("assignee")
        if isinstance(assignee, dict):
            metadata["assignee"] = self._format_people_field(assignee)
        reporter = fields.get("reporter")
        if isinstance(reporter, dict):
            metadata["reporter"] = self._format_people_field(reporter)
        creator = fields.get("creator")
        if isinstance(creator, dict):
            metadata["creator"] = self._format_people_field(creator)

        # Parent
        parent = fields.get("parent")
        if isinstance(parent, dict):
            parent_fields = parent.get("fields", {})
            if not isinstance(parent_fields, dict):
                parent_fields = {}
            metadata["parent"] = {
                "key": parent.get("key"),
                "summary": parent_fields.get("summary"),
            }

        # Subtasks
        subtasks = fields.get("subtasks")
        if isinstance(subtasks, list):
            metadata["subtasks"] = [_subtask_metadata(s) for s in subtasks if isinstance(s, dict)]

        # Issue links
        issuelinks = fields.get("issuelinks")
        if isinstance(issuelinks, list):
            links_meta: list[dict[str, Any]] = []
            for link in issuelinks:
                if not isinstance(link, dict):
                    continue
                link_type = link.get("type", {})
                if not isinstance(link_type, dict):
                    continue

                entry: dict[str, Any] = {
                    "type": link_type.get("name"),
                }

                inward = link.get("inwardIssue")
                if isinstance(inward, dict):
                    entry["direction"] = "inward"
                    inward_fields = inward.get("fields", {})
                    if not isinstance(inward_fields, dict):
                        inward_fields = {}
                    entry["linked_issue_key"] = inward.get("key")
                    entry["linked_issue_summary"] = inward_fields.get("summary")
                    inward_status = inward_fields.get("status", {})
                    entry["linked_issue_status"] = (
                        inward_status.get("name") if isinstance(inward_status, dict) else None
                    )
                    links_meta.append(entry)
                    entry = {"type": link_type.get("name")}

                outward = link.get("outwardIssue")
                if isinstance(outward, dict):
                    entry["direction"] = "outward"
                    outward_fields = outward.get("fields", {})
                    if not isinstance(outward_fields, dict):
                        outward_fields = {}
                    entry["linked_issue_key"] = outward.get("key")
                    entry["linked_issue_summary"] = outward_fields.get("summary")
                    outward_status = outward_fields.get("status", {})
                    entry["linked_issue_status"] = (
                        outward_status.get("name") if isinstance(outward_status, dict) else None
                    )
                    links_meta.append(entry)

            if links_meta:
                metadata["issuelinks"] = links_meta

        # Comments metadata
        include_comments = self._config_bool(_CFG_INCLUDE_COMMENTS, True)
        if include_comments:
            comments = fields.get("comment", {})
            comment_list = comments.get("comments", []) if isinstance(comments, dict) else []
            if isinstance(comment_list, list):
                max_comments = self._config_int(_CFG_MAX_COMMENTS_PER_ISSUE, 200)
                comments_meta: list[dict[str, Any]] = []
                for comment in comment_list[:max_comments]:
                    if not isinstance(comment, dict):
                        continue
                    comment_entry: dict[str, Any] = {}

                    # Author
                    author = comment.get("author", {})
                    if isinstance(author, dict):
                        comment_entry["author"] = self._format_people_field(author)

                    # Update author
                    update_author = comment.get("updateAuthor", {})
                    if isinstance(update_author, dict) and update_author:
                        comment_entry["update_author"] = self._format_people_field(update_author)

                    # Timestamps
                    created_ts = comment.get("created")
                    if created_ts:
                        comment_entry["created"] = str(created_ts)
                    updated_ts = comment.get("updated")
                    if updated_ts:
                        comment_entry["updated"] = str(updated_ts)

                    # Visibility
                    visibility = comment.get("visibility")
                    if isinstance(visibility, dict):
                        comment_entry["visibility"] = {
                            "type": visibility.get("type"),
                            "value": visibility.get("value"),
                        }

                    # Body (stripped to text for metadata, but not searchable)
                    body = comment.get("body")
                    if body:
                        body_text = self._jira_field_to_text(body)
                        if body_text:
                            comment_entry["body_preview"] = body_text[:500]

                    if comment_entry:
                        comments_meta.append(comment_entry)

                if comments_meta:
                    metadata["comments"] = comments_meta

        return metadata

    @staticmethod
    def _format_people_field(person: dict[str, Any]) -> dict[str, Any]:
        """Extract safe stable identifiers and display fields from a Jira people field.

        Captures:
        - key (Jira user key, stable identifier)
        - name (username)
        - display_name (full display name)
        - email (if available)
        - active (account status)
        """
        result: dict[str, Any] = {}
        for src_key, dst_key in [
            ("key", "key"),
            ("name", "name"),
            ("displayName", "display_name"),
            ("emailAddress", "email"),
        ]:
            val = person.get(src_key)
            if val is not None:
                result[dst_key] = val
        active = person.get("active")
        if active is not None:
            result["active"] = bool(active)
        return result

    # ── Attachment handling ───────────────────────────────────────────────

    def _fetch_attachments(
        self,
        *,
        issue_key: str,
        fields: dict[str, Any],
        storage_root: Path | None = None,
        max_bytes: int | None = None,
    ) -> Iterator[ConnectorDocument]:
        attachments = fields.get("attachment", [])
        if not isinstance(attachments, list):
            return
        skipped_count = 0
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            attachment_id = str(attachment.get("id", ""))
            filename = str(attachment.get("filename") or attachment_id)
            content_url = attachment.get("content")
            if not isinstance(content_url, str) or not content_url:
                skipped_count += 1
                continue

            # MIME type check (before download)
            mime_type = str(attachment.get("mimeType") or "application/octet-stream")
            if not self._mime_is_allowed(mime_type):
                skipped_count += 1
                logger.info(
                    "Skipped Jira attachment %s (MIME type %s blocked by filter)",
                    filename,
                    mime_type,
                )
                continue

            try:
                downloaded = self._download_attachment(
                    content_url, filename, storage_root=storage_root, max_bytes=max_bytes
                )
            except ValueError as exc:
                skipped_count += 1
                logger.warning(
                    "Skipping Jira attachment %s (issue %s): %s",
                    filename,
                    issue_key,
                    str(exc),
                )
                continue

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

        if skipped_count > 0:
            logger.info(
                "Skipped %d attachment(s) for issue %s",
                skipped_count,
                issue_key,
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
