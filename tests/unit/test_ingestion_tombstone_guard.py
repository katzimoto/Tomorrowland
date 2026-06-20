"""Guards on full_resync tombstoning to prevent mass data loss.

A full_resync deletes (tombstones + removes from search) every document not
seen during the run. These tests verify the safety guards in
``_handle_tombstones`` so a transient empty/partial fetch cannot wipe a source.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from services.api.routers.admin.ingestion import _handle_tombstones


def _results(**overrides: int) -> dict[str, int]:
    base = {
        "discovered": 0,
        "created": 0,
        "skipped": 0,
        "enqueued": 0,
        "failed_discovery": 0,
        "failed_enqueue": 0,
        "unchanged": 0,
    }
    base.update(overrides)
    return base


@patch("services.api.routers.admin.ingestion.build_index_cleanup")
@patch("services.api.routers.admin.ingestion.tombstone_missing_documents")
def test_clean_full_resync_tombstones(mock_tombstone: MagicMock, _cleanup: MagicMock) -> None:
    _handle_tombstones(
        "full_resync", MagicMock(), uuid4(), {"a", "b"}, _results(discovered=2), MagicMock()
    )
    mock_tombstone.assert_called_once()


@patch("services.api.routers.admin.ingestion.build_index_cleanup")
@patch("services.api.routers.admin.ingestion.tombstone_missing_documents")
def test_empty_seen_set_skips_tombstone(mock_tombstone: MagicMock, _cleanup: MagicMock) -> None:
    _handle_tombstones("full_resync", MagicMock(), uuid4(), set(), _results(), MagicMock())
    mock_tombstone.assert_not_called()


@patch("services.api.routers.admin.ingestion.build_index_cleanup")
@patch("services.api.routers.admin.ingestion.tombstone_missing_documents")
def test_discovery_failure_skips_tombstone(mock_tombstone: MagicMock, _cleanup: MagicMock) -> None:
    _handle_tombstones(
        "full_resync", MagicMock(), uuid4(), {"a"}, _results(failed_discovery=1), MagicMock()
    )
    mock_tombstone.assert_not_called()


@patch("services.api.routers.admin.ingestion.build_index_cleanup")
@patch("services.api.routers.admin.ingestion.tombstone_missing_documents")
def test_incremental_mode_skips_tombstone(mock_tombstone: MagicMock, _cleanup: MagicMock) -> None:
    _handle_tombstones("incremental", MagicMock(), uuid4(), {"a"}, _results(), MagicMock())
    mock_tombstone.assert_not_called()
