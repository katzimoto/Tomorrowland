from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from services.pipeline.translation_worker import run_translation_once

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeJobRepo:
    def __init__(
        self,
        *,
        job: dict | None = None,
        payload: dict | None = None,
    ) -> None:
        self._job = job
        self._payload = payload
        self.claimed: list[str] = []
        self.stages: list[tuple[UUID, str]] = []
        self.succeeded: list[UUID] = []
        self.retried: list[UUID] = []
        self.dead_lettered: list[UUID] = []
        self.translated_text_updates: list[tuple[UUID, str]] = []
        self.enqueued: list[dict] = []

    def claim_next(self, worker_id: str, job_types: list[str] | None = None) -> dict | None:
        self.claimed.append(worker_id)
        return self._job

    def mark_running_stage(self, job_id: UUID, stage: str) -> None:
        self.stages.append((job_id, stage))

    def mark_succeeded(self, job_id: UUID) -> None:
        self.succeeded.append(job_id)

    def mark_retry(self, job_id: UUID, error: object, *, stage: str = "process") -> None:
        self.retried.append(job_id)

    def mark_dead_letter(self, job_id: UUID, error: object) -> None:
        self.dead_lettered.append(job_id)

    def get_payload(self, document_id: UUID) -> dict | None:
        return self._payload

    def update_translated_text(self, document_id: UUID, translated_text: str) -> None:
        self.translated_text_updates.append((document_id, translated_text))

    def enqueue_document(self, *, document_id: UUID, source_id: UUID, job_type: str) -> UUID:
        self.enqueued.append(
            {"document_id": document_id, "source_id": source_id, "job_type": job_type}
        )
        return uuid4()

    def count_by_status(self) -> dict:
        return {}

    def reap_stale_locks(self) -> int:
        return 0


class _FakeDocRepo:
    def __init__(self, doc: object | None = None) -> None:
        self._doc = doc

    def get_by_id(self, document_id: UUID) -> object | None:
        return self._doc


class _FakeDoc:
    def __init__(
        self, *, document_id: UUID | None = None, source_language: str | None = "en"
    ) -> None:
        self.id = document_id or uuid4()
        self.source_language = source_language


class _FakeTranslator:
    def __init__(self, translated: str = "translated text") -> None:
        self._translated = translated
        self.calls: list[tuple[str, str | None]] = []

    def translate(self, text: str, *, source_lang: str | None = None) -> str:
        self.calls.append((text, source_lang))
        return self._translated


def _make_job(*, document_id: UUID | None = None, source_id: UUID | None = None) -> dict:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "document_id": document_id or uuid4(),
        "source_id": source_id or uuid4(),
        "job_type": "translate_document",
        "attempts": 1,
        "max_attempts": 5,
        "priority": 0,
        "stage": None,
        "last_error": None,
        "run_after": now,
        "locked_by": "translation-worker",
        "locked_at": now,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_false_when_no_job() -> None:
    job_repo = _FakeJobRepo(job=None)
    doc_repo = _FakeDocRepo()
    translator = _FakeTranslator()
    result = run_translation_once(job_repo, doc_repo, translator)
    assert result is False


def test_translates_and_persists_text() -> None:
    document_id = uuid4()
    job = _make_job(document_id=document_id)
    doc = _FakeDoc(source_language="fr")
    payload = {"content_text": "bonjour monde", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    translator = _FakeTranslator(translated="hello world")

    result = run_translation_once(job_repo, doc_repo, translator)

    assert result is True
    assert job_repo.translated_text_updates == [(document_id, "hello world")]
    assert translator.calls == [("bonjour monde", "fr")]
    assert job_repo.succeeded == [job["id"]]


def test_enqueues_index_document_after_success() -> None:
    source_id = uuid4()
    document_id = uuid4()
    job = _make_job(document_id=document_id, source_id=source_id)
    payload = {"content_text": "some text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=_FakeDoc())
    translator = _FakeTranslator()

    run_translation_once(job_repo, doc_repo, translator)

    assert len(job_repo.enqueued) == 1
    assert job_repo.enqueued[0]["job_type"] == "index_document"
    assert job_repo.enqueued[0]["document_id"] == document_id
    assert job_repo.enqueued[0]["source_id"] == source_id


def test_retries_when_document_not_found() -> None:
    job = _make_job()
    job_repo = _FakeJobRepo(job=job, payload=None)
    doc_repo = _FakeDocRepo(doc=None)
    translator = _FakeTranslator()

    result = run_translation_once(job_repo, doc_repo, translator)

    assert result is True
    assert job_repo.retried == [job["id"]]
    assert job_repo.translated_text_updates == []
    assert job_repo.enqueued == []


def test_retries_when_content_text_missing() -> None:
    job = _make_job()
    payload = {"content_text": "", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=_FakeDoc())
    translator = _FakeTranslator()

    result = run_translation_once(job_repo, doc_repo, translator)

    assert result is True
    assert job_repo.retried == [job["id"]]
    assert job_repo.translated_text_updates == []


def test_dead_letters_when_max_attempts_reached() -> None:
    job = _make_job()
    job["attempts"] = 5
    job["max_attempts"] = 5
    payload = {"content_text": "", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=_FakeDoc())
    translator = _FakeTranslator()

    result = run_translation_once(job_repo, doc_repo, translator)

    assert result is True
    assert job_repo.dead_lettered == [job["id"]]
    assert job_repo.retried == []


def test_marks_running_stage_before_work(caplog: pytest.LogCaptureFixture) -> None:
    document_id = uuid4()
    job = _make_job(document_id=document_id)
    payload = {"content_text": "hello", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=_FakeDoc())
    translator = _FakeTranslator()

    run_translation_once(job_repo, doc_repo, translator)

    assert job_repo.stages == [(job["id"], "translate")]


def test_no_enqueue_when_translation_fails() -> None:
    job = _make_job()
    job_repo = _FakeJobRepo(job=job, payload=None)
    doc_repo = _FakeDocRepo(doc=None)
    translator = _FakeTranslator()

    run_translation_once(job_repo, doc_repo, translator)

    assert job_repo.enqueued == []
