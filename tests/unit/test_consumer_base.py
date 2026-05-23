from unittest.mock import MagicMock, call, patch
from uuid import uuid4
import json, pytest
from services.pipeline.consumer_base import BaseConsumer


class SucceedingConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def handle_message(self, job_id, document_id, source_id, attempt, correlation_id):
        pass


class FailingConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def handle_message(self, job_id, document_id, source_id, attempt, correlation_id):
        raise RuntimeError("something broke")


def _make_delivery(job_id=None, attempt=1):
    body = json.dumps({
        "job_id": str(job_id or uuid4()),
        "document_id": str(uuid4()),
        "source_id": str(uuid4()),
        "attempt": attempt,
        "pipeline_version": "v1",
    }).encode()
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


def test_failure_nacks_and_retries_when_attempts_remaining():
    consumer = FailingConsumer.__new__(FailingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._job_repo.get_max_attempts.return_value = 5
    consumer._jobs_processed = 0

    ch, method, props, body = _make_delivery(attempt=1)
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_nack.assert_called_once_with(
        delivery_tag=42, requeue=False
    )
    consumer._job_repo.mark_retry.assert_called_once()


def test_failure_dead_letters_when_attempts_exhausted():
    consumer = FailingConsumer.__new__(FailingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._job_repo.get_max_attempts.return_value = 3
    consumer._jobs_processed = 0

    ch, method, props, body = _make_delivery(attempt=3)
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_nack.assert_called_once_with(
        delivery_tag=42, requeue=False
    )
    consumer._job_repo.mark_dead_letter.assert_called_once()
