"""NiFi event envelope parsing and connector normalization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from services.connectors.base import ConnectorDocument, ConnectorField

PayloadType = Literal["inline_text", "staged_file"]


class NiFiEventError(ValueError):
    """Raised when a NiFi event cannot be parsed or normalized safely."""


class NiFiEventPayload(BaseModel):
    """Release-supported NiFi event payload descriptor."""

    model_config = ConfigDict(extra="forbid")

    type: PayloadType
    text: str | None = None
    path: str | None = None

    @model_validator(mode="after")
    def validate_payload_fields(self) -> NiFiEventPayload:
        """Ensure the payload has exactly the data required for its strategy."""
        if self.type == "inline_text":
            if self.text is None or not self.text:
                raise ValueError("inline_text payload requires non-empty text")
            if self.path is not None:
                raise ValueError("inline_text payload must not include path")
        if self.type == "staged_file":
            if self.path is None or not self.path:
                raise ValueError("staged_file payload requires non-empty path")
            if self.text is not None:
                raise ValueError("staged_file payload must not include text")
        return self


class NiFiEventEnvelope(BaseModel):
    """Validated envelope for Kafka-delivered NiFi flow-file events."""

    model_config = ConfigDict(extra="forbid")

    source_id: UUID | None = None
    source_key: str | None = Field(default=None, min_length=1, max_length=200)
    external_id: str = Field(min_length=1, max_length=512)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    filename: str | None = Field(default=None, min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=255)
    source_language: str | None = Field(default=None, min_length=2, max_length=16)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    event_timestamp: datetime | None = None
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    dlq_id: str | None = Field(default=None, min_length=1, max_length=128)
    payload: NiFiEventPayload

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        """Require lowercase hexadecimal SHA-256 strings when a checksum is supplied."""
        if value is None:
            return None
        if any(char not in "0123456789abcdef" for char in value):
            raise ValueError("sha256 must be lowercase hexadecimal")
        return value

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Accept only JSON-object metadata to avoid leaking raw payload structures."""
        json.dumps(value)
        return value

    @model_validator(mode="after")
    def validate_source_and_title(self) -> NiFiEventEnvelope:
        """Require a source identifier and a user-facing title or filename."""
        if self.source_id is None and self.source_key is None:
            raise ValueError("source_id or source_key is required")
        if self.title is None and self.filename is None:
            raise ValueError("title or filename is required")
        return self

    @property
    def display_title(self) -> str:
        """Return the preferred title for the normalized document."""
        return self.title or self.filename or self.external_id


def parse_nifi_event(raw: bytes | str | dict[str, Any]) -> NiFiEventEnvelope:
    """Parse and validate a NiFi event envelope without exposing payload contents."""
    try:
        if isinstance(raw, bytes):
            data = json.loads(raw.decode("utf-8"))
        elif isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw
        if not isinstance(data, dict):
            raise NiFiEventError("NiFi event must be a JSON object")
        return NiFiEventEnvelope.model_validate(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NiFiEventError("Malformed NiFi event JSON") from exc
    except (ValidationError, TypeError, ValueError) as exc:
        raise NiFiEventError("Invalid NiFi event envelope") from exc


class NiFiConnector:
    """Normalize Kafka-delivered NiFi flow-file events into connector documents."""

    @classmethod
    def fields(cls) -> list[ConnectorField]:
        return [
            ConnectorField(
                key="source_key",
                label="NiFi source key",
                required=False,
                placeholder="finance-flow",
            ),
            ConnectorField(
                key="staging_root",
                label="Staged file root",
                required=False,
                placeholder="/var/lib/tomorrowland/nifi-staging",
            ),
            ConnectorField(
                key="api_token",
                label="API token (reserved)",
                required=False,
                sensitive=True,
            ),
        ]

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._source_id = str(config.get("source_id") or "") or None
        self._source_key = str(config.get("source_key") or "") or None
        staging_root = str(config.get("staging_root") or "")
        self._staging_root = Path(staging_root).resolve() if staging_root else None

    def validate(self) -> None:
        """Validate optional NiFi connector configuration."""
        if self._staging_root is not None and not self._staging_root.exists():
            raise ValueError("NiFi staging_root does not exist")
        if self._staging_root is not None and not self._staging_root.is_dir():
            raise ValueError("NiFi staging_root is not a directory")

    def fetch_documents(self) -> Iterator[ConnectorDocument]:
        """NiFi ingestion is event-driven; bulk polling is intentionally unsupported."""
        return iter(())

    def normalize_event(self, event: NiFiEventEnvelope) -> ConnectorDocument:
        """Normalize one validated NiFi event into the standard connector document contract."""
        self._ensure_event_matches_config(event)
        path: str | None = None
        text_content: str | None = None
        if event.payload.type == "inline_text":
            if event.payload.text is None:
                raise NiFiEventError("NiFi inline payload text is missing")
            text_content = event.payload.text
            if event.sha256 is not None:
                calculated = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
                if calculated != event.sha256:
                    raise NiFiEventError("NiFi inline payload checksum mismatch")
        else:
            path = self._resolve_staged_path(event.payload.path)
            if event.sha256 is not None:
                calculated = hashlib.sha256(Path(path).read_bytes()).hexdigest()
                if calculated != event.sha256:
                    raise NiFiEventError("NiFi staged payload checksum mismatch")

        metadata = self._safe_metadata(event)
        return ConnectorDocument(
            external_id=f"nifi:{event.external_id}",
            title=event.display_title,
            mime_type=event.mime_type,
            sha256=event.sha256,
            source_language=event.source_language,
            metadata=metadata,
            path=path,
            text_content=text_content,
        )

    def _ensure_event_matches_config(self, event: NiFiEventEnvelope) -> None:
        if (
            self._source_id is not None
            and event.source_id is not None
            and str(event.source_id) != self._source_id
        ):
            raise NiFiEventError("NiFi event source_id does not match configured source")
        if (
            self._source_key is not None
            and event.source_key is not None
            and event.source_key != self._source_key
        ):
            raise NiFiEventError("NiFi event source_key does not match configured source")

    def _resolve_staged_path(self, raw_path: str | None) -> str:
        if self._staging_root is None:
            raise NiFiEventError("NiFi staged_file payload requires staging_root to be configured")
        if raw_path is None:
            raise NiFiEventError("NiFi staged payload path is missing")
        candidate = Path(raw_path).resolve()
        if not candidate.is_relative_to(self._staging_root):
            raise NiFiEventError("NiFi staged payload path is outside staging_root")
        if not candidate.is_file():
            raise NiFiEventError("NiFi staged payload file is inaccessible")
        return str(candidate)

    @staticmethod
    def _safe_metadata(event: NiFiEventEnvelope) -> dict[str, Any]:
        safe = dict(event.metadata)
        safe.update(
            {
                "nifi_external_id": event.external_id,
                "nifi_correlation_id": event.correlation_id,
                "nifi_dlq_id": event.dlq_id,
                "nifi_event_timestamp": event.event_timestamp.isoformat()
                if event.event_timestamp is not None
                else None,
                "nifi_payload_type": event.payload.type,
            }
        )
        return {key: value for key, value in safe.items() if value is not None}
