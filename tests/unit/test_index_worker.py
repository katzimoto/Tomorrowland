from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from services.pipeline.index_worker import run_index_once

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeJobRepo:
    def __init__(self, *, job: dict | None = None, payload: dict | None = None) -> None:
        self._job = job
        self._payload = payload
        self.stages: list[tuple[UUID, str]] = []
        self.succeeded: list[UUID] = []
        self.retried: list[UUID] = []
        self.dead_lettered: list[UUID] = []
        self.enqueued: list[dict] = []

    def claim_next(self, worker_id: str, job_types: list[str] | None = None) -> dict | None:
        return self._job

    def mark_running_stage(self, job_id: UUID, stage: str) -> None:
        self.stages.append((job_id, stage))

    def mark_succeeded(self, job_id: UUID) -> None:
        self.succeeded.append(job_id)

    def mark_retry(self, job_id: UUID, error: object, *, stage: str = "process") -> None:
        self.retried.append(job_id)

    def mark_dead_letter(self, job_id: UUID, error: object) -> None:
        self.dead_lettered.append(job_id)

    def get_payload(self, doc_id: UUID) -> dict | None:
        return self._payload

    def enqueue_document(self, *, doc_id: UUID, source_id: UUID, job_type: str) -> UUID:
        self.enqueued.append({"doc_id": doc_id, "source_id": source_id, "job_type": job_type})
        return uuid4()

    def count_by_status(self) -> dict:
        return {}

    def reap_stale_locks(self) -> int:
        return 0


class _FakeDoc:
    def __init__(
        self,
        *,
        doc_id: UUID | None = None,
        source_id: UUID | None = None,
        path: str | None = None,
        title: str | None = "Test document",
    ) -> None:
        self.id = doc_id or uuid4()
        self.source_id = source_id or uuid4()
        self.path = path
        self.title = title
        self.metadata: dict = {}


class _FakeDocRepo:
    def __init__(self, doc: _FakeDoc | None = None, group_ids: list[UUID] | None = None) -> None:
        self._doc = doc
        self._group_ids = group_ids or []
        self.indexed_updates: list[tuple[UUID, str, str | None]] = []
        self.status_updates: list[tuple[UUID, str]] = []

    def get_by_id(self, doc_id: UUID) -> _FakeDoc | None:
        return self._doc

    def source_group_ids(self, source_id: UUID) -> list[UUID]:
        return self._group_ids

    def update_indexed(self, doc_id: UUID, status: str, translation_quality: str | None) -> None:
        self.indexed_updates.append((doc_id, status, translation_quality))

    def update_status(self, doc_id: UUID, status: str) -> None:
        self.status_updates.append((doc_id, status))


class _FakeElasticsearch:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    def index_document(self, doc_id: str, body: dict) -> None:
        self.calls.append((doc_id, body))
        if self.fail:
            raise RuntimeError("elasticsearch_unavailable")


def _make_job(*, doc_id: UUID | None = None, source_id: UUID | None = None) -> dict:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "doc_id": doc_id or uuid4(),
        "source_id": source_id or uuid4(),
        "job_type": "index_document",
        "attempts": 1,
        "max_attempts": 5,
        "priority": 0,
        "stage": None,
        "last_error": None,
        "run_after": now,
        "locked_by": "index-worker",
        "locked_at": now,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_false_when_no_job() -> None:
    job_repo = _FakeJobRepo(job=None)
    doc_repo = _FakeDocRepo()
    es = _FakeElasticsearch()
    assert run_index_once(job_repo, doc_repo, es) is False


def test_indexes_document_into_elasticsearch() -> None:
    group_id = uuid4()
    doc_id = uuid4()
    source_id = uuid4()
    job = _make_job(doc_id=doc_id, source_id=source_id)
    doc = _FakeDoc(doc_id=doc_id, source_id=source_id, title="My Doc")
    payload = {"content_text": "original text", "translated_text": "english text"}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc, group_ids=[group_id])
    es = _FakeElasticsearch()

    result = run_index_once(job_repo, doc_repo, es)

    assert result is True
    assert len(es.calls) == 1
    indexed_id, indexed_body = es.calls[0]
    assert indexed_id == str(doc_id)
    assert indexed_body["content_original"] == "original text"
    assert indexed_body["content_english"] == "english text"
    assert indexed_body["allowed_group_ids"] == [str(group_id)]
    assert indexed_body["title"] == "My Doc"


