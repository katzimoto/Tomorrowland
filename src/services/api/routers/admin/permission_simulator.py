"""Admin endpoints for Permission Simulator — simulate access and explain verdicts (#717)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from services.api.main import current_user
from services.api.routers.admin.permission_simulator_service import (
    PermissionSimulatorService,
)
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from services.search.meili_types import DocumentSearchFilters, DocumentSearchQuery

router = APIRouter(tags=["admin"])


@router.post("/admin/permission-simulator/check-source")
def check_source_access(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Simulate source access for a user/group combination.

    Payload:
        {
            "source_id": "<uuid>",
            "user_id": "<uuid>" | null,
            "group_ids": ["<uuid>", ...] | null
        }

    Provide *user_id* to simulate a real user, or *group_ids* to simulate
    a synthetic user belonging to those groups.  If neither is provided,
    simulates a no-group anonymous user.
    """
    require_admin(user)

    source_id = payload.get("source_id")
    if not source_id or not isinstance(source_id, str):
        raise HTTPException(status_code=422, detail="source_id is required")

    simulated_user_id = payload.get("user_id")
    if simulated_user_id is not None and not isinstance(simulated_user_id, str):
        raise HTTPException(status_code=422, detail="user_id must be a string or null")

    simulated_group_ids = payload.get("group_ids")
    if simulated_group_ids is not None and not isinstance(simulated_group_ids, list):
        raise HTTPException(status_code=422, detail="group_ids must be a list or null")

    with request.app.state.engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        return service.check_source_access(
            source_id,
            simulated_user_id=simulated_user_id,
            simulated_group_ids=simulated_group_ids,
        )


@router.post("/admin/permission-simulator/check-document")
def check_document_access(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Simulate document access for a user/group combination.

    Payload:
        {
            "document_id": "<uuid>",
            "user_id": "<uuid>" | null,
            "group_ids": ["<uuid>", ...] | null
        }
    """
    require_admin(user)

    document_id = payload.get("document_id")
    if not document_id or not isinstance(document_id, str):
        raise HTTPException(status_code=422, detail="document_id is required")

    simulated_user_id = payload.get("user_id")
    if simulated_user_id is not None and not isinstance(simulated_user_id, str):
        raise HTTPException(status_code=422, detail="user_id must be a string or null")

    simulated_group_ids = payload.get("group_ids")
    if simulated_group_ids is not None and not isinstance(simulated_group_ids, list):
        raise HTTPException(status_code=422, detail="group_ids must be a list or null")

    with request.app.state.engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        return service.check_document_access(
            document_id,
            simulated_user_id=simulated_user_id,
            simulated_group_ids=simulated_group_ids,
        )


@router.post("/admin/permission-simulator/search")
def simulate_search(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Simulate search with a user/group's permission filter.

    Payload:
        {
            "query": "search terms",
            "user_id": "<uuid>" | null,
            "group_ids": ["<uuid>", ...] | null,
            "top_k": 20,
            "source_filter": ["folder"] | null,
            "mime_type_filter": ["application/pdf"] | null
        }

    Returns the Meilisearch ACL filter that would be applied and explanation
    of the group resolution.  When the running server has a Meilisearch client
    wired, also returns actual BM25 search results (safe metadata only — no
    inaccessible text is leaked).
    """
    require_admin(user)

    query = payload.get("query", "")
    if not isinstance(query, str):
        raise HTTPException(status_code=422, detail="query must be a string")

    simulated_user_id = payload.get("user_id")
    if simulated_user_id is not None and not isinstance(simulated_user_id, str):
        raise HTTPException(status_code=422, detail="user_id must be a string or null")

    simulated_group_ids = payload.get("group_ids")
    if simulated_group_ids is not None and not isinstance(simulated_group_ids, list):
        raise HTTPException(status_code=422, detail="group_ids must be a list or null")

    top_k = payload.get("top_k", 20)
    if not isinstance(top_k, int) or top_k < 1:
        top_k = 20

    source_filter = payload.get("source_filter")
    if source_filter is not None and not isinstance(source_filter, list):
        source_filter = None

    mime_type_filter = payload.get("mime_type_filter")
    if mime_type_filter is not None and not isinstance(mime_type_filter, list):
        mime_type_filter = None

    # First, build the permission filter and explanation.
    with request.app.state.engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        report = service.simulate_search(
            query,
            simulated_user_id=simulated_user_id,
            simulated_group_ids=simulated_group_ids,
            top_k=top_k,
            source_filter=source_filter,
            mime_type_filter=mime_type_filter,
        )

    # Try running an actual Meilisearch query if the provider is available.
    meili_provider = getattr(request.app.state, "meili_provider", None)
    if meili_provider is not None and query.strip():
        try:
            filters = DocumentSearchFilters()
            if source_filter:
                filters.source = source_filter
            if mime_type_filter:
                filters.mime_type = mime_type_filter

            # Build a minimal payload matching what meili_provider.search expects.
            # It only accesses .is_admin and .groups for ACL filter construction.
            class _SimPayload:
                is_admin = report.get("is_admin", False)
                groups: list[UUID] = [UUID(g) for g in report.get("effective_group_ids", [])]
                sub = ""

            sim_payload = _SimPayload()

            meili_response = meili_provider.search(
                query=DocumentSearchQuery(
                    q=query,
                    limit=top_k,
                    filters=filters,
                    sort="relevance",
                ),
                user=sim_payload,
            )

            report["bm25_results"] = [
                {
                    "document_id": r.document_id,
                    "title": r.title,
                    "score": r.score,
                    "chunk_index": r.chunk_index,
                }
                for r in meili_response.results
            ]
            report["bm25_total"] = meili_response.total
        except Exception as exc:
            report["bm25_error"] = f"Meilisearch query failed: {exc}"

    return report


@router.post("/admin/permission-simulator/audit")
def audit_access(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Run a full access audit for a simulated user/group across sources and documents.

    Payload:
        {
            "user_id": "<uuid>" | null,
            "group_ids": ["<uuid>", ...] | null,
            "source_id": "<uuid>" | null,
            "document_id": "<uuid>" | null
        }

    At least one of *source_id* or *document_id* must be provided.
    """
    require_admin(user)

    def _require_optional(payload: dict[str, object], key: str, expected: type) -> Any | None:
        value = payload.get(key)
        if value is not None and not isinstance(value, expected):
            raise HTTPException(
                status_code=422,
                detail=f"{key} must be a {expected.__name__} or null",
            )
        return value

    simulated_user_id = _require_optional(payload, "user_id", str)
    simulated_group_ids = _require_optional(payload, "group_ids", list)
    source_id = _require_optional(payload, "source_id", str)
    document_id = _require_optional(payload, "document_id", str)

    if not source_id and not document_id:
        raise HTTPException(
            status_code=422,
            detail="At least one of source_id or document_id is required",
        )

    with request.app.state.engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        return service.audit_full_access(
            simulated_user_id=simulated_user_id,
            simulated_group_ids=simulated_group_ids,
            source_id=source_id,
            document_id=document_id,
        )
