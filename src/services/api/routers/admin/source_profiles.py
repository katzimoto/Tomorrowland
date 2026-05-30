"""Admin API for SourceProfile management.

Endpoints:
- POST   /admin/source-profiles
- GET    /admin/source-profiles
- GET    /admin/source-profiles/{id}
- PATCH  /admin/source-profiles/{id}
- POST   /admin/source-profiles/{id}/activate
- POST   /admin/source-profiles/{id}/deprecate
- DELETE /admin/source-profiles/{id}
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from services.api._helpers import _audit_log
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.intelligence.profile_repository import ProfileRepository
from services.permissions.enforcer import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class _ProfileCreate(BaseModel):
    source_id: UUID
    name: str
    domain_type: str = Field(pattern=r"^(legal|engineering|logs|email|spreadsheet|generic)$")
    chunking_strategy: str = Field(
        pattern=r"^(paragraph|clause|heading|row|thread|page|code_block|default)$"
    )
    retrieval_strategy: str = Field(
        pattern=r"^(hybrid|vector_only|keyword_only|metadata_first|default)$"
    )
    extraction_strategy: str = Field(
        pattern=r"^(full_text|ocr_required|table_aware|header_metadata|default)$"
    )
    status: str = Field(default="draft", pattern=r"^(draft|active|needs_review|deprecated)$")
    model_policy_provider_id: UUID | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    created_by: str | None = None
    approved_by: str | None = None


class _ProfileUpdate(BaseModel):
    name: str | None = None
    domain_type: str | None = Field(
        default=None, pattern=r"^(legal|engineering|logs|email|spreadsheet|generic)$"
    )
    chunking_strategy: str | None = Field(
        default=None, pattern=r"^(paragraph|clause|heading|row|thread|page|code_block|default)$"
    )
    retrieval_strategy: str | None = Field(
        default=None,
        pattern=r"^(hybrid|vector_only|keyword_only|metadata_first|default)$",
    )
    extraction_strategy: str | None = Field(
        default=None,
        pattern=r"^(full_text|ocr_required|table_aware|header_metadata|default)$",
    )
    status: str | None = Field(default=None, pattern=r"^(draft|active|needs_review|deprecated)$")
    model_policy_provider_id: UUID | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    created_by: str | None = None
    approved_by: str | None = None
    version: int | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/admin/source-profiles", status_code=201)
def admin_create_profile(
    body: _ProfileCreate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        # Verify source exists
        source_exists = connection.execute(
            sa.text("SELECT id FROM ingestion_sources WHERE id = :id"),
            {"id": body.source_id.hex},
        ).scalar()
        if source_exists is None:
            raise HTTPException(status_code=404, detail="Source not found")

        # Verify model provider exists if specified
        if body.model_policy_provider_id is not None:
            provider_exists = connection.execute(
                sa.text("SELECT id FROM model_providers WHERE id = :id"),
                {"id": body.model_policy_provider_id.hex},
            ).scalar()
            if provider_exists is None:
                raise HTTPException(status_code=404, detail="Model policy provider not found")

        repo = ProfileRepository(connection)
        profile_id = repo.create_profile(
            source_id=body.source_id,
            name=body.name,
            domain_type=body.domain_type,
            chunking_strategy=body.chunking_strategy,
            retrieval_strategy=body.retrieval_strategy,
            extraction_strategy=body.extraction_strategy,
            status=body.status,
            model_policy_provider_id=body.model_policy_provider_id,
            description=body.description,
            config=body.config,
            created_by=body.created_by or (str(user.sub) if user.sub else None),
            approved_by=body.approved_by,
        )

        _audit_log(
            connection,
            user.sub,
            "create",
            "source_profile",
            str(profile_id),
            details={
                "source_id": str(body.source_id),
                "domain_type": body.domain_type,
                "created_by": body.created_by,
            },
        )

        profile = repo.get_profile(profile_id)
        assert profile is not None
        return profile


@router.get("/admin/source-profiles")
def admin_list_profiles(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    source_id: UUID | None = None,
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ProfileRepository(connection)
        return repo.list_profiles(source_id=source_id)


@router.get("/admin/source-profiles/{profile_id}")
def admin_get_profile(
    profile_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ProfileRepository(connection)
        profile = repo.get_profile(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="SourceProfile not found")
        return profile


@router.patch("/admin/source-profiles/{profile_id}")
def admin_update_profile(
    profile_id: UUID,
    body: _ProfileUpdate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ProfileRepository(connection)

        existing = repo.get_profile(profile_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="SourceProfile not found")

        # Verify model provider exists if specified
        if body.model_policy_provider_id is not None:
            provider_exists = connection.execute(
                sa.text("SELECT id FROM model_providers WHERE id = :id"),
                {"id": body.model_policy_provider_id.hex},
            ).scalar()
            if provider_exists is None:
                raise HTTPException(status_code=404, detail="Model policy provider not found")

        update_fields = body.model_dump(exclude_unset=True)
        if not update_fields:
            return existing

        try:
            repo.update_profile(profile_id, **update_fields)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        _audit_log(
            connection,
            user.sub,
            "update",
            "source_profile",
            str(profile_id),
        )

        updated = repo.get_profile(profile_id)
        assert updated is not None
        return updated


@router.post("/admin/source-profiles/{profile_id}/activate")
def admin_activate_profile(
    profile_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ProfileRepository(connection)

        existing = repo.get_profile(profile_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="SourceProfile not found")

        if existing["status"] == "active":
            return existing

        try:
            repo.activate_profile(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _audit_log(
            connection,
            user.sub,
            "activate",
            "source_profile",
            str(profile_id),
            details={
                "source_id": existing["source_id"],
                "domain_type": existing["domain_type"],
                "previous_status": existing["status"],
            },
        )

        updated = repo.get_profile(profile_id)
        assert updated is not None
        return updated


@router.post("/admin/source-profiles/{profile_id}/deprecate")
def admin_deprecate_profile(
    profile_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ProfileRepository(connection)

        existing = repo.get_profile(profile_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="SourceProfile not found")

        if existing["status"] == "deprecated":
            return existing

        previous_status = existing["status"]
        repo.deprecate_profile(profile_id)

        _audit_log(
            connection,
            user.sub,
            "deprecate",
            "source_profile",
            str(profile_id),
            details={
                "source_id": existing["source_id"],
                "domain_type": existing["domain_type"],
                "previous_status": previous_status,
            },
        )

        updated = repo.get_profile(profile_id)
        assert updated is not None
        return updated


@router.delete("/admin/source-profiles/{profile_id}")
def admin_delete_profile(
    profile_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ProfileRepository(connection)

        existing = repo.get_profile(profile_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="SourceProfile not found")

        try:
            repo.delete_profile(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        _audit_log(
            connection,
            user.sub,
            "delete",
            "source_profile",
            str(profile_id),
            details={
                "source_id": existing["source_id"],
                "domain_type": existing["domain_type"],
            },
        )

        return {"deleted": True, "id": str(profile_id)}
