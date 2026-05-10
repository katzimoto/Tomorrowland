"""Source connector package."""

from __future__ import annotations

from services.connectors.atlassian import ConfluenceConnector, JiraConnector
from services.connectors.base import ConnectorDocument, ConnectorField, SourceConnector
from services.connectors.factory import build_connector, connector_types
from services.connectors.folder import FolderConnector
from services.connectors.nifi import NiFiConnector
from services.connectors.smb import SmbConnector

__all__ = [
    "ConfluenceConnector",
    "ConnectorDocument",
    "ConnectorField",
    "FolderConnector",
    "JiraConnector",
    "NiFiConnector",
    "SmbConnector",
    "SourceConnector",
    "build_connector",
    "connector_types",
]
