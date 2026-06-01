import json
from unittest.mock import MagicMock
from uuid import uuid4

from services.pipeline.consumer_base import BaseConsumer


class SucceedingConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def handle_message(
        self,
        job_id,
        document_id,
        source_id,
        attempt,
        correlation_id,
        content_text: str = "",
        translated_text: str = "",
    ):
        pass


class FailingConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def handle_message(
        self,
        job_id,
        document_id,
        source_id,
        attempt,
        correlation_id,
        content_text: str = "",
        translated_text: str = "",
    ):
        raise RuntimeError("something broke")


def _make_delivery(job_id=None, attempt=1):
    body = json.dumps(
        {
            "job_id": str(job_id or uuid4()),
            "document_id": str(uuid4()),
            "source_id": str(uuid4()),
            "attempt": attempt,
            "pipeline_version": "v1",
        }
    ).encode()
    method = MagicMock()
    method.delivery_tag = 42
    return MagicMock(), method, MagicMock(), body


def test_success_acks_message():
    consumer = SucceedingConsumer.__new__(SucceedingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._jobs_processed = 0

    ch, method, props, body = _make_delivery()
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_ack.assert_called_once_with(delivery_tag=42)
    consumer._channel.basic_nack.assert_not_called()


def test_failure_republishes_to_retry_when_attempts_remaining():
    consumer = FailingConsumer.__new__(FailingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._connection = None
    consumer._job_repo.get_max_attempts.return_value = 5
    consumer._job_repo.get_payload.return_value = None
    consumer._jobs_processed = 0

    ch, method, props, body = _make_delivery(attempt=1)
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_publish.assert_called_once()
    consumer._channel.basic_ack.assert_called_once_with(delivery_tag=42)
    consumer._job_repo.mark_retry.assert_called_once()


def test_failure_dead_letters_when_attempts_exhausted():
    consumer = FailingConsumer.__new__(FailingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._job_repo.get_max_attempts.return_value = 3
    consumer._connection = None
    consumer._jobs_processed = 0

    ch, method, props, body = _make_delivery(attempt=3)
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
    consumer._job_repo.mark_dead_letter.assert_called_once()


def test_retry_message_includes_stored_content_text():
    """Retry bodies must carry content_text so downstream workers do not see empty text.

    All non-final failures are now re-published through the retry exchange
    with the stored content_text and translated_text from the DB payload.
    """
    consumer = FailingConsumer.__new__(FailingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._job_repo.get_max_attempts.return_value = 5
    # Simulate stored payload with extracted + translated text
    consumer._job_repo.get_payload.return_value = {
        "content_text": "extracted slide text",
        "translated_text": "translated slide text",
    }
    consumer._jobs_processed = 0

    # Any attempt < max_attempts should re-publish through the retry exchange
    ch, method, props, body = _make_delivery(attempt=1)
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_publish.assert_called_once()
    published_body = json.loads(consumer._channel.basic_publish.call_args.kwargs["body"])
    assert published_body.get("content_text") == "extracted slide text"
    assert published_body.get("translated_text") == "translated slide text"


def test_retry_message_omits_content_text_when_payload_empty():
    """When no payload exists the retry body must not include content_text."""
    consumer = FailingConsumer.__new__(FailingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._job_repo.get_max_attempts.return_value = 5
    consumer._job_repo.get_payload.return_value = None
    consumer._jobs_processed = 0

    # Any attempt < max_attempts should re-publish through the retry exchange
    ch, method, props, body = _make_delivery(attempt=1)
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_publish.assert_called_once()
    published_body = json.loads(consumer._channel.basic_publish.call_args.kwargs["body"])
    assert "content_text" not in published_body
    assert "translated_text" not in published_body
