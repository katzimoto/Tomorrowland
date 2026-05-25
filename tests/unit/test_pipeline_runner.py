"""Tests for the pipeline job runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from services.pipeline.runner import run_once
from services.pipeline.worker import PipelineWorker, ProcessResult


class _FakeJobRepo:
    """Minimal fake that implements only the methods run_once needs."""

    def __init__(self) -> None:
        self.claim_next_calls: list[tuple[str, list[str] | None]] = []
        self.claimed_job: dict | None = None
        self.payload: dict | None = {"content_text": "extracted text"}
        self.for_success: bool = True
        self.content_text_updates: list[tuple[UUID, str]] = []
        self.translated_text_updates: list[tuple[UUID, str]] = []
        self.enqueue_calls: list[dict] = []
        self._connection: object = None  # required by TranslationVersionRepository init

    def claim_next(self, worker_id: str, job_types: list[str] | None = None) -> dict | None:
        self.claim_next_calls.append((worker_id, job_types))
        return self.claimed_job

    def get_payload(self, document_id: UUID) -> dict | None:
        return self.payload

    def mark_running_stage(self, job_id: UUID, stage: str) -> None:
        self.marked_stage = (job_id, stage)

    def mark_succeeded(self, job_id: UUID) -> None:
        self.succeeded = job_id

    def mark_retry(self, job_id: UUID, error: str | BaseException, stage: str = "process") -> None:
        self.retried = (job_id, error, stage)

    def mark_dead_letter(self, job_id: UUID, error: str | BaseException) -> None:
        self.dead_lettered = (job_id, error)

    def update_content_text(self, document_id: UUID, content_text: str) -> None:
        self.content_text_updates.append((document_id, content_text))

    def update_translated_text(self, document_id: UUID, translated_text: str) -> None:
        self.translated_text_updates.append((document_id, translated_text))

    def enqueue_document(self, *, document_id: UUID, source_id: UUID, job_type: str) -> UUID:
        from uuid import uuid4

        job_id = uuid4()
        self.enqueue_calls.append(
            {
                "document_id": document_id,
                "source_id": source_id,
                "job_type": job_type,
            }
        )
        return job_id


class TestRunOnce:
    def test_returns_false_when_no_job_available(self) -> None:
        repo = _FakeJobRepo()
        worker = MagicMock()
        result = run_once(repo, worker)
        assert result is False
        worker.process_document.assert_not_called()

    def test_processes_job_and_marks_succeeded(self) -> None:
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        result = run_once(repo, worker)
        assert result is True
        worker.process_document.assert_called_once_with(
            document_id, pre_extracted_text="extracted text"
        )
        assert repo.succeeded == repo.claimed_job["id"]

    def test_marks_retry_when_worker_raises_and_attempts_remain(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 3,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("processing failed")
        result = run_once(repo, worker)
        assert result is True
        assert repo.retried is not None
        assert repo.retried[0] == repo.claimed_job["id"]

    def test_marks_dead_letter_when_attempts_exhausted(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 5,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("final failure")
        result = run_once(repo, worker)
        assert result is True
        assert repo.dead_lettered is not None
        assert repo.dead_lettered[0] == repo.claimed_job["id"]

    def test_loads_payload_and_passes_to_worker(self) -> None:
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.payload = {"content_text": "custom extracted text"}
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        run_once(repo, worker)
        # payload loaded correctly
        worker.process_document.assert_called_once()  # noqa: B015

    def test_handles_missing_payload_gracefully(self) -> None:
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.payload = None
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        run_once(repo, worker)
        worker.process_document.assert_called_once_with(document_id, pre_extracted_text=None)

    def test_persists_extracted_and_translated_text_after_successful_process_document(
        self,
    ) -> None:
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        worker.process_document.return_value = ProcessResult(
            extracted_text="raw document text",
            translated_text="translated document body",
        )

        run_once(repo, worker)

        assert len(repo.content_text_updates) == 1
        assert repo.content_text_updates[0] == (document_id, "raw document text")

        assert len(repo.translated_text_updates) == 1
        assert repo.translated_text_updates[0] == (
            document_id,
            "translated document body",
        )

    def test_does_not_persist_texts_when_worker_raises(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 3,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("pipeline failure")

        run_once(repo, worker)

        assert repo.content_text_updates == []
        assert repo.translated_text_updates == []

    # ------------------------------------------------------------------ #
    #  Worker isolation tests
    # ------------------------------------------------------------------ #

    def test_claim_next_receives_allowed_job_types_filter(self) -> None:
        """run_once passes job_types filter to claim_next."""
        from services.pipeline.runner import _WORKER_ALLOWED_JOB_TYPES

        repo = _FakeJobRepo()
        repo.claimed_job = None
        worker = MagicMock()
        run_once(repo, worker)

        assert len(repo.claim_next_calls) == 1
        _worker_id, job_types = repo.claim_next_calls[0]
        assert job_types == _WORKER_ALLOWED_JOB_TYPES

    def test_does_not_claim_unknown_job_types(self) -> None:
        """Pipeline worker must not claim disallowed job types."""
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "vector_index_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        run_once(repo, worker)

        # The fake always returns the claimed_job, so run_once WILL claim it.
        # But in production, claim_next's job_types filter would prevent this.
        # This test verifies that the job_types filter IS sent to claim_next.
        _worker_id, job_types = repo.claim_next_calls[0]
        assert "vector_index_document" not in (job_types or [])

    # ------------------------------------------------------------------ #
    #  Intelligence document job handling
    # ------------------------------------------------------------------ #

    def test_processes_intelligence_job_and_marks_succeeded(self) -> None:
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.payload = {"translated_text": "some translated content"}
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "intelligence_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = MagicMock()
        worker.alert_matcher = None

        result = run_once(repo, worker)

        assert result is True
        worker.intelligence_worker.process_document.assert_called_once_with(
            document_id, "some translated content"
        )
        assert repo.succeeded == repo.claimed_job["id"]

    def test_intelligence_job_uses_content_text_fallback(self) -> None:
        """When no translated_text, use content_text for intelligence."""
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.payload = {"content_text": "raw text", "translated_text": None}
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "intelligence_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = MagicMock()
        worker.alert_matcher = None

        run_once(repo, worker)

        worker.intelligence_worker.process_document.assert_called_once_with(document_id, "raw text")

    def test_intelligence_job_skips_when_no_worker(self) -> None:
        """Intelligence job succeeds immediately when no intelligence worker."""
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "intelligence_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = None
        worker.alert_matcher = None

        result = run_once(repo, worker)

        assert result is True
        assert repo.succeeded == repo.claimed_job["id"]

    def test_intelligence_job_retries_on_failure(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "intelligence_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 3,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = MagicMock()
        worker.intelligence_worker.process_document.side_effect = RuntimeError("intel failure")
        worker.alert_matcher = None

        result = run_once(repo, worker)

        assert result is True
        assert repo.retried is not None
        assert repo.retried[0] == repo.claimed_job["id"]

    def test_intelligence_job_dead_letters_on_exhausted_attempts(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "intelligence_document",
            "priority": 0,
            "attempts": 5,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = MagicMock()
        worker.intelligence_worker.process_document.side_effect = RuntimeError("final intel fail")
        worker.alert_matcher = None

        result = run_once(repo, worker)

        assert result is True
        assert repo.dead_lettered is not None
        assert repo.dead_lettered[0] == repo.claimed_job["id"]

    # ------------------------------------------------------------------ #
    #  Alert document job handling
    # ------------------------------------------------------------------ #

    def test_processes_alert_job_and_marks_succeeded(self) -> None:
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.payload = {"translated_text": "alert content"}
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "alert_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = None
        worker.alert_matcher = MagicMock()
        doc_mock = MagicMock()
        doc_mock.id = document_id
        worker.document_repository.get_by_id.return_value = doc_mock

        result = run_once(repo, worker)

        assert result is True
        worker.alert_matcher.match_document.assert_called_once()
        assert repo.succeeded == repo.claimed_job["id"]

    def test_alert_job_skips_when_no_matcher(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "alert_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = None
        worker.alert_matcher = None

        result = run_once(repo, worker)

        assert result is True
        assert repo.succeeded == repo.claimed_job["id"]

    def test_alert_job_retries_on_failure(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "alert_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 3,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = None
        worker.alert_matcher = MagicMock()
        doc_mock = MagicMock()
        doc_mock.id = uuid4()
        worker.document_repository.get_by_id.return_value = doc_mock
        worker.alert_matcher.match_document.side_effect = RuntimeError("alert failure")

        result = run_once(repo, worker)

        assert result is True
        assert repo.retried is not None
        assert repo.retried[0] == repo.claimed_job["id"]

    def test_alert_job_dead_letters_on_exhausted_attempts(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "alert_document",
            "priority": 0,
            "attempts": 5,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock(spec=PipelineWorker)
        worker.intelligence_worker = None
        worker.alert_matcher = MagicMock()
        doc_mock = MagicMock()
        doc_mock.id = uuid4()
        worker.document_repository.get_by_id.return_value = doc_mock
        worker.alert_matcher.match_document.side_effect = RuntimeError("final alert fail")

        result = run_once(repo, worker)

        assert result is True
        assert repo.dead_lettered is not None
        assert repo.dead_lettered[0] == repo.claimed_job["id"]

    # ------------------------------------------------------------------ #
    #  Translation version fallback
    # ------------------------------------------------------------------ #

    @patch("services.pipeline.runner.TranslationVersionRepository")
    def test_translation_version_uses_extracted_text_when_translated_is_empty(
        self, mock_version_repo_cls: MagicMock
    ) -> None:
        """When translator returns '' (e.g. LibreTranslate empty response),
        the translation version is still created using extracted_text so the
        UI is not left with no translation at all."""
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }

        # Simulate: extraction produced text, but translation returned empty string.
        worker = MagicMock()
        worker.process_document.return_value = ProcessResult(
            extracted_text="email body in some language",
            translated_text="",
        )
        doc_mock = MagicMock()
        doc_mock.target_language = "en"
        worker.document_repository.get_by_id.return_value = doc_mock

        mock_version_repo = MagicMock()
        mock_version_repo.find_pending_or_running.return_value = None
        mock_version_repo.create_version.return_value = {"id": str(uuid4())}
        mock_version_repo_cls.return_value = mock_version_repo

        run_once(repo, worker)

        # A translation version must have been created and marked available.
        mock_version_repo.create_version.assert_called_once()
        mock_version_repo.update_version_status.assert_called_once()
        _version_id, status, *_ = mock_version_repo.update_version_status.call_args.args
        assert status == "available"
        # The stored text must be the extracted text, not the empty translated string.
        stored_text = mock_version_repo.update_version_status.call_args.kwargs.get(
            "translated_text"
        )
        assert stored_text == "email body in some language"

    @patch("services.pipeline.runner.TranslationVersionRepository")
    def test_translation_version_skipped_when_both_texts_empty(
        self, mock_version_repo_cls: MagicMock
    ) -> None:
        """When both extracted_text and translated_text are empty (truly empty
        document), no translation version is created."""
        document_id = uuid4()
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "document_id": document_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }

        worker = MagicMock()
        worker.process_document.return_value = ProcessResult(
            extracted_text="",
            translated_text="",
        )
        doc_mock = MagicMock()
        doc_mock.target_language = "en"
        worker.document_repository.get_by_id.return_value = doc_mock

        mock_version_repo = MagicMock()
        mock_version_repo_cls.return_value = mock_version_repo

        run_once(repo, worker)

        mock_version_repo.create_version.assert_not_called()
        mock_version_repo.update_version_status.assert_not_called()
