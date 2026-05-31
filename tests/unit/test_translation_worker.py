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
            {
                "document_id": document_id,
                "source_id": source_id,
                "job_type": job_type,
            }
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


class _FakePublisher:
    def __init__(self) -> None:
        self.embed_calls: list[dict] = []
        self.index_calls: list[dict] = []

    def publish_embed(self, **kwargs: object) -> None:
        self.embed_calls.append(dict(kwargs))

    def publish_index(self, **kwargs: object) -> None:
        self.index_calls.append(dict(kwargs))


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


def test_publishes_downstream_after_success() -> None:
    """After a successful translation, embed + index messages are published."""
    source_id = uuid4()
    document_id = uuid4()
    job_id = uuid4()  # not job["id"] — translation_worker creates a new UUID for job_id
    job = _make_job(document_id=document_id, source_id=source_id)
    # Override the job id so we can assert on it
    job["id"] = job_id
    payload = {"content_text": "some text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=_FakeDoc())
    translator = _FakeTranslator()
    publisher = _FakePublisher()

    run_translation_once(job_repo, doc_repo, translator, publisher=publisher)

    # Must NOT enqueue orphan database jobs
    assert job_repo.enqueued == []

    # Must publish embed
    assert len(publisher.embed_calls) == 1
    embed = publisher.embed_calls[0]
    assert embed["job_id"] == job_id
    assert embed["document_id"] == document_id
    assert embed["source_id"] == source_id
    assert embed["content_text"] == "some text"
    assert embed["translated_text"] == "translated text"

    # Must publish index
    assert len(publisher.index_calls) == 1
    index = publisher.index_calls[0]
    assert index["job_id"] == job_id
    assert index["document_id"] == document_id
    assert index["source_id"] == source_id
    assert index["content_text"] == "some text"
    assert index["translated_text"] == "translated text"


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


def test_skips_gracefully_when_content_text_missing() -> None:
    """Empty content_text must be handled gracefully (not retried / dead-lettered).

    Documents with no extractable text (e.g. scanned PDFs without OCR) used to
    cause the job to be retried up to max_attempts times and then dead-lettered.
    After the fix the job succeeds immediately and the downstream pipeline is
    triggered via the publisher.
    """
    job = _make_job()
    payload = {"content_text": "", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=_FakeDoc())
    translator = _FakeTranslator()
    publisher = _FakePublisher()

    result = run_translation_once(job_repo, doc_repo, translator, publisher=publisher)

    assert result is True
    # Must NOT retry or dead-letter
    assert job_repo.retried == []
    assert job_repo.dead_lettered == []
    # Must have stored empty translated text so index worker has a payload row
    assert job_repo.translated_text_updates == [(job["document_id"], "")]
    # Must have succeeded
    assert job_repo.succeeded == [job["id"]]
    # Must NOT enqueue orphan database jobs
    assert job_repo.enqueued == []
    # Must publish downstream with empty content/translated text
    assert len(publisher.embed_calls) == 1
    assert publisher.embed_calls[0]["content_text"] == ""
    assert publisher.embed_calls[0]["translated_text"] == ""
    assert len(publisher.index_calls) == 1
    assert publisher.index_calls[0]["content_text"] == ""
    assert publisher.index_calls[0]["translated_text"] == ""


def test_dead_letters_only_when_translation_itself_fails() -> None:
    """Dead-lettering must only happen when translation raises, not for empty text."""
    job = _make_job()
    job["attempts"] = 5
    job["max_attempts"] = 5
    # Give it real content so it tries to translate
    payload = {"content_text": "some content", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=_FakeDoc())

    class _BrokenTranslator:
        def translate(self, text: str, source_lang: str | None) -> str:
            raise RuntimeError("LibreTranslate unreachable")

    result = run_translation_once(job_repo, doc_repo, _BrokenTranslator())

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


def test_no_downstream_when_translation_fails() -> None:
    """No downstream messages are published when translation itself fails."""
    job = _make_job()
    job_repo = _FakeJobRepo(job=job, payload=None)
    doc_repo = _FakeDocRepo(doc=None)
    translator = _FakeTranslator()
    publisher = _FakePublisher()

    run_translation_once(job_repo, doc_repo, translator, publisher=publisher)

    assert job_repo.enqueued == []
    assert publisher.embed_calls == []
    assert publisher.index_calls == []


def test_succeeds_without_publisher() -> None:
    """When no publisher is provided, translation succeeds and logs a warning.

    This preserves backward compatibility: the translated text is persisted
    even if RabbitMQ is not available.
    """
    job = _make_job()
    payload = {"content_text": "some text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=_FakeDoc())
    translator = _FakeTranslator(translated="translated text")

    # No publisher passed — should succeed without publishing
    result = run_translation_once(job_repo, doc_repo, translator)

    assert result is True
    assert job_repo.succeeded == [job["id"]]
    assert job_repo.enqueued == []
    assert job_repo.translated_text_updates == [(job["document_id"], "translated text")]
