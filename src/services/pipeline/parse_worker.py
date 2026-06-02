"""Parse stage consumer — extracts text from a document and publishes translate."""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from services.documents.repository import DocumentRelationshipRepository, DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher

logger = logging.getLogger(__name__)


def _maybe_delete_connector_temp(path: str) -> None:
    """Delete *path* if it lives inside the system temporary directory.

    Connectors that download files to a temp location set ``doc.path`` to a
    temp file the worker owns after extraction.  Folder and NiFi staged files
    live outside the system temp directory and are intentionally left untouched.
    """
    try:
        p = Path(path)
        if p.is_relative_to(Path(tempfile.gettempdir())):
            p.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning(
            "Failed to delete connector temp file path=%s error_type=%s",
            path,
            exc.__class__.__name__,
        )


# Maximum attachment nesting depth before we stop expanding child documents.
# Bounds resource use on deeply nested (e.g. zip-in-zip) archives even when no
# exact content cycle is present.
_MAX_ATTACHMENT_NESTING = 10


def _attachment_cycle_or_depth_skip(parent_external_id: str, sha256_hex: str) -> bool:
    """Return True when processing this attachment would loop or nest too deep.

    Each ancestor attachment's sha256 prefix is encoded in the document's
    ``external_id`` (``...::attachment::<name>::<sha12>``). If this attachment's
    prefix already appears in the chain it's a content cycle; if the chain is
    already ``_MAX_ATTACHMENT_NESTING`` deep we stop regardless. Both prevent the
    unbounded child-document/job expansion a cyclic or deeply nested archive
    would otherwise trigger (the async pipeline cannot pass a recursion ``_seen``
    set, so the chain is reconstructed from ``external_id``).
    """
    if sha256_hex[:12] in parent_external_id:
        return True
    return parent_external_id.count("::attachment::") >= _MAX_ATTACHMENT_NESTING


class ParseConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def __init__(
        self,
        rabbit: Any,
        job_repo: PipelineJobRepository,
        doc_repo: DocumentRepository,
        publisher: DocumentPublisher,
        extractor: ExtractorRegistry | None = None,
        health_port: int = 8081,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._doc_repo = doc_repo
        self._publisher = publisher
        self._extractor = extractor or ExtractorRegistry()

    def handle_message(
        self,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        correlation_id: str,
        content_text: str = "",
        translated_text: str = "",
    ) -> None:
        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        payload = self._job_repo.get_payload(document_id)
        content_text = (payload.get("content_text", "") if payload else None) or ""
        location_segments: list[dict[str, Any]] = []
        _extraction_attachments: list[Any] = []
        if not content_text and doc.path:
            result = self._extractor.extract(Path(doc.path), doc.mime_type)
            content_text = result.text
            location_segments = [seg.to_dict() for seg in result.location_segments]
            if location_segments:
                self._job_repo.update_extraction_metadata(document_id, location_segments)
            _extraction_attachments = result.attachments
            # Release connector-owned temp files after extraction
            _maybe_delete_connector_temp(doc.path)

        self._job_repo.update_content_text(document_id, content_text)
        self._job_repo.mark_running_stage(job_id, "parsed")
        self._job_repo.commit()
        logger.debug("parsed document_id=%s text_len=%d", document_id, len(content_text))
        self._publisher.publish_translate(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
        )

        # Process email/archive attachments as child documents (best-effort).
        for att in _extraction_attachments:
            try:
                sha256 = hashlib.sha256(att.data).hexdigest()
                if _attachment_cycle_or_depth_skip(doc.external_id or "", sha256):
                    logger.warning(
                        "Skipping attachment (cycle or max nesting depth) parent_id=%s filename=%s",
                        document_id,
                        att.filename,
                    )
                    continue
                # Skip attachments whose MIME type cannot yield text (images,
                # audio, video) so we don't spawn no-op child documents/jobs.
                if not self._extractor.has_extractor(att.mime_type):
                    logger.debug(
                        "Skipping unextractable attachment mime_type=%s filename=%s parent_id=%s",
                        att.mime_type,
                        att.filename,
                        document_id,
                    )
                    continue
                suffix = Path(att.filename).suffix or ".bin"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(att.data)
                    tmp_path = tmp.name

                child_external_id = f"{doc.external_id}::attachment::{att.filename}::{sha256[:12]}"
                child_doc = self._doc_repo.create(
                    source_id=source_id,
                    external_id=child_external_id,
                    source=doc.source,
                    mime_type=att.mime_type,
                    path=tmp_path,
                    title=att.filename,
                    source_language=doc.source_language,
                    metadata={"parent_document_id": str(document_id)},
                )
                if child_doc is None:
                    Path(tmp_path).unlink(missing_ok=True)
                    continue

                rel_repo = DocumentRelationshipRepository(self._doc_repo._connection)
                rel_type = (
                    "email_attachment"
                    if doc.mime_type in ("message/rfc822", "application/vnd.ms-outlook")
                    else "archive_child"
                )
                rel_repo.create_relationship(document_id, child_doc.id, rel_type, att.filename)

                child_job_id = self._job_repo.enqueue_document(
                    document_id=child_doc.id,
                    source_id=source_id,
                )
                self._publisher.publish_parse(
                    job_id=child_job_id,
                    document_id=child_doc.id,
                    source_id=source_id,
                    attempt=1,
                )
                logger.info(
                    "attachment enqueued: parent_id=%s child_id=%s filename=%s",
                    document_id,
                    child_doc.id,
                    att.filename,
                )
            except Exception:
                logger.exception(
                    "Failed to process attachment: parent_id=%s filename=%s",
                    document_id,
                    att.filename,
                )


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.documents.repository import DocumentRepository
    from services.pipeline.jobs import PipelineJobRepository
    from services.pipeline.publisher import DocumentPublisher
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    connection = engine.connect()
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
    job_repo = PipelineJobRepository(connection)
    doc_repo = DocumentRepository(connection)
    publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)
    consumer = ParseConsumer(
        rabbit=rabbit,
        job_repo=job_repo,
        doc_repo=doc_repo,
        publisher=publisher,
        extractor=ExtractorRegistry(
            enable_ocr=settings.enable_ocr,
            enable_legacy_office=settings.enable_legacy_office,
            enable_markitdown=settings.enable_markitdown,
        ),
    )
    consumer.run()
