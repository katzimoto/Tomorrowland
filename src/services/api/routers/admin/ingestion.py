from __future__ import annotations

import logging
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _record_source_sync_state, _sanitize_source_error
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.connectors.factory import build_connector
from services.connectors.sync_models import SyncRunCreate, SyncRunUpdate
from services.connectors.sync_repository import SyncRunRepository
from services.documents.models import DocumentSource
from services.documents.repository import DocumentRepository
from services.permissions.enforcer import require_admin
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.original_store import move_to_originals
from shared.db import db_uuid
from shared.metrics import safe_label_value

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


def _publish_pending_rabbit_messages(
    request: Request,
    pending: list[dict[str, Any]],
) -> None:
    if not pending or not request.app.state.settings.rabbitmq_enabled:
        return

    from uuid import uuid4 as _uuid4

    from shared.rabbit import RabbitClient, RabbitConnectionError

    rabbit = getattr(request.app.state, "rabbit", None) or RabbitClient(
        request.app.state.settings.rabbitmq_url,
        enabled=True,
    )
    try:
        rabbit.connect()
        rabbit.declare_topology()
    except RabbitConnectionError as exc:
        raise HTTPException(
            status_code=502,
            detail="RabbitMQ is unreachable — pipeline messages could not be published. "
            "Check the RabbitMQ service and retry the sync.",
        ) from exc

    message_ids: dict[str, str] = {}
    with request.app.state.engine.begin() as connection:
        pub_repo = PipelineJobRepository(connection)
        for p in pending:
            mid = str(_uuid4())
            message_ids[p["job_id"]] = mid
            pub_repo.set_rabbit_message_id(p["job_id"], mid)
    # DB committed — pipeline_jobs rows visible to workers

    for p in pending:
        body: dict[str, Any] = {
            "job_id": str(p["job_id"]),
            "document_id": str(p["document_id"]),
            "source_id": str(p["source_id"]),
            "attempt": 1,
            "pipeline_version": "v1",
        }
        if p.get("content_text"):
            body["content_text"] = p["content_text"]
        rabbit.publish_with_id("document.parse.requested", body, message_ids[p["job_id"]])


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

        connector_type = str(source_row["type"])

        # Create a sync run record
        sync_repo = SyncRunRepository(connection)

        # Guard against concurrent syncs
        if sync_repo.has_active_sync(source_id):
            raise HTTPException(
                status_code=409,
                detail="Source already has an active sync in progress. "
                "Wait for it to complete before starting a new one.",
            )

        sync_run = sync_repo.create(
            SyncRunCreate(
                source_id=source_id,
                connector_type=connector_type,
                sync_mode="incremental",
            )
        )
        sync_run_id = sync_run.id
        sync_repo.start(sync_run_id)

        try:
            connector = build_connector(source_row)
            connector.validate()
        except ValueError as exc:
            detail = _sanitize_source_error(str(exc), source_row)
            sync_repo.complete(sync_run_id, "failed", error_summary=detail)
            _record_source_sync_state(
                connection,
                source_id,
                status="failed",
                failed=1,
                error=detail,
                sync_run_id=sync_run_id,
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
            "unchanged": 0,
        }
        pending_rabbit: list[dict[str, Any]] = []
        source_language = source_row.get("source_language")
        originals_root = request.app.state.settings.files_root / "originals"
        try:
            documents = connector.fetch_documents(storage_root=originals_root)
        except NotImplementedError as exc:
            detail = _sanitize_source_error(str(exc), source_row)
            sync_repo.complete(sync_run_id, "failed", error_summary=detail)
            _record_source_sync_state(
                connection,
                source_id,
                status="failed",
                failed=1,
                error=detail,
                sync_run_id=sync_run_id,
            )
            raise HTTPException(status_code=400, detail=detail) from exc
        except Exception as exc:
            detail = _sanitize_source_error(
                "Sync failed while reading source documents. "
                "Check connector settings and source availability.",
                source_row,
            )
            sync_repo.complete(sync_run_id, "failed", error_summary=detail)
            _record_source_sync_state(
                connection,
                source_id,
                status="failed",
                failed=1,
                error=detail,
                sync_run_id=sync_run_id,
            )
            raise HTTPException(status_code=502, detail=detail) from exc

        for item in documents:
            results["discovered"] += 1
            request.app.state.metrics.ingestion_documents_total.labels(
                safe_label_value(connector_type), "discovered"
            ).inc()

            try:
                stored_path = item.path
                moved = move_to_originals(
                    item.path, item.mime_type, request.app.state.settings.files_root
                )
                if moved is not None:
                    stored_path = moved

                doc = doc_repo.create(
                    source_id=source_id,
                    external_id=item.external_id,
                    source=cast("DocumentSource", source_row["type"]),
                    mime_type=item.mime_type,
                    path=stored_path,
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

                effective_lang = item.source_language or source_language
                if effective_lang is None:
                    logger.warning(
                        "document ingested without source_language: source_id=%s "
                        "external_id=%s mime_type=%s — translation will use LibreTranslate "
                        "auto-detect which may fail. Set source_language on the ingestion source.",
                        source_id,
                        item.external_id,
                        item.mime_type,
                    )

                results["created"] += 1
                try:
                    job_id = job_repo.enqueue_document(
                        document_id=doc.id,
                        source_id=source_id,
                        content_text=item.text_content,
                    )
                    results["enqueued"] += 1

                    pending_rabbit.append(
                        {
                            "job_id": job_id,
                            "document_id": doc.id,
                            "source_id": source_id,
                            "content_text": item.text_content,
                        }
                    )

                    request.app.state.metrics.ingestion_documents_total.labels(
                        safe_label_value(connector_type), "success"
                    ).inc()
                except Exception:
                    results["failed_enqueue"] += 1
                    request.app.state.metrics.ingestion_documents_total.labels(
                        safe_label_value(connector_type), "failure"
                    ).inc()
                    connection.execute(
                        sa.text(
                            "INSERT INTO dlq (id, document_id, error_message, status) "
                            "VALUES (:id, :document_id, :error_message, 'pending')"
                        ),
                        {
                            "id": db_uuid(uuid4()),
                            "document_id": db_uuid(doc.id),
                            "error_message": "Failed to enqueue document for processing",
                        },
                    )
            except Exception:
                results["failed_discovery"] += 1
                request.app.state.metrics.ingestion_documents_total.labels(
                    safe_label_value(connector_type), "failure"
                ).inc()

        if results["discovered"] > 0 and results["failed_discovery"] == results["discovered"]:
            sync_outcome = "failed"
            sync_run_status: str = "failed"
        elif results["failed_enqueue"] > 0 or results["failed_discovery"] > 0:
            sync_outcome = "partial_failure"
            sync_run_status = "completed_with_warnings"
        else:
            sync_outcome = "success"
            sync_run_status = "completed"

        request.app.state.metrics.ingestion_syncs_total.labels(
            safe_label_value(connector_type), sync_outcome
        ).inc()

        # Record final counts before completing — complete() sets the terminal status
        sync_repo.update(
            sync_run_id,
            SyncRunUpdate(
                documents_discovered=results["discovered"],
                documents_created=results["created"],
                documents_skipped=results["skipped"],
                documents_failed=results["failed_discovery"] + results["failed_enqueue"],
            ),
        )
        sync_repo.complete(sync_run_id, sync_run_status)  # type: ignore[arg-type]

        _record_source_sync_state(
            connection,
            source_id,
            status=sync_outcome,
            indexed=results["enqueued"],
            skipped=results["skipped"],
            failed=results["failed_discovery"] + results["failed_enqueue"],
            sync_run_id=sync_run_id,
        )
    # Publish to RabbitMQ after transaction commits so consumers see the documents
    _publish_pending_rabbit_messages(request, pending_rabbit)

    return {"status": sync_outcome, "sync_run_id": str(sync_run_id), **results}
