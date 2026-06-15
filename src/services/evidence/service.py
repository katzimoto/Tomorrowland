"""Permission-enforcing service layer for evidence packs.

This layer is the security boundary for evidence packs:

* Packs are strictly owner-scoped. A non-owner — including an admin who does
  not own the pack — gets a 404, which avoids leaking the existence of other
  users' packs.
* Adding a document-anchored item requires *current* access to that document
  (``assert_doc_access``).
* Reading or exporting a pack filters out items whose document the caller can
  no longer access, so a stored excerpt never leaks after access is revoked or
  the document is deleted.

Audit logging is performed by the router (the API layer that owns the request
context), mirroring every other ``_audit_log`` call site in the codebase.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.engine import Connection

from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.evidence.models import (
    EvidencePack,
    EvidencePackCreateRequest,
    EvidencePackItem,
    EvidencePackItemCreateRequest,
    EvidencePackItemFromCitationRequest,
    EvidencePackUpdateRequest,
)
from services.evidence.repository import EvidencePackRepository
from services.permissions.enforcer import assert_doc_access


class EvidencePackService:
    """Owner-scoped, permission-first operations over evidence packs."""

    def __init__(self, connection: Connection) -> None:
        self._repo = EvidencePackRepository(connection)
        self._auth = AuthRepository(connection)

    # ------------------------------------------------------------------
    # Packs
    # ------------------------------------------------------------------

    def create_pack(self, user: TokenPayload, req: EvidencePackCreateRequest) -> EvidencePack:
        """Create a pack owned by *user*."""
        return self._repo.create_pack(
            owner_user_id=user.sub,
            title=req.title,
            created_from=req.created_from,
            description=req.description,
            source_scope=req.source_scope,
            metadata=req.metadata,
        )

    def list_packs(self, user: TokenPayload) -> list[EvidencePack]:
        """List packs owned by *user*."""
        return self._repo.list_packs(user.sub)

    def get_pack_detail(
        self, user: TokenPayload, pack_id: UUID
    ) -> tuple[EvidencePack, list[EvidencePackItem]]:
        """Return an owned pack with only the items the caller can still access."""
        pack = self._load_owned_pack(user, pack_id)
        items = [
            item
            for item in self._repo.list_items(pack_id)
            if self._can_access_document(user, item.document_id)
        ]
        return pack, items

    def update_pack(
        self, user: TokenPayload, pack_id: UUID, req: EvidencePackUpdateRequest
    ) -> EvidencePack:
        """Update an owned pack's title/description/scope/metadata."""
        self._load_owned_pack(user, pack_id)
        self._repo.update_pack(
            pack_id,
            title=req.title,
            description=req.description,
            source_scope=req.source_scope,
            metadata=req.metadata,
        )
        updated = self._repo.get_pack(pack_id)
        if updated is None:  # pragma: no cover - just deleted concurrently
            raise HTTPException(status_code=404, detail="Evidence pack not found")
        return updated

    def delete_pack(self, user: TokenPayload, pack_id: UUID) -> None:
        """Delete an owned pack (items cascade)."""
        self._load_owned_pack(user, pack_id)
        self._repo.delete_pack(pack_id)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def add_item(
        self, user: TokenPayload, pack_id: UUID, req: EvidencePackItemCreateRequest
    ) -> EvidencePackItem:
        """Add an item to an owned pack after verifying document access."""
        self._load_owned_pack(user, pack_id)
        # Raises 404 (unknown document) or 403 (no access) before anything is
        # persisted — an inaccessible document can never become a pack item.
        assert_doc_access(req.document_id, user, self._auth)
        item = self._repo.add_item(
            evidence_pack_id=pack_id,
            document_id=req.document_id,
            item_type=req.item_type,
            text_excerpt=req.text_excerpt,
            chunk_id=req.chunk_id,
            citation_id=req.citation_id,
            page_number=req.page_number,
            section_heading=req.section_heading,
            translated_text=req.translated_text,
            claim=req.claim,
            text_lane=req.text_lane,
            translated_from=req.translated_from,
            matched_text_kind=req.matched_text_kind,
            translation_version_id=req.translation_version_id,
            translation_quality=req.translation_quality,
            translation_validation_status=req.translation_validation_status,
        )
        self._repo.touch_pack(pack_id)
        return item

    def add_item_from_citation(
        self, user: TokenPayload, pack_id: UUID, req: EvidencePackItemFromCitationRequest
    ) -> EvidencePackItem:
        """Add an item from a citation payload (same permission checks as add_item)."""
        return self.add_item(user, pack_id, req.to_item_request())

    def remove_item(self, user: TokenPayload, pack_id: UUID, item_id: UUID) -> EvidencePackItem:
        """Remove an item from an owned pack and return the removed row."""
        self._load_owned_pack(user, pack_id)
        item = self._repo.get_item(item_id)
        if item is None or item.evidence_pack_id != pack_id:
            raise HTTPException(status_code=404, detail="Evidence pack item not found")
        self._repo.remove_item(item_id)
        self._repo.touch_pack(pack_id)
        return item

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def _load_owned_pack(self, user: TokenPayload, pack_id: UUID) -> EvidencePack:
        """Return the pack only if *user* owns it, else raise 404.

        A 404 (rather than 403) is deliberate: it prevents a caller from
        probing for the existence of other users' packs by id.
        """
        pack = self._repo.get_pack(pack_id)
        if pack is None or pack.owner_user_id != user.sub:
            raise HTTPException(status_code=404, detail="Evidence pack not found")
        return pack

    def _can_access_document(self, user: TokenPayload, document_id: UUID) -> bool:
        """Whether *user* can currently access *document_id*'s source."""
        if user.is_admin:
            return True
        source_id = self._auth.document_source_id(document_id)
        if source_id is None:
            return False
        return self._auth.user_can_access_source(user, source_id)  # type: ignore[arg-type]