def test_marks_indexed_after_success() -> None:
    doc_id = uuid4()
    source_id = uuid4()
    job = _make_job(doc_id=doc_id, source_id=source_id)
    doc = _FakeDoc(doc_id=doc_id, source_id=source_id)
    payload = {"content_text": "hello", "translated_text": "hello translated"}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch()

    run_index_once(job_repo, doc_repo, es)

    assert doc_repo.indexed_updates == [(doc_id, "indexed", "fast")]
    assert job_repo.succeeded == [job["id"]]


def test_translation_quality_none_when_text_unchanged() -> None:
    doc_id = uuid4()
    job = _make_job(doc_id=doc_id)
    doc = _FakeDoc(doc_id=doc_id)
    payload = {"content_text": "same text", "translated_text": "same text"}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch()

    run_index_once(job_repo, doc_repo, es)

    assert doc_repo.indexed_updates[0][2] is None


def test_content_english_falls_back_to_original_when_no_translated_text() -> None:
    doc_id = uuid4()
    job = _make_job(doc_id=doc_id)
    doc = _FakeDoc(doc_id=doc_id)
    payload = {"content_text": "raw content", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch()

    run_index_once(job_repo, doc_repo, es)

    _, body = es.calls[0]
    assert body["content_original"] == "raw content"
    assert body["content_english"] == "raw content"


def test_enqueues_vector_job_after_success() -> None:
    source_id = uuid4()
    doc_id = uuid4()
    job = _make_job(doc_id=doc_id, source_id=source_id)
    doc = _FakeDoc(doc_id=doc_id, source_id=source_id)
    payload = {"content_text": "text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch()

    run_index_once(job_repo, doc_repo, es)

    assert len(job_repo.enqueued) == 1
    assert job_repo.enqueued[0]["job_type"] == "vector_index_document"
    assert job_repo.enqueued[0]["doc_id"] == doc_id
    assert job_repo.enqueued[0]["source_id"] == source_id


def test_marks_failed_and_retries_when_elasticsearch_raises() -> None:
    doc_id = uuid4()
    job = _make_job(doc_id=doc_id)
    doc = _FakeDoc(doc_id=doc_id)
    payload = {"content_text": "text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch(fail=True)

    result = run_index_once(job_repo, doc_repo, es)

    assert result is True
    assert doc_repo.status_updates == [(doc_id, "failed")]
    assert job_repo.retried == [job["id"]]
    assert job_repo.enqueued == []
    assert doc_repo.indexed_updates == []


def test_dead_letters_when_max_attempts_reached() -> None:
    doc_id = uuid4()
    job = _make_job(doc_id=doc_id)
    job["attempts"] = 5
    job["max_attempts"] = 5
    doc = _FakeDoc(doc_id=doc_id)
    payload = {"content_text": "text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch(fail=True)

    run_index_once(job_repo, doc_repo, es)

    assert job_repo.dead_lettered == [job["id"]]
    assert job_repo.retried == []


def test_filename_fallback_when_path_is_none() -> None:
    doc_id = uuid4()
    job = _make_job(doc_id=doc_id)
    doc = _FakeDoc(doc_id=doc_id, path=None, title="My Title")
    payload = {"content_text": "text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch()

    run_index_once(job_repo, doc_repo, es)

    _, body = es.calls[0]
    assert body["filename"] == "My Title"
    assert body["path"] == ""


def test_filename_extracted_from_path() -> None:
    doc_id = uuid4()
    job = _make_job(doc_id=doc_id)
    doc = _FakeDoc(doc_id=doc_id, path="/data/ingest/report.pdf")
    payload = {"content_text": "text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch()

    run_index_once(job_repo, doc_repo, es)

    _, body = es.calls[0]
    assert body["filename"] == "report.pdf"
    assert body["path"] == "/data/ingest/report.pdf"


def test_retries_when_document_not_found() -> None:
    job = _make_job()
    job_repo = _FakeJobRepo(job=job, payload=None)
    doc_repo = _FakeDocRepo(doc=None)
    es = _FakeElasticsearch()

    result = run_index_once(job_repo, doc_repo, es)

    assert result is True
    assert job_repo.retried == [job["id"]]
    assert es.calls == []


def test_marks_running_stage_before_work() -> None:
    doc_id = uuid4()
    job = _make_job(doc_id=doc_id)
    doc = _FakeDoc(doc_id=doc_id)
    payload = {"content_text": "text", "translated_text": None}
    job_repo = _FakeJobRepo(job=job, payload=payload)
    doc_repo = _FakeDocRepo(doc=doc)
    es = _FakeElasticsearch()

    run_index_once(job_repo, doc_repo, es)

    assert job_repo.stages == [(job["id"], "index")]
