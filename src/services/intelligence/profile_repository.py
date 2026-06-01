"""Repository for SourceProfile CRUD operations.

Enforces one active profile per source atomically in the activate method.
All enum-like fields are validated at the API layer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_uuid, to_uuid

_VALID_DOMAIN_TYPES = frozenset({"legal", "engineering", "logs", "email", "spreadsheet", "generic"})
_VALID_CHUNKING_STRATEGIES = frozenset(
    {"paragraph", "clause", "heading", "row", "thread", "page", "code_block", "default"}
)
_VALID_RETRIEVAL_STRATEGIES = frozenset(
    {"hybrid", "vector_only", "keyword_only", "metadata_first", "default"}
)
_VALID_EXTRACTION_STRATEGIES = frozenset(
    {"full_text", "ocr_required", "table_aware", "header_metadata", "default"}
)
_VALID_STATUSES = frozenset({"draft", "active", "needs_review", "deprecated"})

_ALLOWED_COLUMNS = frozenset(
    [
        "source_id",
        "name",
        "domain_type",
        "chunking_strategy",
        "retrieval_strategy",
        "extraction_strategy",
        "status",
        "model_policy_provider_id",
        "description",
        "config",
        "created_by",
        "approved_by",
        "version",
        "updated_at",
        "id",
    ]
)


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_enum(value: str, allowed: frozenset[str], field_name: str) -> None:
    if value not in allowed:
        allowed_str = ", ".join(sorted(allowed))
        raise ValueError(f"Invalid {field_name}: '{value}'. Allowed: {allowed_str}")


def _ensure_config(value: Any) -> str:
    """Return a JSON string for the config column."""
    if isinstance(value, str):
        return value
    return json.dumps(value or {})


def _resolve_config(value: Any) -> dict[str, Any]:
    """Deserialize config from the database."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value)) if value else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _row_to_dict(row: sa.RowMapping) -> dict[str, Any]:
    """Convert a source_profiles row to a dict with proper UUID/JSON handling."""
    return {
        "id": str(to_uuid(row["id"])),
        "source_id": str(to_uuid(row["source_id"])),
        "name": row["name"],
        "domain_type": row["domain_type"],
        "chunking_strategy": row["chunking_strategy"],
        "retrieval_strategy": row["retrieval_strategy"],
        "extraction_strategy": row["extraction_strategy"],
        "status": row["status"],
        "model_policy_provider_id": (
            str(to_uuid(row["model_policy_provider_id"]))
            if row.get("model_policy_provider_id")
            else None
        ),
        "description": row.get("description"),
        "config": _resolve_config(row.get("config")),
        "created_by": row.get("created_by"),
        "approved_by": row.get("approved_by"),
        "version": row["version"],
        "created_at": (
            row["created_at"].isoformat()
            if isinstance(row.get("created_at"), datetime)
            else str(row["created_at"])
            if row.get("created_at")
            else None
        ),
        "updated_at": (
            row["updated_at"].isoformat()
            if isinstance(row.get("updated_at"), datetime)
            else str(row["updated_at"])
            if row.get("updated_at")
            else None
        ),
    }


