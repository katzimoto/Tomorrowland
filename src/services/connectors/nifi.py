"""NiFi connector stub."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from services.connectors.base import ConnectorDocument, ConnectorField


class NiFiConnector:
    """Pull documents from a NiFi flow (not yet implemented).

    Expected config keys: ``base_url``, ``flow_id``, ``api_token``.
    """

    @classmethod
    def fields(cls) -> list[ConnectorField]:
        return [
            ConnectorField(
                key="base_url",
                label="NiFi base URL",
                placeholder="http://nifi:8080",
            ),
            ConnectorField(key="flow_id", label="Flow ID"),
            ConnectorField(key="api_token", label="API token", sensitive=True),
        ]

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def validate(self) -> None:
        pass

    def fetch_documents(self) -> Iterator[ConnectorDocument]:
        raise NotImplementedError(
            "NiFi connector is not yet implemented. "
            "Implement fetch_documents() to poll the NiFi REST API "
            "using config keys: base_url, flow_id, api_token."
        )
