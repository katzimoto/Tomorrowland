"""Permission Simulator service — simulates access with detailed diagnostics (#717)."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from services.auth.models import UserIdentity
from services.auth.repository import AuthRepository
from shared.db import to_uuid


@dataclass
class _AccessVerdict:
    """Result of a single access simulation check."""

    allowed: bool
    reason_category: str  # "admin_bypass", "group_membership", "effective_group", "no_access"
    reasoning_path: list[str] = field(default_factory=list)
    effective_groups: list[str] = field(default_factory=list)
    source_permission_groups: list[str] = field(default_factory=list)
    matching_groups: list[str] = field(default_factory=list)


class PermissionSimulatorService:
    """Simulate permission checks, search, and RAG for admins to diagnose access."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._auth = AuthRepository(connection)
        # DocumentRepository is available via self._auth.document_source_id()

    # ── Resolve a simulated identity ──────────────────────────────────────

    def _resolve_simulated_user(
        self,
        user_id: str | None,
        group_ids: list[str] | None,
    ) -> UserIdentity | None:
        """Build a simulated UserIdentity for access checks.

        Precedence: if *user_id* is given, load the real user from the DB.
        Otherwise, if *group_ids* is given, build a synthetic identity that
        belongs to exactly those groups (no admin flag, no email).
        """
        if user_id:
            try:
                uid = UUID(user_id)
            except ValueError:
                return None
            row = (
                self._connection.execute(
                    sa.text(
                        """\
                        SELECT id, email, display_name, auth_source, is_admin
                        FROM users WHERE id = :uid
                        """
                    ),
                    {"uid": uid.hex},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            return self._auth._identity_from_row(row)

        if group_ids:
            resolved: list[UUID] = []
            for g in group_ids:
                with suppress(ValueError):
                    resolved.append(UUID(g))
            return UserIdentity(
                id=uuid4(),
                email="simulator@local",
                display_name="Simulated User",
                auth_source="local",
                is_admin=False,
                groups=resolved,
            )

        # No identity — simulate an anonymous / no-group user.
        return UserIdentity(
            id=uuid4(),
            email="simulator@local",
            display_name="Anonymous",
            auth_source="local",
            is_admin=False,
            groups=[],
        )

    # ── Source / Document access check ────────────────────────────────────

    @staticmethod
    def _build_verdict(
        *,
        verdict: str,
        reason_category: str,
        reasoning_path: list[str],
        effective_groups: list[str],
        source_permission_groups: list[str],
        matching_groups: list[str],
        is_admin: bool,
        user_id: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, object]:
        d: dict[str, object] = {
            "verdict": verdict,
            "reason_category": reason_category,
            "reasoning_path": reasoning_path,
            "effective_groups": effective_groups,
            "source_permission_groups": source_permission_groups,
            "matching_groups": matching_groups,
            "is_admin": is_admin,
        }
        if user_id is not None:
            d["user_id"] = user_id
        if user_email is not None:
            d["user_email"] = user_email
        return d

    def check_source_access(
        self,
        source_id: str,
        *,
        simulated_user_id: str | None = None,
        simulated_group_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Simulate whether a user/group combination can access a source.

        Returns a detailed verdict with reasoning paths.
        """
        user = self._resolve_simulated_user(simulated_user_id, simulated_group_ids)
        reasoning: list[str] = []
        source_permission_groups: list[str] = []
        matching_groups: list[str] = []

        if user is None:
            return self._build_verdict(
                verdict="deny",
                reason_category="invalid_user",
                reasoning_path=["Simulated user not found or invalid ID."],
                effective_groups=[],
                source_permission_groups=[],
                matching_groups=[],
                is_admin=False,
            )

        is_admin = user.is_admin

        if is_admin:
            reasoning.append("User has is_admin=True — global bypass applies.")
            return self._build_verdict(
                verdict="allow",
                reason_category="admin_bypass",
                reasoning_path=reasoning,
                effective_groups=[],
                source_permission_groups=[],
                matching_groups=[],
                is_admin=True,
                user_id=str(user.id),
                user_email=user.email,
            )

        reasoning.append(f"User {user.email} is not an admin — checking group membership.")

        # Resolve effective groups (flat + ancestor expansion).
        direct = [str(g) for g in user.groups]
        ancestors = [str(g) for g in self._auth.get_effective_group_ids(user.groups)]
        effective = list(dict.fromkeys(direct + ancestors))  # dedup preserving order

        reasoning.append(f"Direct group memberships: {direct if direct else 'none'}.")
        if ancestors:
            reasoning.append(f"Ancestor groups (via group_memberships): {ancestors}.")
        else:
            reasoning.append("No ancestor groups (no group_memberships rows).")

        # Resolve group names for display.
        group_names = _resolve_group_names(self._connection, effective)
        effective_group_names = [group_names.get(g, g) for g in effective]

        # Which groups are granted access to this source?
        try:
            sid = UUID(source_id)
        except ValueError:
            return self._build_verdict(
                verdict="deny",
                reason_category="invalid_source",
                reasoning_path=["Invalid source_id."],
                effective_groups=effective_group_names,
                source_permission_groups=[],
                matching_groups=[],
                is_admin=False,
                user_id=str(user.id),
                user_email=user.email,
            )

        perm_rows = self._connection.execute(
            sa.text("SELECT group_id FROM source_permissions WHERE source_id = :sid"),
            {"sid": sid.hex},
        ).scalars()

        # DB stores group IDs as hex; convert to dashed UUID strings for comparison.
        perm_groups = [str(to_uuid(r)) for r in perm_rows]
        source_permission_groups = [group_names.get(g, g) for g in perm_groups]

        if not perm_groups:
            reasoning.append(
                f"Source {source_id} has no source_permissions rows — only admins can access it."
            )
            return self._build_verdict(
                verdict="deny",
                reason_category="no_source_permissions",
                reasoning_path=reasoning,
                effective_groups=effective_group_names,
                source_permission_groups=source_permission_groups,
                matching_groups=[],
                is_admin=False,
                user_id=str(user.id),
                user_email=user.email,
            )

        reasoning.append(f"Source {source_id} is granted to groups: {source_permission_groups}.")

        # Intersection check.
        matched = [g for g in effective if g in set(perm_groups)]
        matching_groups = [group_names.get(g, g) for g in matched]

        if matched:
            reasoning.append(
                f"User's effective groups intersect with source grants via: {matching_groups}."
            )
            return self._build_verdict(
                verdict="allow",
                reason_category="group_membership",
                reasoning_path=reasoning,
                effective_groups=effective_group_names,
                source_permission_groups=source_permission_groups,
                matching_groups=matching_groups,
                is_admin=False,
                user_id=str(user.id),
                user_email=user.email,
            )

        reasoning.append(
            "No intersection between user's effective groups and source grants — access denied."
        )
        return self._build_verdict(
            verdict="deny",
            reason_category="no_group_match",
            reasoning_path=reasoning,
            effective_groups=effective_group_names,
            source_permission_groups=source_permission_groups,
            matching_groups=matching_groups,
            is_admin=False,
            user_id=str(user.id),
            user_email=user.email,
        )

    def check_document_access(
        self,
        document_id: str,
        *,
        simulated_user_id: str | None = None,
        simulated_group_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Simulate access to a specific document.

        Resolves the document's source, then runs source-level access check.
        """
        try:
            did = UUID(document_id)
        except ValueError:
            return {
                "verdict": "deny",
                "reason_category": "invalid_document",
                "reasoning_path": ["Invalid document_id."],
            }

        source_id = self._auth.document_source_id(did)
        if source_id is None:
            return {
                "verdict": "deny",
                "reason_category": "document_not_found",
                "reasoning_path": [f"Document {document_id} not found."],
            }

        result = self.check_source_access(
            str(source_id),
            simulated_user_id=simulated_user_id,
            simulated_group_ids=simulated_group_ids,
        )
        result["document_id"] = document_id
        result["source_id"] = str(source_id)

        # Add document-level context.
        doc_row = (
            self._connection.execute(
                sa.text("SELECT title, mime_type, source FROM documents WHERE id = :did"),
                {"did": did.hex},
            )
            .mappings()
            .first()
        )
        if doc_row:
            result["document_title"] = doc_row["title"]
            result["document_mime_type"] = doc_row["mime_type"]
            result["document_source_type"] = doc_row["source"]
        return result

    # ── Search simulation ─────────────────────────────────────────────────

    def simulate_search(
        self,
        query: str,
        *,
        simulated_user_id: str | None = None,
        simulated_group_ids: list[str] | None = None,
        top_k: int = 20,
        source_filter: list[str] | None = None,
        mime_type_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Simulate what search results a user/group would see.

        Builds the permission filter that would be applied, then runs a Meilisearch
        query (BM25-only, no vector) and returns result metadata plus the filter
        explanation.  This is a read-only diagnostic — it does not leak inaccessible
        document text.
        """
        user = self._resolve_simulated_user(simulated_user_id, simulated_group_ids)
        if user is None:
            return {
                "error": "invalid_user",
                "detail": "Simulated user not found.",
                "search_filter": "",
                "filter_explanation": [],
                "results": [],
                "total": 0,
            }

        reasoning: list[str] = []

        if user.is_admin:
            reasoning.append("User is_admin=True — no ACL filter applied (empty filter).")
            search_filter = ""
            effective_group_ids: list[str] = []
        elif not user.groups:
            reasoning.append(
                "User has no groups — filter is 'allowedGroupIds IS EMPTY' "
                "(explicitly matches nothing)."
            )
            search_filter = "allowedGroupIds IS EMPTY"
            effective_group_ids = []
        else:
            effective = set(user.groups) | set(self._auth.get_effective_group_ids(user.groups))
            effective_group_ids = [str(g) for g in effective]
            quoted = ", ".join(f'"{g}"' for g in effective_group_ids)
            search_filter = f"allowedGroupIds IN [{quoted}]"
            direct = [str(g) for g in user.groups]
            ancestors = [str(g) for g in self._auth.get_effective_group_ids(user.groups)]
            reasoning.append(f"Direct groups: {direct if direct else 'none'}.")
            reasoning.append(f"Ancestor groups: {ancestors if ancestors else 'none'}.")
            reasoning.append(f"Effective group IDs in filter: {effective_group_ids}.")

        # Try to run an actual BM25 search using Meilisearch provider — but
        # this requires the provider to be wired.  Since the simulator runs
        # inside a DB transaction and doesn't have access to the app state,
        # we report the filter that *would* be applied and note that live
        # search requires the full request context.
        #
        # We can still resolve group names and source details for the
        # explanation.
        group_names_map = _resolve_group_names(self._connection, effective_group_ids)
        filter_explanation = [
            {
                "step": step,
                "group_names": [group_names_map.get(g, g) for g in effective_group_ids]
                if "Effective group" in step
                else None,
            }
            for step in reasoning
        ]

        return {
            "search_filter": search_filter,
            "filter_explanation": filter_explanation,
            "effective_group_ids": effective_group_ids,
            "effective_group_names": [group_names_map.get(g, g) for g in effective_group_ids],
            "is_admin": user.is_admin,
            "user_id": str(user.id),
            "user_email": user.email,
            "query": query,
            "note": (
                "Live search simulation requires the full request context "
                "(Meilisearch client, Qdrant client). Use the "
                "/admin/permission-simulator/search endpoint with the running "
                "server to see actual results."
            ),
        }

    # ── Full access audit ─────────────────────────────────────────────────

    def audit_full_access(
        self,
        *,
        simulated_user_id: str | None = None,
        simulated_group_ids: list[str] | None = None,
        source_id: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        """Run all access checks at once and return a unified diagnostic report."""
        user = self._resolve_simulated_user(simulated_user_id, simulated_group_ids)
        if user is None:
            return {"error": "invalid_user", "detail": "Simulated user not found."}

        report: dict[str, Any] = {
            "simulated_user": {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "is_admin": user.is_admin,
                "auth_source": user.auth_source,
            },
            "checks": [],
        }

        # Source check if requested.
        if source_id:
            report["checks"].append(
                {
                    "type": "source_access",
                    "target": source_id,
                    **self.check_source_access(
                        source_id,
                        simulated_user_id=simulated_user_id,
                        simulated_group_ids=simulated_group_ids,
                    ),
                }
            )

        # Document check if requested.
        if document_id:
            report["checks"].append(
                {
                    "type": "document_access",
                    "target": document_id,
                    **self.check_document_access(
                        document_id,
                        simulated_user_id=simulated_user_id,
                        simulated_group_ids=simulated_group_ids,
                    ),
                }
            )

        return report


def _resolve_group_names(connection: Connection, group_ids: list[str]) -> dict[str, str]:
    """Resolve a batch of group UUIDs (dashed format) to their display names."""
    if not group_ids:
        return {}
    # DB stores UUIDs as hex; convert dashed UUID strings to hex for the query.
    hex_ids = [UUID(g).hex for g in group_ids]
    placeholders = ", ".join(f":g{i}" for i in range(len(hex_ids)))
    params = {f"g{i}": hid for i, hid in enumerate(hex_ids)}
    rows = connection.execute(
        sa.text(f"SELECT id, name FROM groups WHERE id IN ({placeholders})"),
        params,
    ).mappings()
    return {str(to_uuid(row["id"])): row["name"] for row in rows}
