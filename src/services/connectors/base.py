"""Connector protocol and shared document dataclass."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ConnectorField:
    """Describes one config field required by a connector type.

    ``sensitive=True`` signals that the value should be masked in the UI
    (rendered as ``<input type="password">``).
    """

    key: str
    label: str
    required: bool = True
    sensitive: bool = False
    placeholder: str = ""


@dataclass(frozen=True, slots=True)
class ConnectorDocument:
    """Normalised document returned by any SourceConnector.

    File-based connectors set *path* and leave *text_content* as None.
    API/network connectors set *text_content* and leave *path* as None.
    """

    external_id: str
    title: str
    mime_type: str
    sha256: str | None
    source_language: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    path: str | None = None
    text_content: str | None = None


class SourceConnector(Protocol):
    """Protocol satisfied by every concrete source connector."""

    @classmethod
    def fields(cls) -> list[ConnectorField]:
        """Return the config field schema for this connector type."""
        ...

    def validate(self) -> None:
        """Raise ValueError if the connector is misconfigured."""
        ...

    def fetch_documents(self) -> Iterator[ConnectorDocument]:
        """Yield all documents available from this source."""
        ...
