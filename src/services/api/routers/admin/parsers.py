"""Admin API for parser management and extraction history.

Endpoints:
- GET    /admin/parsers                          — list registered parsers
- GET    /admin/parsers/{parser_name}               — parser capabilities
- GET    /admin/documents/{document_id}/extraction  — extraction history
- POST   /admin/parser-policies                     — create policy
- GET    /admin/parser-policies                     — list policies
- GET    /admin/parser-policies/{policy_id}         — get policy
- PATCH  /admin/parser-policies/{policy_id}         — update policy
- DELETE /admin/parser-policies/{policy_id}         — delete policy
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from services.api._helpers import _audit_log
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.extraction.extraction_repository import DocumentExtractionRepository
from services.extraction.policy_repository import ParserPolicyRepository
from services.extraction.registry import ExtractorRegistry
from services.permissions.enforcer import require_admin

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ParserCapabilitiesOut(BaseModel):
    parser_name: str
    parser_version: str
    supported_mime_types: list[str]
    quality_tier: str  # "high" | "standard" | "basic"
    requires_ocr: bool
    max_file_size: int | None


class ExtractionRecordOut(BaseModel):
    id: str
    document_id: str
    parser_name: str
    parser_version: str
    duration_ms: int
    confidence: float | None
    warnings: list[str]
    attempts: list[str]
    created_at: str | None


class ParserPolicyIn(BaseModel):
    source_id: UUID | None = None  # None = global default
    mime_pattern: str = Field(min_length=1)
    parser_chain: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    priority: int = 0


class ParserPolicyUpdate(BaseModel):
    mime_pattern: str | None = None
    parser_chain: list[str] | None = None
    options: dict[str, Any] | None = None
    enabled: bool | None = None
    priority: int | None = None


class ParserPolicyOut(BaseModel):
    id: str
    source_id: str | None
    mime_pattern: str
    parser_chain: list[str]
    options: dict[str, Any]
    enabled: bool
    priority: int
    created_by: str | None
    created_at: str | None
    updated_at: str | None


# ---------------------------------------------------------------------------
# Parser listing (reads from in-process registry)
# ---------------------------------------------------------------------------


@router.get("/admin/parsers")
def admin_list_parsers(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[ParserCapabilitiesOut]:
    require_admin(user)
    registry: ExtractorRegistry = request.app.state.extractor_registry
    result: list[ParserCapabilitiesOut] = []
    for caps in registry.list():
        result.append(
            ParserCapabilitiesOut(
                parser_name=caps.parser_name,
                parser_version=caps.parser_version,
                supported_mime_types=list(caps.supported_mime_types),
                quality_tier=caps.quality_tier.value,
                requires_ocr=caps.requires_ocr,
                max_file_size=caps.max_file_size,
            )
        )
    return result


@router.get("/admin/parsers/{parser_name}")
def admin_get_parser(
    parser_name: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ParserCapabilitiesOut:
    require_admin(user)
    registry: ExtractorRegistry = request.app.state.extractor_registry
    caps = registry.capabilities(parser_name)
    if caps is None:
        raise HTTPException(status_code=404, detail="Parser not found")
    return ParserCapabilitiesOut(
        parser_name=caps.parser_name,
        parser_version=caps.parser_version,
        supported_mime_types=list(caps.supported_mime_types),
        quality_tier=caps.quality_tier.value,
        requires_ocr=caps.requires_ocr,
        max_file_size=caps.max_file_size,
    )


# ---------------------------------------------------------------------------
# Document extraction history
# ---------------------------------------------------------------------------


@router.get("/admin/documents/{document_id}/extraction")
def admin_get_extraction(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ExtractionRecordOut:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = DocumentExtractionRepository(connection)
        record = repo.get_latest(document_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No extraction record — document may have been ingested before parser tracking"
                ),
            )
        return ExtractionRecordOut(
            id=record["id"],
            document_id=record["document_id"],
            parser_name=record["parser_name"],
            parser_version=record["parser_version"],
            duration_ms=record["duration_ms"],
            confidence=record["confidence"],
            warnings=record["warnings"],
            attempts=record["attempts"],
            created_at=record["created_at"],
        )


# ---------------------------------------------------------------------------
# Parser policy CRUD
# ---------------------------------------------------------------------------


@router.post("/admin/parser-policies", status_code=201)
def admin_create_policy(
    body: ParserPolicyIn,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ParserPolicyOut:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        # Validate source exists when specified
        if body.source_id is not None:
            exists = connection.execute(
                sa.text("SELECT id FROM ingestion_sources WHERE id = :id"),
                {"id": body.source_id.hex},
            ).scalar()
            if exists is None:
                raise HTTPException(status_code=404, detail="Source not found")

        # Validate every parser_name against the live registry
        registry: ExtractorRegistry = request.app.state.extractor_registry
        unknown = [p for p in body.parser_chain if registry.get_by_name(p) is None]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown parsers: {', '.join(unknown)}",
            )

        repo = ParserPolicyRepository(connection)
        policy_id = repo.create(
            source_id=body.source_id,
            mime_pattern=body.mime_pattern,
            parser_chain=body.parser_chain,
            options=body.options,
            enabled=body.enabled,
            priority=body.priority,
        )

        _audit_log(
            connection,
            user.sub,
            "create",
            "parser_policy",
            str(policy_id),
            details={
                "source_id": str(body.source_id) if body.source_id else None,
                "mime": body.mime_pattern,
            },
        )

        created = repo.get(policy_id)
        if created is None:
            raise RuntimeError(f"parser_policy missing after create: {policy_id}")
        return ParserPolicyOut(**created)


@router.get("/admin/parser-policies")
def admin_list_policies(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    source_id: UUID | None = None,
) -> list[ParserPolicyOut]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ParserPolicyRepository(connection)
        policies = repo.list(source_id=source_id)
        return [ParserPolicyOut(**p) for p in policies]


@router.get("/admin/parser-policies/{policy_id}")
def admin_get_policy(
    policy_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ParserPolicyOut:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ParserPolicyRepository(connection)
        policy = repo.get(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Parser policy not found")
        return ParserPolicyOut(**policy)


@router.patch("/admin/parser-policies/{policy_id}")
def admin_update_policy(
    policy_id: UUID,
    body: ParserPolicyUpdate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ParserPolicyOut:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ParserPolicyRepository(connection)

        existing = repo.get(policy_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Parser policy not found")

        update_fields = body.model_dump(exclude_unset=True)
        if not update_fields:
            return ParserPolicyOut(**existing)

        # Validate new parser chain against live registry
        if "parser_chain" in update_fields:
            registry: ExtractorRegistry = request.app.state.extractor_registry
            unknown = [p for p in update_fields["parser_chain"] if registry.get_by_name(p) is None]
            if unknown:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown parsers: {', '.join(unknown)}",
                )

        repo.update(policy_id, **update_fields)

        _audit_log(
            connection,
            user.sub,
            "update",
            "parser_policy",
            str(policy_id),
            details={
                "source_id": existing["source_id"],
                "mime": existing["mime_pattern"],
            },
        )

        updated = repo.get(policy_id)
        if updated is None:
            raise RuntimeError(f"parser_policy missing after update: {policy_id}")
        return ParserPolicyOut(**updated)


@router.delete("/admin/parser-policies/{policy_id}")
def admin_delete_policy(
    policy_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ParserPolicyRepository(connection)

        existing = repo.get(policy_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Parser policy not found")

        repo.delete(policy_id)

        _audit_log(
            connection,
            user.sub,
            "delete",
            "parser_policy",
            str(policy_id),
            details={
                "source_id": existing["source_id"],
                "mime": existing["mime_pattern"],
            },
        )

        return {"deleted": True, "id": str(policy_id)}
