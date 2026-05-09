"""Build the correct SourceConnector from a DB source row."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, cast

from sqlalchemy.engine import RowMapping

from services.connectors.base import SourceConnector
from services.connectors.folder import FolderConnector
from services.connectors.nifi import NiFiConnector

# Values are connector classes; typed as Any so mypy doesn't reject classmethod
# calls and constructor calls on a bare `type` without a known signature.
_REGISTRY: dict[str, Any] = {
    "folder": FolderConnector,
    "nifi": NiFiConnector,
}


def connector_types() -> list[dict[str, Any]]:
    """Return field metadata for all registered connector types.

    The result drives the admin UI form — each type describes the config
    fields it requires, including which are sensitive (passwords/tokens).
    """
    return [
        {
            "type": key,
            "label": cls.__name__.replace("Connector", ""),
            "fields": [asdict(f) for f in cls.fields()],
        }
        for key, cls in _REGISTRY.items()
    ]


def build_connector(source_row: RowMapping) -> SourceConnector:
    """Return a connector for *source_row*.

    Reads ``source_row["type"]`` and ``source_row["config"]``.
    Raises ``ValueError`` for unknown or misconfigured types.
    """
    source_type = str(source_row["type"])
    config = _parse_config(source_row.get("config"))

    cls = _REGISTRY.get(source_type)
    if cls is None:
        raise ValueError(f"Unknown source type: {source_type!r}")

    if source_type == "folder":
        path = source_row.get("path") or config.get("path") or ""
        if not path:
            raise ValueError("Source has no path configured")
        return FolderConnector(path)

    return cast("SourceConnector", cls(config))


def _parse_config(raw: Any) -> dict[str, Any]:
    """Normalise the config column value to a dict.

    SQLite returns JSON columns as strings; PostgreSQL returns native dicts.
    """
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    if isinstance(raw, dict):
        return raw
    return {}
