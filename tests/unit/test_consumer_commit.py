"""Unit tests for PipelineJobRepository.commit() behavior."""

from unittest.mock import MagicMock

from services.pipeline.jobs import PipelineJobRepository


def test_commit_delegates_to_connection():
    mock_conn = MagicMock()
    repo = PipelineJobRepository(mock_conn)
    repo.commit()
    mock_conn.commit.assert_called_once()
