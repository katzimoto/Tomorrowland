from __future__ import annotations

from uuid import UUID

from services.auth.models import TokenPayload, UserIdentity


def build_permission_filter(user: TokenPayload | UserIdentity) -> str:
    """Return the Meilisearch filter expression for the authenticated user.

    Cases:
    - Admin: empty string (no filter — admin sees all documents).
    - Non-admin with groups: ``allowed_group_ids IN ["id1", ...] AND is_admin_only = false``.
    - Non-admin with no groups: caller must check ``needs_acl_short_circuit``
      first and return empty results without querying Meilisearch.

    Only UUID values from the signed JWT are interpolated — no user-supplied
    strings reach the filter expression.
    """
    if user.is_admin:
        return ""

    group_ids = [str(g) for g in user.groups]
    if not group_ids:
        # Callers must check needs_acl_short_circuit() before calling this.
        # Returning a placeholder that matches nothing avoids an empty IN [] syntax error.
        return "is_admin_only = true AND is_admin_only = false"

    quoted = ", ".join(f'"{gid}"' for gid in group_ids)
    return f"allowed_group_ids IN [{quoted}] AND is_admin_only = false"


def build_permission_filter_for_ids(group_ids: list[str], *, is_admin: bool) -> str:
    """Build a Meilisearch ACL filter from pre-resolved effective group IDs.

    Use this instead of build_permission_filter() when the caller has already
    expanded transitive group membership (nested-groups support).
    """
    if is_admin:
        return ""
    if not group_ids:
        return "is_admin_only = true AND is_admin_only = false"
    quoted = ", ".join(f'"{gid}"' for gid in group_ids)
    return f"allowed_group_ids IN [{quoted}] AND is_admin_only = false"


def needs_acl_short_circuit(user: TokenPayload | UserIdentity) -> bool:
    """Return True when the query should be short-circuited to empty results.

    A non-admin user with no group memberships can never access any document
    (all documents require at least one group). Skipping the Meilisearch query
    is cheaper than sending a filter that matches nothing.
    """
    return not user.is_admin and not user.groups


def compose_filters(acl_filter: str, user_filter: str) -> str:
    """Compose the ACL filter with an optional user-supplied filter.

    The ACL filter is always placed first in AND position. If either part is
    empty the other is returned as-is (no spurious ``AND``).
    """
    parts = [f for f in (acl_filter, user_filter) if f]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " AND ".join(f"({p})" for p in parts)


def allowed_group_ids_for_indexing(groups: list[UUID]) -> list[str]:
    """Convert a list of UUID group IDs to the string format stored in the index.

    Mirrors ``get_allowed_groups`` from ``services.permissions.enforcer`` but
    returns strings rather than UUIDs, matching the ``SearchChunkRecord`` field type.
    """
    return [str(g) for g in groups]
