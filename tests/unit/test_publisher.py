from unittest.mock import MagicMock
from uuid import uuid4

from services.pipeline.publisher import DocumentPublisher


def _make_publisher(rabbit_enabled: bool = True):
    mock_job_repo = MagicMock()
    mock_rabbit = MagicMock()
    mock_rabbit.enabled = rabbit_enabled
    mock_rabbit.publish.return_value = "msg-uuid-123"
    return DocumentPublisher(job_repo=mock_job_repo, rabbit=mock_rabbit), mock_job_repo, mock_rabbit


def test_publish_parse_stores_message_id():
    pub, job_repo, rabbit = _make_publisher()
    job_id = uuid4()
    document_id = uuid4()
    source_id = uuid4()

    pub.publish_parse(
        job_id=job_id,
        document_id=document_id,
        source_id=source_id,
    )

    rabbit.publish.assert_called_once_with(
        "document.parse.requested",
        {
            "job_id": str(job_id),
            "document_id": str(document_id),
            "source_id": str(source_id),
            "attempt": 1,
            "pipeline_version": "v1",
        },
    )
    job_repo.set_rabbit_message_id.assert_called_once_with(job_id, "msg-uuid-123")


def test_publish_parse_skips_rabbit_when_disabled():
    pub, job_repo, rabbit = _make_publisher(rabbit_enabled=False)
    rabbit.publish.return_value = ""
    pub.publish_parse(job_id=uuid4(), document_id=uuid4(), source_id=uuid4())
    job_repo.set_rabbit_message_id.assert_not_called()
