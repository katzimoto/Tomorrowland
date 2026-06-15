"""Evidence pack API — durable, auditable collections of cited evidence.

All endpoints are user-scoped: a caller can only see and mutate packs they own
(see :class:`services.evidence.service.EvidencePackService`). Every mutating
action writes an ``audit_log`` row via :func:`_audit_log`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from services.api._helpers import _audit_log, _fmt_dt
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.evidence.models import (
    EvidencePack,
    EvidencePackCreateRequest,
    EvidencePackItem,
    EvidencePackItemCreateRequest,
    EvidencePackItemFromCitationRequest,
    EvidencePackUpdateRequest,
)
from services.evidence.service import EvidencePackService
from shared.request_context import get_request_id

router = APIRouter(prefix="/evidence-packs", tags=["evidence-packs"])


def _pack_response(pack: EvidencePack) -> dict[str, Any]:
    return {
        "id": str(pack.id),
        "owner_user_id": str(pack.owner_user_id),
        "title": pack.title,
        "description": pack.description,
        "source_scope": pack.source_scope,
        "created_from": pack.created_from,
        "metadata": pack.metadata,
        "created_at": _fmt_dt(pack.created_at),
        "updated_at": _fmt_dt(pack.updated_at),
    }


def _item_response(item: EvidencePackItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "evidence_pack_id": str(item.evidence_pack_id),
        "document_id": str(item.document_id),
        "item_type": item.item_type,
        "text_excerpt": item.text_excerpt,
        "chunk_id": item.chunk_id,
        "citation_id": item.citation_id,
        "page_number": item.page_number,
        "section_heading": item.section_heading,
        "translated_text": item.translated_text,
        "claim": item.claim,
        "text_lane": item.text_lane,
        "translated_from": item.translated_from,
        "matched_text_kind": item.matched_text_kind,
        "translation_version_id": item.translation_version_id,
        "translation_quality": item.translation_quality,
        "translation_validation_status": item.translation_validation_status,
        "created_at": _fmt_dt(item.created_at),
    }


def _audit_pack_action(
    connection: Any,
    user: TokenPayload,
    action: str,
    pack_id: UUID,
    *,
    item_id: UUID | None = None,
    document_id: UUID | None = None,
) -> None:
    """Write an audit_log row for an evidence-pack mutation.

    ``details`` carries the correlation/request id plus the item and document
    ids when relevant — never any document text.
    """
    details: dict[str, Any] = {"request_id": get_request_id()}
    if item_id is not None:
        details["item_id"] = str(item_id)
    if document_id is not None:
        details["document_id"] = str(document_id)
    _audit_log(connection, user.sub, action, "evidence_pack", str(pack_id), details)


# ---------------------------------------------------------------------------
# Packs
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
def create_pack(
    body: EvidencePackCreateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        pack = service.create_pack(user, body)
        _audit_pack_action(connection, user, "create", pack.id)
        return _pack_response(pack)


@router.get("")
def list_packs(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        packs = service.list_packs(user)
        return {"items": [_pack_response(p) for p in packs]}


@router.get("/{pack_id}")
def get_pack(
    pack_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        pack, items = service.get_pack_detail(user, pack_id)
        return {**_pack_response(pack), "items": [_item_response(i) for i in items]}


@router.patch("/{pack_id}")
def update_pack(
    pack_id: UUID,
    body: EvidencePackUpdateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        pack = service.update_pack(user, pack_id, body)
        _audit_pack_action(connection, user, "update", pack.id)
        return _pack_response(pack)


@router.delete("/{pack_id}", status_code=204)
def delete_pack(
    pack_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        service.delete_pack(user, pack_id)
        _audit_pack_action(connection, user, "delete", pack_id)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


@router.post("/{pack_id}/items", status_code=201)
def add_item(
    pack_id: UUID,
    body: EvidencePackItemCreateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        item = service.add_item(user, pack_id, body)
        _audit_pack_action(
            connection, user, "item_add", pack_id, item_id=item.id, document_id=item.document_id
        )
        return _item_response(item)


@router.post("/{pack_id}/items/from-citation", status_code=201)
def add_item_from_citation(
    pack_id: UUID,
    body: EvidencePackItemFromCitationRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        item = service.add_item_from_citation(user, pack_id, body)
        _audit_pack_action(
            connection, user, "item_add", pack_id, item_id=item.id, document_id=item.document_id
        )
        return _item_response(item)


@router.delete("/{pack_id}/items/{item_id}", status_code=204)
def remove_item(
    pack_id: UUID,
    item_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        item = service.remove_item(user, pack_id, item_id)
        _audit_pack_action(
            connection, user, "item_remove", pack_id, item_id=item.id, document_id=item.document_id
        )


# ---------------------------------------------------------------------------
# Export (minimal; excludes items the caller can no longer access)
# ---------------------------------------------------------------------------


def _render_markdown(pack: dict[str, Any], items: list[dict[str, Any]]) -> str:
    lines = [f"# {pack['title']}", ""]
    if pack.get("description"):
        lines += [str(pack["description"]), ""]
    for idx, item in enumerate(items, start=1):
        lines.append(f"## {idx}. {item['item_type']}")
        if item.get("section_heading"):
            lines.append(f"*{item['section_heading']}*")
        if item.get("page_number") is not None:
            lines.append(f"Page: {item['page_number']}")
        lines += ["", f"> {item['text_excerpt']}", ""]
        if item.get("translated_text"):
            lines += [f"> _(translated)_ {item['translated_text']}", ""]
        if item.get("claim"):
            lines += [f"**Claim:** {item['claim']}", ""]
    return "\n".join(lines)


@router.get("/{pack_id}/export")
def export_pack(
    pack_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    export_format: Annotated[Literal["json", "markdown"], Query(alias="format")] = "json",
) -> Any:
    """Minimal pack export. Only items the caller can still access are included."""
    with request.app.state.engine.begin() as connection:
        service = EvidencePackService(connection)
        pack, items = service.get_pack_detail(user, pack_id)
        pack_dict = _pack_response(pack)
        item_dicts = [_item_response(i) for i in items]
        if export_format == "markdown":
            return PlainTextResponse(
                _render_markdown(pack_dict, item_dicts),
                media_type="text/markdown",
            )
        return {**pack_dict, "items": item_dicts}
