from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import (
    _SENSITIVE_CONFIG_KEYS,
    _audit_log,
    _classify_connection_error,
    _fmt_dt,
    _source_config,
)
from services.api.main import current_user
from services.api.schemas import (
    ConnectionTestResult,
    CreateSourceRequest,
    GrantPermissionRequest,
    UpdateSourceRequest,
)
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.connectors.factory import build_connector, connector_types
from services.permissions.enforcer import require_admin
from shared.db import db_resolve_json, to_uuid

# Recognised OCR-capable parser names.  These perform explicit OCR (vs
# non-OCR parsers that extract text natively from the file format).
_OCR_PARSERS: frozenset[str] = frozenset({"OcrExtractor"})

router = APIRouter(tags=["admin"])


def _parse_json_list(raw: object) -> list[str]:
    """Safely parse a JSON list from either a native Python list or a JSON string."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(w) for w in raw]
    try:
        parsed = db_resolve_json(raw)
        if isinstance(parsed, list):
            return [str(w) for w in parsed]
    except Exception:
        pass
    return [str(raw)]


def _approximate_chunk_count(char_count: int) -> int:
    """Approximate chunk count from character count (~2000 chars per chunk)."""
    if char_count <= 0:
        return 0
    return max(1, (char_count + 1000) // 2000)


@router.get("/admin/connector-types")
def admin_connector_types(
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    return connector_types()


@router.get("/admin/source-languages")
def admin_source_languages(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[str]:
    require_admin(user)
    return request.app.state.settings.supported_translation_source_languages_list  # type: ignore[no-any-return]


@router.post(
    "/admin/sources/{source_id}/test-connection",
    response_model=ConnectionTestResult,
)
def admin_test_source_connection(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ConnectionTestResult:
    """Validate a source configuration and reachability."""
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
        checked_at = datetime.now(UTC).isoformat()

        try:
            connector = build_connector(source_row)
            connector.validate()
        except Exception as exc:
            status, error = _classify_connection_error(exc, connector_type, source_row)
            connection.execute(
                sa.text("""
                    UPDATE ingestion_sources
                    SET last_validation_status = :status,
                        last_validation_error = :error,
                        last_validated_at = :checked_at
                    WHERE id = :id
                    """),
                {
                    "id": source_id.hex,
                    "status": status,
                    "error": error,
                    "checked_at": checked_at,
                },
            )
            return ConnectionTestResult(
                source_id=str(source_id),
                status=status,
                checked_at=checked_at,
                error=error,
            )

        details: dict[str, Any] = {"config_valid": True}
        connection.execute(
            sa.text("""
                UPDATE ingestion_sources
                SET last_validation_status = 'ok',
                    last_validation_error = NULL,
                    last_validated_at = :checked_at
                WHERE id = :id
                """),
            {
                "id": source_id.hex,
                "checked_at": checked_at,
            },
        )
        return ConnectionTestResult(
            source_id=str(source_id),
            status="ok",
            checked_at=checked_at,
            details=details,
        )


@router.get("/admin/sources")
def admin_list_sources(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(
            sa.text("""
                SELECT id, name, type, path, source_language, enabled, created_at,
                       schedule,
                       last_sync_status, last_sync_indexed, last_sync_skipped,
                       last_sync_failed, last_sync_error, last_sync_at,
                       last_validation_status, last_validation_error, last_validated_at,
                       last_successful_sync_at, last_failed_sync_at,
                       failure_count, warning_count, last_sync_id
                FROM ingestion_sources ORDER BY created_at DESC
                """)
        ).mappings()
        return [
            {
                "id": str(to_uuid(row["id"])),
                "name": row["name"],
                "type": row["type"],
                "path": row["path"],
                "source_language": row["source_language"],
                "enabled": row["enabled"],
                "created_at": _fmt_dt(row["created_at"]),
                "last_sync_status": row.get("last_sync_status"),
                "last_sync_indexed": row.get("last_sync_indexed"),
                "last_sync_skipped": row.get("last_sync_skipped"),
                "last_sync_failed": row.get("last_sync_failed"),
                "last_sync_error": row.get("last_sync_error"),
                "last_sync_at": _fmt_dt(row.get("last_sync_at")),
                "last_validation_status": row.get("last_validation_status"),
                "last_validation_error": row.get("last_validation_error"),
                "last_validated_at": _fmt_dt(row.get("last_validated_at")),
                "schedule": row.get("schedule"),
                # New source health fields
                "last_successful_sync_at": _fmt_dt(row.get("last_successful_sync_at")),
                "last_failed_sync_at": _fmt_dt(row.get("last_failed_sync_at")),
                "failure_count": row.get("failure_count") or 0,
                "warning_count": row.get("warning_count") or 0,
                "last_sync_id": (
                    str(to_uuid(row["last_sync_id"])) if row.get("last_sync_id") else None
                ),
            }
            for row in rows
        ]


@router.get("/admin/sources/{source_id}")
def admin_get_source(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        row = (
            connection.execute(
                sa.text("""
                SELECT id, name, type, path, source_language, enabled, created_at,
                       config, schedule,
                       last_sync_status, last_sync_indexed, last_sync_skipped,
                       last_sync_failed, last_sync_error, last_sync_at,
                       last_validation_status, last_validation_error, last_validated_at,
                       last_successful_sync_at, last_failed_sync_at,
                       failure_count, warning_count, last_sync_id
                FROM ingestion_sources WHERE id = :id
                """),
                {"id": source_id.hex},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Source not found")

        config = _source_config(row.get("config"))
        masked_config: dict[str, Any] = {}
        for key, value in config.items():
            if key.lower() in _SENSITIVE_CONFIG_KEYS:
                masked_config[key] = "••••••••"
            else:
                masked_config[key] = value

        permissions = (
            connection.execute(
                sa.text("""
                SELECT g.id, g.name
                FROM source_permissions sp
                JOIN groups g ON g.id = sp.group_id
                WHERE sp.source_id = :source_id
                ORDER BY g.name
                """),
                {"source_id": source_id.hex},
            )
            .mappings()
            .all()
        )

        return {
            "id": str(to_uuid(row["id"])),
            "name": row["name"],
            "type": row["type"],
            "path": row["path"],
            "source_language": row["source_language"],
            "enabled": row["enabled"],
            "created_at": _fmt_dt(row["created_at"]),
            "config": masked_config,
            "last_sync_status": row.get("last_sync_status"),
            "last_sync_indexed": row.get("last_sync_indexed"),
            "last_sync_skipped": row.get("last_sync_skipped"),
            "last_sync_failed": row.get("last_sync_failed"),
            "last_sync_error": row.get("last_sync_error"),
            "last_sync_at": _fmt_dt(row.get("last_sync_at")),
            "last_validation_status": row.get("last_validation_status"),
            "last_validation_error": row.get("last_validation_error"),
            "last_validated_at": _fmt_dt(row.get("last_validated_at")),
            "schedule": row.get("schedule"),
            "groups": [{"id": str(to_uuid(p["id"])), "name": p["name"]} for p in permissions],
            # New source health fields
            "last_successful_sync_at": _fmt_dt(row.get("last_successful_sync_at")),
            "last_failed_sync_at": _fmt_dt(row.get("last_failed_sync_at")),
            "failure_count": row.get("failure_count") or 0,
            "warning_count": row.get("warning_count") or 0,
            "last_sync_id": (
                str(to_uuid(row["last_sync_id"])) if row.get("last_sync_id") else None
            ),
        }


@router.put("/admin/sources/{source_id}")
def admin_update_source(
    source_id: UUID,
    body: UpdateSourceRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        existing = connection.execute(
            sa.text("SELECT id FROM ingestion_sources WHERE id = :id"),
            {"id": source_id.hex},
        ).scalar()
        if existing is None:
            raise HTTPException(status_code=404, detail="Source not found")

        updates: list[str] = []
        params: dict[str, Any] = {"id": source_id.hex}
        if body.name is not None:
            updates.append("name = :name")
            params["name"] = body.name
        if body.source_language is not None:
            updates.append("source_language = :source_language")
            params["source_language"] = body.source_language
        if body.enabled is not None:
            updates.append("enabled = :enabled")
            params["enabled"] = body.enabled
        if body.config is not None:
            updates.append("config = :config")
            params["config"] = json.dumps(body.config)
        if body.schedule is not None:
            updates.append("schedule = :schedule")
            params["schedule"] = body.schedule
        if updates:
            # Safe: `updates` list contains only hardcoded column-name strings
            # (e.g. "name = :name").  User values go through `params` via
            # bound parameters — no SQL injection surface.
            connection.execute(
                sa.text(f"UPDATE ingestion_sources SET {', '.join(updates)} WHERE id = :id"),
                params,
            )
        _audit_log(connection, user.sub, "update", "source", str(source_id))
        return {"id": str(source_id)}


@router.post("/admin/sources", status_code=201)
def admin_create_source(
    body: CreateSourceRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        source_id = uuid4()
        connection.execute(
            sa.text("""
                INSERT INTO ingestion_sources
                    (id, name, type, path, source_language, enabled, config)
                VALUES
                    (:id, :name, :type, :path, :source_language, :enabled, :config)
                """),
            {
                "id": source_id.hex,
                "name": body.name,
                "type": body.type,
                "path": body.path,
                "source_language": body.source_language,
                "enabled": body.enabled,
                "config": json.dumps(body.config),
            },
        )
        auth_repo = AuthRepository(connection)
        admins_group_id = auth_repo.ensure_group("admins")
        auth_repo.grant_source_to_group(source_id, admins_group_id)
        _audit_log(
            connection,
            user.sub,
            "create",
            "source",
            str(source_id),
            {"name": body.name},
        )
        return {
            "id": str(source_id),
            "name": body.name,
            "type": body.type,
            "path": body.path,
            "source_language": body.source_language,
            "enabled": body.enabled,
            "created_at": None,
            "last_sync_status": None,
            "last_sync_indexed": None,
            "last_sync_skipped": None,
            "last_sync_failed": None,
            "last_sync_error": None,
            "last_sync_at": None,
            "last_validation_status": None,
            "last_validation_error": None,
            "last_validated_at": None,
        }


@router.post("/admin/sources/{source_id}/permissions", status_code=201)
def admin_grant_permission(
    source_id: UUID,
    body: GrantPermissionRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    group_id = UUID(body.group_id)
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.grant_source_to_group(source_id, group_id)
        _audit_log(
            connection,
            user.sub,
            "grant",
            "permission",
            str(source_id),
            {"group_id": str(group_id)},
        )
        return {"source_id": str(source_id), "group_id": str(group_id)}


@router.delete("/admin/sources/{source_id}/permissions/{group_id}", status_code=204)
def admin_revoke_permission(
    source_id: UUID,
    group_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        connection.execute(
            sa.text("""
                DELETE FROM source_permissions
                WHERE source_id = :source_id AND group_id = :group_id
                """),
            {"source_id": source_id.hex, "group_id": group_id.hex},
        )
        _audit_log(
            connection,
            user.sub,
            "revoke",
            "permission",
            str(source_id),
            {"group_id": str(group_id)},
        )


@router.get("/admin/sources/{source_id}/documents")
def admin_get_source_documents(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        existing = connection.execute(
            sa.text("SELECT 1 FROM ingestion_sources WHERE id = :id"),
            {"id": source_id.hex},
        ).scalar()
        if existing is None:
            raise HTTPException(status_code=404, detail="Source not found")

        count_row = connection.execute(
            sa.text("SELECT COUNT(*) FROM documents WHERE source_id = :source_id"),
            {"source_id": source_id.hex},
        ).scalar()
        total = int(count_row or 0)

        # ── parser_summary computed from ALL documents (not paginated) ──
        parser_summary: dict[str, Any] = {
            "documents_by_parser": {},
            "total_extracted": 0,
            "total_ocr_done": 0,
            "total_failed": 0,
            "total_documents": total,
            "avg_char_count": 0,
        }
        if total > 0:
            summary_rows = connection.execute(
                sa.text("""
                    SELECT
                        e_sum.parser_name,
                        COUNT(*) AS doc_count,
                        d.mime_type,
                        e_sum.warnings AS extraction_warnings,
                        p_sum.char_count,
                        pj.status AS parse_status
                    FROM documents d
                    LEFT JOIN LATERAL (
                        SELECT parser_name, warnings
                        FROM document_extractions
                        WHERE document_id = d.id
                        ORDER BY created_at DESC LIMIT 1
                    ) e_sum ON true
                    LEFT JOIN LATERAL (
                        SELECT LENGTH(content_text) AS char_count
                        FROM document_payloads
                        WHERE document_id = d.id
                        LIMIT 1
                    ) p_sum ON true
                    LEFT JOIN LATERAL (
                        SELECT status
                        FROM pipeline_jobs
                        WHERE document_id = d.id AND job_type = 'process_document'
                        ORDER BY created_at DESC LIMIT 1
                    ) pj ON true
                    WHERE d.source_id = :source_id
                    GROUP BY e_sum.parser_name, d.mime_type, e_sum.warnings,
                             p_sum.char_count, pj.status
                    """),
                {"source_id": source_id.hex},
            ).mappings()

            parser_counts: dict[str, int] = {}
            total_extracted = 0
            total_ocr_done = 0
            total_failed = 0
            total_char_count = 0
            for srow in summary_rows:
                doc_count = srow.get("doc_count", 1) or 1
                pname = srow.get("parser_name")
                if pname:
                    parser_counts[pname] = parser_counts.get(pname, 0) + doc_count
                    total_extracted += doc_count
                else:
                    # Dead-letter parse job → failed
                    if srow.get("parse_status") == "dead_letter":
                        total_failed += doc_count

                # OCR-done inference: count extracted docs likely OCR-processed
                mime = srow.get("mime_type") or ""
                if pname and (
                    mime.startswith("image/")
                    or (
                        mime == "application/pdf"
                        and any(
                            "ocr" in w.lower()
                            for w in _parse_json_list(srow.get("extraction_warnings"))
                        )
                    )
                ):
                    total_ocr_done += doc_count

                cc = srow.get("char_count") or 0
                total_char_count += cc * doc_count

            parser_summary["documents_by_parser"] = parser_counts
            parser_summary["total_extracted"] = total_extracted
            parser_summary["total_ocr_done"] = total_ocr_done
            parser_summary["total_failed"] = total_failed
            parser_summary["avg_char_count"] = round(total_char_count / total) if total > 0 else 0

        # ── Paginated document rows ──
        rows = connection.execute(
            sa.text("""
                SELECT d.id, d.title, d.external_id, d.status, d.mime_type,
                       d.source_language, d.translation_quality, d.created_at,
                       COALESCE(j.total_jobs, 0) AS total_jobs,
                       COALESCE(j.succeeded_jobs, 0) AS succeeded_jobs,
                       COALESCE(j.pending_jobs, 0) AS pending_jobs,
                       COALESCE(j.failed_jobs, 0) AS failed_jobs,
                       e.parser_name,
                       e.attempts AS fallback_chain,
                       e.confidence AS extraction_confidence,
                       e.warnings AS extraction_warnings,
                       e.duration_ms AS extraction_duration_ms,
                       p.char_count,
                       lb.layout_blocks_available,
                       lb.table_block_count,
                       lb.figure_block_count
                FROM documents d
                LEFT JOIN (
                    SELECT document_id,
                           COUNT(*) AS total_jobs,
                           COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded_jobs,
                           COUNT(*) FILTER (WHERE status IN ('pending', 'running', 'retry'))
                               AS pending_jobs,
                           COUNT(*) FILTER (WHERE status = 'dead_letter') AS failed_jobs
                    FROM pipeline_jobs
                    GROUP BY document_id
                ) j ON j.document_id = d.id
                LEFT JOIN LATERAL (
                    SELECT parser_name, attempts, confidence, warnings, duration_ms
                    FROM document_extractions
                    WHERE document_id = d.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) e ON true
                LEFT JOIN LATERAL (
                    SELECT LENGTH(content_text) AS char_count
                    FROM document_payloads
                    WHERE document_id = d.id
                    LIMIT 1
                ) p ON true
                LEFT JOIN (
                    SELECT document_id,
                           COUNT(*) AS layout_blocks_available,
                           COUNT(*) FILTER (WHERE block_type = 'table') AS table_block_count,
                           COUNT(*) FILTER (WHERE block_type = 'figure') AS figure_block_count
                    FROM document_layout_blocks
                    GROUP BY document_id
                ) lb ON lb.document_id = d.id
                WHERE d.source_id = :source_id
                ORDER BY d.created_at DESC
                LIMIT :limit OFFSET :offset
                """),
            {"source_id": source_id.hex, "limit": limit, "offset": offset},
        ).mappings()

        doc_rows = list(rows)
        doc_ids = [row["id"] for row in doc_rows]

        jobs_by_doc: dict[str, list[dict[str, Any]]] = {}
        if doc_ids:
            job_rows = connection.execute(
                sa.text("""
                    SELECT id, document_id, job_type, status, attempts,
                           max_attempts, stage, last_error,
                           rabbit_message_id, created_at, updated_at
                    FROM pipeline_jobs
                    WHERE document_id = ANY(:doc_ids)
                    ORDER BY created_at ASC
                    """),
                {"doc_ids": [d.hex for d in doc_ids]},
            ).mappings()
            for jr in job_rows:
                did = str(to_uuid(jr["document_id"]))
                if did not in jobs_by_doc:
                    jobs_by_doc[did] = []
                jobs_by_doc[did].append(
                    {
                        "id": str(to_uuid(jr["id"])),
                        "job_type": jr["job_type"],
                        "status": jr["status"],
                        "attempts": jr["attempts"],
                        "max_attempts": jr["max_attempts"],
                        "stage": jr["stage"],
                        "last_error": jr["last_error"],
                        "rabbit_message_id": jr["rabbit_message_id"],
                        "created_at": _fmt_dt(jr["created_at"]),
                        "updated_at": _fmt_dt(jr["updated_at"]),
                    }
                )

        # Build per-document metadata from the paginated rows
        documents = []
        for row in doc_rows:
            did = str(to_uuid(row["id"]))
            # Compute parse_job once per document
            parse_job = next(
                (j for j in jobs_by_doc.get(did, []) if j["job_type"] == "process_document"),
                None,
            )

            parser_name = row.get("parser_name")
            # extraction_status: "extracted" if parser ran, "failed" if parse
            # job dead-lettered, "pending" otherwise.
            if parser_name:
                extraction_status = "extracted"
            elif parse_job and parse_job["status"] == "dead_letter":
                extraction_status = "failed"
            else:
                extraction_status = "pending"

            char_count = row.get("char_count") or 0
            chunk_count = _approximate_chunk_count(char_count)

            # OCR-needed: image/* always needs OCR; PDF needs OCR when
            # extraction warnings mention it.
            mime = row.get("mime_type") or ""
            ocr_needed = mime.startswith("image/") or (
                mime == "application/pdf"
                and any(
                    "ocr" in w.lower() for w in _parse_json_list(row.get("extraction_warnings"))
                )
            )
            # ocr_performed: true only when a recognised OCR-capable parser
            # produced the extraction, not as a general heuristic.
            ocr_performed: bool | None = None
            if parser_name and parser_name in _OCR_PARSERS:
                ocr_performed = True

            fallback_chain_raw = row.get("fallback_chain")
            fallback_chain: list[str] | None = None
            if fallback_chain_raw is not None:
                fallback_chain = _parse_json_list(fallback_chain_raw) or None
                if not fallback_chain:
                    fallback_chain = None

            last_error: str | None = None
            if parse_job and parse_job.get("last_error"):
                last_error = parse_job["last_error"]

            docs = {
                "id": did,
                "title": row["title"],
                "external_id": row["external_id"],
                "status": row["status"],
                "mime_type": row["mime_type"],
                "source_language": row["source_language"],
                "translation_quality": row["translation_quality"],
                "created_at": _fmt_dt(row["created_at"]),
                "total_jobs": row["total_jobs"],
                "succeeded_jobs": row["succeeded_jobs"],
                "pending_jobs": row["pending_jobs"],
                "failed_jobs": row["failed_jobs"],
                "jobs": jobs_by_doc.get(did, []),
                # Parser metadata (new)
                "parser_name": parser_name,
                "fallback_chain": fallback_chain,
                "extraction_status": extraction_status,
                "extraction_confidence": row.get("extraction_confidence"),
                "extraction_duration_ms": row.get("extraction_duration_ms"),
                "char_count": char_count,
                "chunk_count": chunk_count,
                "ocr_needed": ocr_needed,
                "ocr_performed": ocr_performed,
                "translation_status": row.get("translation_quality"),
                "layout_blocks_available": bool(row.get("layout_blocks_available")),
                "table_block_count": row.get("table_block_count") or 0,
                "figure_block_count": row.get("figure_block_count") or 0,
                "last_error": last_error,
            }
            documents.append(docs)

        return {"documents": documents, "total": total, "parser_summary": parser_summary}


@router.delete("/admin/sources/{source_id}", status_code=204)
def admin_delete_source(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        existing = connection.execute(
            sa.text("SELECT id, name FROM ingestion_sources WHERE id = :id"),
            {"id": source_id.hex},
        ).first()
        if existing is None:
            raise HTTPException(status_code=404, detail="Source not found")

        connection.execute(
            sa.text("DELETE FROM ingestion_sources WHERE id = :id"),
            {"id": source_id.hex},
        )
        _audit_log(connection, user.sub, "delete", "source", str(source_id))


@router.delete("/admin/documents/{document_id}", status_code=204)
def admin_delete_document(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        existing = connection.execute(
            sa.text("SELECT id, title FROM documents WHERE id = :id"),
            {"id": document_id.hex},
        ).first()
        if existing is None:
            raise HTTPException(status_code=404, detail="Document not found")

        connection.execute(
            sa.text("DELETE FROM documents WHERE id = :id"),
            {"id": document_id.hex},
        )
        _audit_log(connection, user.sub, "delete", "document", str(document_id))
