"""Admin routes for LDAP group search and mapping (#582).

Endpoints:
* GET  /admin/ldap/groups/search?q=...    — live LDAP group search (ephemeral)
* GET  /admin/ldap/group-mappings          — list explicit mappings
* POST /admin/ldap/group-mappings          — create a mapping
* DELETE /admin/ldap/group-mappings/{id}   — delete a mapping
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _audit_log
from services.api.main import current_user
from services.api.schemas import (
    CreateLdapGroupMappingRequest,
    LdapGroupMappingResponse,
    LdapGroupSearchResult,
)
from services.auth.ldap_client import LdapClient
from services.auth.ldap_group_mapping_repository import LdapGroupMappingRepository
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin

router = APIRouter(tags=["admin"])

_MAX_QUERY_LENGTH = 200


@router.get("/admin/ldap/groups/search", response_model=list[LdapGroupSearchResult])
def admin_ldap_group_search(
    q: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    """Search LDAP/DC groups live.  Results are ephemeral — never persisted."""
    require_admin(user)

    q = q.strip()
    if not q:
        return []
    if len(q) > _MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Search query must be at most {_MAX_QUERY_LENGTH} characters",
        )

    ldap_client: LdapClient | None = getattr(request.app.state, "ldap_client", None)
    if ldap_client is None:
        raise HTTPException(
            status_code=503,
            detail="LDAP is not configured on this server",
        )

    try:
        return ldap_client.search_groups(q)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LDAP group search failed: {_sanitize_ldap_error(exc)}",
        ) from exc


@router.get("/admin/ldap/group-mappings", response_model=list[LdapGroupMappingResponse])
def admin_list_ldap_group_mappings(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    """List all explicit LDAP group → Tomorrowland group mappings."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = LdapGroupMappingRepository(connection)
        return repo.list_mappings()


@router.post(
    "/admin/ldap/group-mappings",
    status_code=201,
    response_model=LdapGroupMappingResponse,
)
def admin_create_ldap_group_mapping(
    body: CreateLdapGroupMappingRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Map an LDAP group to an existing Tomorrowland group."""
    require_admin(user)

    with request.app.state.engine.begin() as connection:
        # Verify target group exists.
        target_uuid = UUID(body.target_group_id)
        group_row = connection.execute(
            sa.text("SELECT id FROM groups WHERE id = :id"),
            {"id": target_uuid.hex},
        ).first()
        if group_row is None:
            raise HTTPException(status_code=404, detail="Target group not found")

        repo = LdapGroupMappingRepository(connection)

        # Check duplicate DN.
        existing = repo.get_mapping_by_dn(body.ldap_dn)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="This LDAP group is already mapped",
            )

        try:
            mapping = repo.create_mapping(
                ldap_dn=body.ldap_dn,
                ldap_external_id_attr=body.ldap_external_id_attr,
                ldap_external_id=body.ldap_external_id,
                ldap_display_name=body.ldap_display_name,
                target_group_id=target_uuid,
                created_by=user.sub,
            )
        except sa.exc.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="This LDAP group is already mapped",
            ) from exc

        _audit_log(
            connection,
            user.sub,
            "create",
            "ldap_group_mapping",
            str(mapping["id"]),
            {
                "ldap_dn": body.ldap_dn,
                "target_group_id": body.target_group_id,
            },
        )
        return mapping


@router.delete("/admin/ldap/group-mappings/{mapping_id}", status_code=204)
def admin_delete_ldap_group_mapping(
    mapping_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    """Delete an LDAP group mapping.  Does not delete the Tomorrowland group."""
    require_admin(user)

    with request.app.state.engine.begin() as connection:
        repo = LdapGroupMappingRepository(connection)

        # Read mapping before deletion for the audit entry.
        row = connection.execute(
            sa.text("SELECT id, ldap_dn FROM ldap_group_mappings WHERE id = :id"),
            {"id": mapping_id.hex},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Mapping not found")

        deleted = repo.delete_mapping(mapping_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Mapping not found")

        _audit_log(
            connection,
            user.sub,
            "delete",
            "ldap_group_mapping",
            str(mapping_id),
            {"ldap_dn": row[1] if row else None},
        )


def _sanitize_ldap_error(exc: Exception) -> str:
    """Return a safe admin-facing error message for LDAP failures."""
    message = str(exc)
    # Strip any potential credentials from error messages.
    for sensitive in ("password", "bind", "credential"):
        if sensitive in message.lower():
            return "LDAP server error — check server logs for details"
    # Truncate long messages.
    if len(message) > 200:
        message = message[:197] + "..."
    return message
