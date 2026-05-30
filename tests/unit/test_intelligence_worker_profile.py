"""Unit tests for IntelligenceWorker source-profile resolution path."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from services.intelligence.profile_repository import ProfileRepository
from services.intelligence.worker import IntelligenceWorker


def _make_worker(profile_repo: ProfileRepository | None = None) -> IntelligenceWorker:
    repo = MagicMock()
    repo.get_config.return_value = {}
    llm = MagicMock()
    return IntelligenceWorker(
        repository=repo,
        ollama_client=llm,
        profile_repo=profile_repo,
    )


def _active_profile(source_id: str) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "source_id": source_id,
        "name": "Test Profile",
        "domain_type": "engineering",
        "chunking_strategy": "heading",
        "retrieval_strategy": "hybrid",
        "extraction_strategy": "full_text",
        "status": "active",
        "model_policy_provider_id": None,
        "description": None,
        "config": {},
        "created_by": None,
        "approved_by": None,
        "version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def test_process_document_without_profile_repo_does_not_raise() -> None:
    """When profile_repo is not configured, process_document runs normally."""
    worker = _make_worker(profile_repo=None)
    worker.process_document(uuid4(), "some content", source_id=uuid4())


def test_process_document_no_source_id_skips_profile_lookup() -> None:
    """When source_id is None, get_active_profile is never called."""
    mock_repo = MagicMock(spec=ProfileRepository)
    worker = _make_worker(profile_repo=mock_repo)
    worker.process_document(uuid4(), "content", source_id=None)
    mock_repo.get_active_profile.assert_not_called()


def test_process_document_logs_active_profile(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When an active profile exists, strategy fields are logged at INFO."""
    source_id = uuid4()
    mock_repo = MagicMock(spec=ProfileRepository)
    mock_repo.get_active_profile.return_value = _active_profile(str(source_id))

    worker = _make_worker(profile_repo=mock_repo)

    with caplog.at_level(logging.INFO, logger="services.intelligence.worker"):
        worker.process_document(uuid4(), "content", source_id=source_id)

    mock_repo.get_active_profile.assert_called_once_with(source_id)
    assert "heading" in caplog.text
    assert "hybrid" in caplog.text
    assert "full_text" in caplog.text


def test_process_document_no_active_profile_falls_back_silently() -> None:
    """When get_active_profile returns None, defaults are used without error."""
    mock_repo = MagicMock(spec=ProfileRepository)
    mock_repo.get_active_profile.return_value = None

    worker = _make_worker(profile_repo=mock_repo)
    worker.process_document(uuid4(), "content", source_id=uuid4())

    mock_repo.get_active_profile.assert_called_once()


def test_process_document_profile_lookup_error_does_not_propagate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing get_active_profile is caught, logged as WARNING, and not raised."""
    mock_repo = MagicMock(spec=ProfileRepository)
    mock_repo.get_active_profile.side_effect = RuntimeError("db gone")

    worker = _make_worker(profile_repo=mock_repo)

    with caplog.at_level(logging.WARNING, logger="services.intelligence.worker"):
        worker.process_document(uuid4(), "content", source_id=uuid4())

    assert "Failed to resolve SourceProfile" in caplog.text
