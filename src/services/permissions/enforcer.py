from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from services.auth.models import TokenPayload, UserIdentity
from services.auth.repository import AuthRepository


def require_admin(user: TokenPayload | UserIdentity) -> None:
    """Raise 403 unless the user has admin privileges."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")


def get_allowed_groups(user: TokenPayload | UserIdentity) -> list[UUID]:
    """Return the group IDs carried by the authenticated user context."""
    return list(user.groups)


def assert_source_access(source_id: UUID, user: UserIdentity, repository: AuthRepository) -> None:
    """Raise 403 unless the user can access a source through source grants."""
    if not repository.user_can_access_source(user, source_id):
        raise HTTPException(status_code=403, detail="Source access denied")


def assert_doc_access(doc_id: UUID, user: UserIdentity, repository: AuthRepository) -> None:
    """Raise 403 unless the user can access the document's source."""
    source_id = repository.document_source_id(doc_id)
    if source_id is None:
        raise HTTPException(status_code=404, detail="Document not found")
    assert_source_access(source_id, user, repository)
