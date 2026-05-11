"""Atlassian Server/Data Center connectors for Confluence and Jira."""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from services.connectors.base import ConnectorDocument, ConnectorField

_REQUEST_TIMEOUT_SECONDS = 30
_DEFAULT_LIMIT = 50


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


class _AtlassianConnectorBase:
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
        """Return a JSON object from an authenticated Atlassian REST request."""
        url = self._url(path, query=query)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(self._auth_headers())
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            raise ValueError(f"Atlassian request failed with HTTP {exc.code}: {url}") from exc
        except URLError as exc:
            raise ValueError(f"Atlassian request failed: {exc.reason}") from exc
        parsed = json.loads(payload) if payload else {}
        if not isinstance(parsed, dict):
            raise ValueError("Atlassian API returned a non-object JSON payload")
        return parsed

    def _download_attachment(self, download_url: str, filename: str) -> _DownloadedAttachment:
        """Download an attachment to a temp file and return its path and SHA256."""
        url = (
            download_url
            if download_url.startswith(("http://", "https://"))
            else urljoin(f"{self._base_url}/", download_url.lstrip("/"))
        )
        request = Request(url, headers=self._auth_headers(), method="GET")
        suffix = Path(filename).suffix
        try:
            with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                data = response.read()
        except HTTPError as exc:
            raise ValueError(
                f"Atlassian attachment download failed with HTTP {exc.code}: {url}"
            ) from exc
        except URLError as exc:
            raise ValueError(f"Atlassian attachment download failed: {exc.reason}") from exc

        digest = hashlib.sha256(data).hexdigest()
        with tempfile.NamedTemporaryFile(
            prefix="tomorrowland-atlassian-", suffix=suffix, delete=False
        ) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        return _DownloadedAttachment(path=tmp_path, sha256=digest)

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
    """Poll Confluence Server/Data Center pages and attachments."""

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

    def fetch_documents(self) -> Iterator[ConnectorDocument]:
        """Yield updated Confluence pages and their attachments."""
        self.validate()
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
            yield from self._fetch_attachments(page_id=page_id, page_title=title)

    def _fetch_pages(self) -> Iterator[dict[str, Any]]:
        cql_parts = ["type=page"]
        space_key = str(self._config.get("space_key", "")).strip()
        if space_key:
            cql_parts.append(f"space={space_key}")
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

    def _fetch_attachments(self, *, page_id: str, page_title: str) -> Iterator[ConnectorDocument]:
        start = 0
        while True:
            payload = self._request_json(
                f"/rest/api/content/{quote(page_id)}/child/attachment",
                query={"limit": _DEFAULT_LIMIT, "start": start, "expand": "version"},
            )
            attachments = self._as_list(payload, "results")
            for attachment in attachments:
                attachment_id = str(attachment.get("id", ""))
                title = str(attachment.get("title") or attachment_id)
                links = attachment.get("_links", {})
                download_link = links.get("download") if isinstance(links, dict) else None
                if not isinstance(download_link, str) or not download_link:
                    continue
                downloaded = self._download_attachment(download_link, title)
                metadata = attachment.get("metadata", {})
                media_type = "application/octet-stream"
                if isinstance(metadata, dict) and isinstance(metadata.get("mediaType"), str):
                    media_type = str(metadata["mediaType"])
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

    def fetch_documents(self) -> Iterator[ConnectorDocument]:
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
            yield from self._fetch_attachments(issue_key=key, fields=fields)

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
        self, *, issue_key: str, fields: dict[str, Any]
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
            downloaded = self._download_attachment(content_url, filename)
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
