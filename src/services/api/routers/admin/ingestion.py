from __future__ import annotations

import os
from contextlib import suppress
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _record_source_sync_state, _sanitize_source_error
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.connectors.factory import build_connector
from services.documents.models import DocumentSource
from services.documents.repository import DocumentRepository
from services.permissions.enforcer import require_admin
from services.pipeline.jobs import PipelineJobRepository
from shared.db import db_uuid
from shared.metrics import safe_label_value

router = APIRouter(tags=["admin"])


@router.post("/admin/ingestion/{source_id}/sync-now")
def sync_now(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)

    with request.app.state.engine.begin() as connection:
        source_row = (
            connection.execute(
                sa.text("SELECT * FROM ingestion_sources WHERE id = :id"),
                {"id": source_id.hex},
            )
            .mappings()
            .first()
        )
        if source_row is None:
            raise HTTPException(status_code=404, detail="Source not found")

        try:
            connector = build_connector(source_row)
            connector.validate()
        except ValueError as exc:
            detail = _sanitize_source_error(str(exc), source_row)
            _record_source_sync_state(
                connection, source_id, status="failed", failed=1, error=detail
            )
            raise HTTPException(status_code=400, detail=detail) from exc

        doc_repo = DocumentRepository(connection)
        job_repo = PipelineJobRepository(connection)

        results: dict[str, int] = {
            "discovered": 0,
            "created": 0,
            "skipped": 0,
            "enqueued": 0,
            "failed_discovery": 0,
            "failed_enqueue": 0,
        }
        pending_rabbit: list[dict[str, Any]] = []
        source_language = source_row.get("source_language")

        def _record_sync_dlq(
            document_id: UUID | None,
            message: str,
        ) -> None:
            connection.execute(
                sa.text("""
                    INSERT INTO dlq (id, document_id, error_message, status)
                    VALUES (:id, :document_id, :error_message, 'pending')
                    """),
                {
                    "id": db_uuid(uuid4()),
                    "document_id": (db_uuid(document_id) if document_id is not None else None),
                    "error_message": message,
                },
            )

        connector_type = str(source_row["type"])
        try:
            documents = connector.fetch_documents()
        except NotImplementedError as exc:
            detail = _sanitize_source_error(str(exc), source_row)
            _record_source_sync_state(
                connection, source_id, status="failed", failed=1, error=detail
            )
            raise HTTPException(status_code=400, detail=detail) from exc
        except Exception as exc:
            detail = _sanitize_source_error(
                "Sync failed while reading source documents. "
                "Check connector settings and source availability.",
                source_row,
            )
            _record_source_sync_state(
                connection, source_id, status="failed", failed=1, error=detail
            )
            raise HTTPException(status_code=502, detail=detail) from exc

        for item in documents:
            results["discovered"] += 1
            request.app.state.metrics.ingestion_documents_total.labels(
                safe_label_value(connector_type), "discovered"
            ).inc()

            try:
                doc = doc_repo.create(
                    source_id=source_id,
                    external_id=item.external_id,
                    source=cast("DocumentSource", source_row["type"]),
                    mime_type=item.mime_type,
                    path=item.path,
                    title=item.title,
                    source_language=item.source_language or source_language,
                    sha256=item.sha256,
                    metadata=item.metadata,
                )
                if doc is None:
                    results["skipped"] += 1
                    request.app.state.metrics.ingestion_documents_total.labels(
                        safe_label_value(connector_type), "skipped"
                    ).inc()
                    continue

                results["created"] += 1
                try:
                    job_id = job_repo.enqueue_document(
                        document_id=doc.id,
                        source_id=source_id,
                        content_text=item.text_content,
                    )
                    results["enqueued"] += 1

                    pending_rabbit.append({
                        "job_id": job_id,
                        "document_id": doc.id,
                        "source_id": source_id,
                        "content_text": item.text_content,
                    })

                    request.app.state.metrics.ingestion_documents_total.labels(
                        safe_label_value(connector_type), "success"
                    ).inc()
                except Exception:
                    results["failed_enqueue"] += 1
                    request.app.state.metrics.ingestion_documents_total.labels(
                        safe_label_value(connector_type), "failure"
                    ).inc()
                    _record_sync_dlq(doc.id, "Failed to enqueue document for processing")
            except Exception:
                results["failed_discovery"] += 1
                request.app.state.metrics.ingestion_documents_total.labels(
                    safe_label_value(connector_type), "failure"
                ).inc()
            finally:
                if connector_type == "smb" and item.path:
                    with suppress(OSError):
                        os.unlink(item.path)

        sync_outcome = (
            "failed"
            if results["failed_discovery"] > 0 and results["discovered"] == 0
            else (
                "partial_failure"
                if results["failed_enqueue"] > 0 or results["failed_discovery"] > 0
                else "success"
            )
        )
        request.app.state.metrics.ingestion_syncs_total.labels(
            safe_label_value(connector_type), sync_outcome
        ).inc()
        _record_source_sync_state(
            connection,
            source_id,
            status=sync_outcome,
            indexed=results["enqueued"],
            skipped=results["skipped"],
            failed=results["failed_discovery"] + results["failed_enqueue"],
        )
        # Publish to RabbitMQ after transaction commits so consumers see the documents
    if pending_rabbit and request.app.state.settings.rabbitmq_enabled:
        from services.pipeline.publisher import DocumentPublisher
        from shared.rabbit import RabbitClient

        rabbit = getattr(request.app.state, "rabbit", None) or RabbitClient(
            request.app.state.settings.rabbitmq_url, enabled=True,
        )
        rabbit.connect()
        rabbit.declare_topology()
        with request.app.state.engine.begin() as conn2:
            pub_repo = PipelineJobRepository(conn2)
            publisher = DocumentPublisher(job_repo=pub_repo, rabbit=rabbit)
            for p in pending_rabbit:
                publisher.publish_parse(
                    job_id=p["job_id"],
                    document_id=p["document_id"],
                    source_id=p["source_id"],
                    content_text=p["content_text"],
                )

    return {"status": sync_outcome, **results}
