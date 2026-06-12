"""Unit tests for parse_worker: attachment cycle/depth guard and publish-failure handling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from services.pipeline.parse_worker import (
    _MAX_ATTACHMENT_NESTING,
    ParseConsumer,
    _attachment_cycle_or_depth_skip,
)

_SHA = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"  # 64 hex


def test_skip_when_attachment_sha_already_in_chain() -> None:
    # The attachment's sha prefix is already encoded in an ancestor → cycle.
    external_id = f"root::attachment::inner.zip::{_SHA[:12]}"
    assert _attachment_cycle_or_depth_skip(external_id, _SHA) is True


def test_no_skip_for_distinct_attachment() -> None:
    external_id = "root::attachment::other.zip::999888777666"
    assert _attachment_cycle_or_depth_skip(external_id, _SHA) is False


def test_skip_when_nesting_depth_exceeded() -> None:
    external_id = "root" + "::attachment::x::aaaaaaaaaaaa" * _MAX_ATTACHMENT_NESTING
    assert _attachment_cycle_or_depth_skip(external_id, _SHA) is True


def test_no_skip_for_shallow_distinct_chain() -> None:
    assert _attachment_cycle_or_depth_skip("root::attachment::x::bbbbbbbbbbbb", _SHA) is False


def test_no_skip_for_root_document() -> None:
    assert _attachment_cycle_or_depth_skip("root-doc-external-id", _SHA) is False


# ---------------------------------------------------------------------------
# Attachment publish-failure surfacing (#697)
# ---------------------------------------------------------------------------


def _make_attachment(filename: str = "child.pdf", mime_type: str = "application/pdf") -> MagicMock:
    att = MagicMock()
    att.filename = filename
    att.mime_type = mime_type
    att.data = b"PDF content"
    return att


def _make_parse_consumer(
    *,
    doc_external_id: str = "root-doc",
    doc_mime_type: str = "text/plain",
    publish_parse_raises: Exception | None = None,
) -> tuple[ParseConsumer, MagicMock, MagicMock, MagicMock]:
    """Return (consumer, doc_repo, job_repo, publisher) with mocked dependencies."""
    doc_id = uuid4()
    source_id = uuid4()
    job_id = uuid4()
    child_doc_id = uuid4()
    child_job_id = uuid4()

    doc = SimpleNamespace(
        id=doc_id,
        source_id=source_id,
        path=None,
        external_id=doc_external_id,
        source="folder",
        mime_type=doc_mime_type,
        source_language="en",
        title="Parent",
    )
    child_doc = SimpleNamespace(id=child_doc_id)

    doc_repo = MagicMock()
    doc_repo.get_by_id.return_value = doc
    doc_repo.create.return_value = child_doc
    doc_repo._connection = MagicMock()

    job_repo = MagicMock()
    job_repo.get_payload.return_value = {}
    job_repo.enqueue_document.return_value = child_job_id

    publisher = MagicMock()
    publisher.publish_translate.return_value = None
    if publish_parse_raises is not None:
        publisher.publish_parse.side_effect = publish_parse_raises
    else:
        publisher.publish_parse.return_value = None

    extractor = MagicMock()
    extractor.has_extractor.return_value = True

    consumer = ParseConsumer(
        rabbit=MagicMock(),
        job_repo=job_repo,
        doc_repo=doc_repo,
        publisher=publisher,
        extractor=extractor,
    )
    return consumer, doc_repo, job_repo, publisher, job_id, source_id, child_job_id


class TestAttachmentPublishFailure:
    def test_publish_failure_marks_child_dead_letter_via_job_repo(self) -> None:
        err = RuntimeError("rabbit connection lost")
        consumer, doc_repo, job_repo, publisher, job_id, source_id, child_job_id = (
            _make_parse_consumer(publish_parse_raises=err)
        )

        # Route attachments through the extractor MagicMock
        att = _make_attachment()
        fake_result = SimpleNamespace(
            text="",
            location_segments=[],
            attachments=[att],
        )
        with patch.object(consumer._extractor, "extract", return_value=fake_result):
            doc = doc_repo.get_by_id.return_value
            doc.path = "/tmp/parent.txt"
            consumer.handle_message(
                job_id=job_id,
                document_id=doc.id,
                source_id=source_id,
                attempt=1,
                correlation_id="test",
            )

        job_repo.mark_running_stage.assert_any_call(child_job_id, "parse")
        job_repo.mark_dead_letter.assert_called_once()
        dead_letter_args = job_repo.mark_dead_letter.call_args
        assert dead_letter_args[0][0] == child_job_id
        assert isinstance(dead_letter_args[0][1], RuntimeError)
        job_repo.commit.assert_called()

    def test_publish_failure_parent_job_continues(self) -> None:
        err = RuntimeError("rabbit connection lost")
        consumer, doc_repo, job_repo, publisher, job_id, source_id, child_job_id = (
            _make_parse_consumer(publish_parse_raises=err)
        )

        att = _make_attachment()
        fake_result = SimpleNamespace(text="some text", location_segments=[], attachments=[att])
        with patch.object(consumer._extractor, "extract", return_value=fake_result):
            doc = doc_repo.get_by_id.return_value
            doc.path = "/tmp/parent.txt"
            # Should not raise — attachment failure is best-effort
            consumer.handle_message(
                job_id=job_id,
                document_id=doc.id,
                source_id=source_id,
                attempt=1,
                correlation_id="test",
            )

        # Parent publish_translate still called
        publisher.publish_translate.assert_called_once()
