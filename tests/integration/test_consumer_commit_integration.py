"""Integration tests validating that consumer DB writes are committed and visible
to downstream stages."""

from uuid import uuid4

import pytest
import sqlalchemy as sa

from services.documents.repository import DocumentRepository
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from shared.db import db_uuid


class _SimpleWriterConsumer(BaseConsumer):
    queue_name = "test.write.requested"
    worker_type = "test-writer"

    def __init__(self, rabbit, job_repo, doc_repo, doc_id):
        super().__init__(rabbit, job_repo)
        self._doc_repo = doc_repo
        self._doc_id = doc_id

    def handle_message(
        self,
        job_id,
        document_id,
        source_id,
        attempt,
        correlation_id,
        content_text="",
        translated_text="",
    ):
        self._doc_repo.update_indexed(self._doc_id, "indexed", "fast")


@pytest.fixture
def _seed_doc(migrated_engine):
    with migrated_engine.begin() as conn:
        src_id = uuid4()
        doc_id = uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO ingestion_sources (id, name, type, source_language, enabled) "
                "VALUES (:id, 'test', 'folder', 'en', true)"
            ),
            {"id": db_uuid(src_id)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type, status) "
                "VALUES (:id, :sid, 'ext', 'folder', 'text/plain', 'pending')"
            ),
            {"id": db_uuid(doc_id), "sid": db_uuid(src_id)},
        )
        return doc_id


class TestConsumerCommit:
    def test_commit_persists_writes(self, migrated_engine, _seed_doc):
        """Consumer writes + commits; another connection sees the data."""
        doc_id = _seed_doc
        conn1 = migrated_engine.connect()
        conn2 = migrated_engine.connect()

        from unittest.mock import MagicMock

        rabbit = MagicMock()
        rabbit._channel = MagicMock()
        jr1 = PipelineJobRepository(conn1)
        dr1 = DocumentRepository(conn1)
        consumer = _SimpleWriterConsumer(rabbit, jr1, dr1, doc_id)

        consumer._channel = MagicMock()
        consumer._jobs_processed = 0

        import json

        body = json.dumps(
            {
                "job_id": str(uuid4()),
                "document_id": str(doc_id),
                "source_id": str(uuid4()),
                "attempt": 1,
            }
        ).encode()
        method = MagicMock()
        method.delivery_tag = 1

        consumer._on_message(MagicMock(), method, MagicMock(), body)

        consumer._channel.basic_ack.assert_called_once_with(delivery_tag=1)

        dr2 = DocumentRepository(conn2)
        doc = dr2.get_by_id(doc_id)
        assert doc is not None
        assert doc.translation_quality == "fast"

        conn1.close()
        conn2.close()

    def test_without_commit_data_is_stale(self, migrated_engine, _seed_doc):
        """Without commit(), another connection sees stale data — proves the bug."""
        doc_id = _seed_doc
        conn1 = migrated_engine.connect()
        conn2 = migrated_engine.connect()

        dr1 = DocumentRepository(conn1)
        dr1.update_indexed(doc_id, "indexed", "fast")

        dr2 = DocumentRepository(conn2)
        doc = dr2.get_by_id(doc_id)
        assert doc.status == "pending"

        conn1.commit()
        conn1.close()
        conn2.close()