class ProfileRepository:
    """CRUD for source_profiles with one-active-per-source enforcement."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_profile(
        self,
        source_id: UUID,
        name: str,
        domain_type: str,
        chunking_strategy: str,
        retrieval_strategy: str,
        extraction_strategy: str,
        *,
        status: str = "draft",
        model_policy_provider_id: UUID | None = None,
        description: str | None = None,
        config: dict[str, Any] | None = None,
        created_by: str | None = None,
        approved_by: str | None = None,
        version: int = 1,
    ) -> UUID:
        """Create a new SourceProfile. Returns the new profile's UUID."""
        _validate_enum(domain_type, _VALID_DOMAIN_TYPES, "domain_type")
        _validate_enum(chunking_strategy, _VALID_CHUNKING_STRATEGIES, "chunking_strategy")
        _validate_enum(retrieval_strategy, _VALID_RETRIEVAL_STRATEGIES, "retrieval_strategy")
        _validate_enum(extraction_strategy, _VALID_EXTRACTION_STRATEGIES, "extraction_strategy")
        _validate_enum(status, _VALID_STATUSES, "status")

        profile_id = uuid4()
        now = _now()
        self._connection.execute(
            sa.text("""
                INSERT INTO source_profiles (
                    id, source_id, name, domain_type,
                    chunking_strategy, retrieval_strategy, extraction_strategy,
                    status, model_policy_provider_id, description, config,
                    created_by, approved_by, version, created_at, updated_at
                ) VALUES (
                    :id, :source_id, :name, :domain_type,
                    :chunking_strategy, :retrieval_strategy, :extraction_strategy,
                    :status, :model_policy_provider_id, :description, :config,
                    :created_by, :approved_by, :version, :created_at, :updated_at
                )
            """),
            {
                "id": db_uuid(profile_id),
                "source_id": db_uuid(source_id),
                "name": name,
                "domain_type": domain_type,
                "chunking_strategy": chunking_strategy,
                "retrieval_strategy": retrieval_strategy,
                "extraction_strategy": extraction_strategy,
                "status": status,
                "model_policy_provider_id": (
                    db_uuid(model_policy_provider_id) if model_policy_provider_id else None
                ),
                "description": description,
                "config": _ensure_config(config),
                "created_by": created_by,
                "approved_by": approved_by,
                "version": version,
                "created_at": now,
                "updated_at": now,
            },
        )
        return profile_id

    def get_profile(self, profile_id: UUID) -> dict[str, Any] | None:
        """Return a profile by id, or None."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM source_profiles WHERE id = :id"),
                {"id": db_uuid(profile_id)},
            )
            .mappings()
            .first()
        )
        return _row_to_dict(row) if row else None

    def get_active_profile(self, source_id: UUID) -> dict[str, Any] | None:
        """Return the active profile for a source, or None if none is active."""
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT * FROM source_profiles "
                    "WHERE source_id = :source_id AND status = 'active' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ),
                {"source_id": db_uuid(source_id)},
            )
            .mappings()
            .first()
        )
        return _row_to_dict(row) if row else None

    def list_profiles(
        self,
        source_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """List profiles, optionally filtered by source_id."""
        query = "SELECT * FROM source_profiles"
        params: dict[str, Any] = {}
        if source_id is not None:
            query += " WHERE source_id = :source_id"
            params["source_id"] = db_uuid(source_id)
        query += " ORDER BY created_at DESC"
        rows = self._connection.execute(sa.text(query), params).mappings().all()
        return [_row_to_dict(r) for r in rows]

    def update_profile(self, profile_id: UUID, **fields: Any) -> None:
        """Update a profile's fields.

        Raises ValueError if an enum field has an invalid value.
        Validates domain_type, chunking_strategy, retrieval_strategy,
        extraction_strategy, and status if present in fields.
        """
        # Validate enum fields
        if "domain_type" in fields:
            _validate_enum(fields["domain_type"], _VALID_DOMAIN_TYPES, "domain_type")
        if "chunking_strategy" in fields:
            _validate_enum(
                fields["chunking_strategy"], _VALID_CHUNKING_STRATEGIES, "chunking_strategy"
            )
        if "retrieval_strategy" in fields:
            _validate_enum(
                fields["retrieval_strategy"], _VALID_RETRIEVAL_STRATEGIES, "retrieval_strategy"
            )
        if "extraction_strategy" in fields:
            _validate_enum(
                fields["extraction_strategy"], _VALID_EXTRACTION_STRATEGIES, "extraction_strategy"
            )
        if "status" in fields:
            _validate_enum(fields["status"], _VALID_STATUSES, "status")

        # Handle UUID conversion
        if "model_policy_provider_id" in fields:
            v = fields["model_policy_provider_id"]
            fields["model_policy_provider_id"] = db_uuid(v) if v else None

        if "source_id" in fields:
            fields["source_id"] = db_uuid(fields["source_id"])

        if "config" in fields:
            fields["config"] = _ensure_config(fields["config"])

        fields["updated_at"] = _now()
        fields["id"] = db_uuid(profile_id)

        unknown = set(fields) - _ALLOWED_COLUMNS
        if unknown:
            raise ValueError(f"Unknown columns in update: {', '.join(sorted(unknown))}")

        sets = ", ".join(f"{k} = :{k}" for k in fields)
        self._connection.execute(
            sa.text(f"UPDATE source_profiles SET {sets} WHERE id = :id"),
            fields,
        )

    def activate_profile(self, profile_id: UUID) -> None:
        """Activate a profile, atomically ensuring one active profile per source.

        If another profile is already active for the same source, it is
        automatically deprecated within the same transaction.
        """
        profile = self.get_profile(profile_id)
        if profile is None:
            raise ValueError("Profile not found")

        source_id = to_uuid(profile["source_id"])

        # Deactivate/deprecate any currently active profile for this source
        current_active = self.get_active_profile(source_id)
        if current_active is not None and to_uuid(current_active["id"]) != profile_id:
            self._connection.execute(
                sa.text(
                    "UPDATE source_profiles SET status = 'deprecated', updated_at = :now "
                    "WHERE id = :id AND status = 'active'"
                ),
                {
                    "id": db_uuid(to_uuid(current_active["id"])),
                    "now": _now(),
                },
            )

        # Activate the requested profile
        self._connection.execute(
            sa.text(
                "UPDATE source_profiles SET status = 'active', updated_at = :now WHERE id = :id"
            ),
            {
                "id": db_uuid(profile_id),
                "now": _now(),
            },
        )

    def deprecate_profile(self, profile_id: UUID) -> None:
        """Mark a profile as deprecated. No-op if already deprecated."""
        self._connection.execute(
            sa.text(
                "UPDATE source_profiles SET status = 'deprecated', updated_at = :now "
                "WHERE id = :id AND status != 'deprecated'"
            ),
            {
                "id": db_uuid(profile_id),
                "now": _now(),
            },
        )

    def delete_profile(self, profile_id: UUID) -> None:
        """Delete a profile. Raises ValueError if the profile is active."""
        profile = self.get_profile(profile_id)
        if profile is None:
            raise ValueError("Profile not found")
        if profile["status"] == "active":
            raise ValueError("Cannot delete an active profile. Deprecate it first.")

        self._connection.execute(
            sa.text("DELETE FROM source_profiles WHERE id = :id"),
            {"id": db_uuid(profile_id)},
        )
