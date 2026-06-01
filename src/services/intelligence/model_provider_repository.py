"""Repository for model provider registry CRUD operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.engine import Connection

from shared.db import db_uuid, to_uuid

from .model_provider_models import (
    ModelDescriptor,
    ModelDescriptorCreate,
    ModelDescriptorUpdate,
    ModelProvider,
    ModelProviderCreate,
    ModelProviderUpdate,
    ModelTaskDefault,
    ModelTaskDefaultCreate,
    ModelTaskDefaultUpdate,
)


def _maybe_json(value: object) -> object:
    """Deserialize a JSON string if needed; return dict/list as-is."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


_TABLES = frozenset(
    {
        "model_providers",
        "model_descriptors",
        "model_task_defaults",
    }
)


def _now() -> datetime:
    return datetime.now(UTC)


class ModelProviderRepository:
    """CRUD for the model provider registry.

    All methods accept and return Pydantic models.  No raw credential values
    are stored — only *api_key_ref* references.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    # ------------------------------------------------------------------
    # Model Providers
    # ------------------------------------------------------------------

    def create_provider(self, data: ModelProviderCreate) -> ModelProvider:
        """Insert a new model provider and return it."""
        row_id = uuid4()
        now = _now()
        self._connection.execute(
            sa.text("""
                INSERT INTO model_providers (
                    id, name, provider_type, description, base_url,
                    api_key_ref, locality, enabled, created_at, updated_at
                ) VALUES (
                    :id, :name, :provider_type, :description, :base_url,
                    :api_key_ref, :locality, :enabled, :created_at, :updated_at
                )
            """),
            {
                "id": db_uuid(row_id),
                "name": data.name,
                "provider_type": data.provider_type,
                "description": data.description,
                "base_url": data.base_url,
                "api_key_ref": data.api_key_ref,
                "locality": data.locality,
                "enabled": data.enabled,
                "created_at": now,
                "updated_at": now,
            },
        )
        return _map_provider(
            {
                "id": db_uuid(row_id),
                "name": data.name,
                "provider_type": data.provider_type,
                "description": data.description,
                "base_url": data.base_url,
                "api_key_ref": data.api_key_ref,
                "locality": data.locality,
                "enabled": data.enabled,
                "created_at": now,
                "updated_at": now,
            }
        )

    def get_provider(self, provider_id: UUID) -> ModelProvider | None:
        """Return a provider by id, or None."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM model_providers WHERE id = :id"),
                {"id": db_uuid(provider_id)},
            )
            .mappings()
            .first()
        )
        return _map_provider(row) if row else None

    def get_provider_by_name(self, name: str) -> ModelProvider | None:
        """Return a provider by name, or None."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM model_providers WHERE name = :name"),
                {"name": name},
            )
            .mappings()
            .first()
        )
        return _map_provider(row) if row else None

    def list_providers(
        self,
        *,
        enabled_only: bool = False,
    ) -> list[ModelProvider]:
        """List all providers, optionally filtered to enabled ones."""
        query = "SELECT * FROM model_providers"
        params: dict[str, Any] = {}
        if enabled_only:
            query += " WHERE enabled = :enabled"
            params["enabled"] = True
        query += " ORDER BY name"
        rows = self._connection.execute(sa.text(query), params).mappings().all()
        return [_map_provider(r) for r in rows if r is not None]

    def update_provider(self, provider_id: UUID, data: ModelProviderUpdate) -> ModelProvider | None:
        """Update a provider's fields.  Returns None if not found."""
        existing = self.get_provider(provider_id)
        if existing is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return existing
        update_data["updated_at"] = _now()
        update_data["id"] = db_uuid(provider_id)
        # Safe: `sets` keys come from a Pydantic model's field names
        # (not user input).  Values go through bound parameters.
        sets = ", ".join(f"{k} = :{k}" for k in update_data)
        self._connection.execute(
            sa.text(f"UPDATE model_providers SET {sets} WHERE id = :id"),
            update_data,
        )
        return self.get_provider(provider_id)

    def delete_provider(self, provider_id: UUID) -> bool:
        """Delete a provider.  Cascades to descriptors.  Returns True if deleted."""
        result = self._connection.execute(
            sa.text("DELETE FROM model_providers WHERE id = :id"),
            {"id": db_uuid(provider_id)},
        )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Model Descriptors
    # ------------------------------------------------------------------

    def create_descriptor(self, data: ModelDescriptorCreate) -> ModelDescriptor:
        """Register a model descriptor under a provider."""
        row_id = uuid4()
        now = _now()
        self._connection.execute(
            sa.text("""
                INSERT INTO model_descriptors (
                    id, provider_id, model_name, display_name, description,
                    capabilities, context_window, max_output_tokens,
                    enabled, created_at, updated_at
                ) VALUES (
                    :id, :provider_id, :model_name, :display_name, :description,
                    :capabilities, :context_window, :max_output_tokens,
                    :enabled, :created_at, :updated_at
                )
            """),
            {
                "id": db_uuid(row_id),
                "provider_id": db_uuid(data.provider_id),
                "model_name": data.model_name,
                "display_name": data.display_name,
                "description": data.description,
                "capabilities": json.dumps(data.capabilities) if data.capabilities else None,
                "context_window": data.context_window,
                "max_output_tokens": data.max_output_tokens,
                "enabled": data.enabled,
                "created_at": now,
                "updated_at": now,
            },
        )
        return _map_descriptor(
            {
                "id": db_uuid(row_id),
                "provider_id": db_uuid(data.provider_id),
                "model_name": data.model_name,
                "display_name": data.display_name,
                "description": data.description,
                "capabilities": data.capabilities,
                "context_window": data.context_window,
                "max_output_tokens": data.max_output_tokens,
                "enabled": data.enabled,
                "created_at": now,
                "updated_at": now,
            }
        )

    def get_descriptor(self, descriptor_id: UUID) -> ModelDescriptor | None:
        """Return a descriptor by id, or None."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM model_descriptors WHERE id = :id"),
                {"id": db_uuid(descriptor_id)},
            )
            .mappings()
            .first()
        )
        return _map_descriptor(row) if row else None

    def list_descriptors(
        self,
        *,
        provider_id: UUID | None = None,
        enabled_only: bool = False,
    ) -> list[ModelDescriptor]:
        """List descriptors, optionally filtered by provider or enabled flag."""
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if provider_id is not None:
            clauses.append("provider_id = :provider_id")
            params["provider_id"] = db_uuid(provider_id)
        if enabled_only:
            clauses.append("enabled = :enabled")
            params["enabled"] = True
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = (
            self._connection.execute(
                sa.text(f"SELECT * FROM model_descriptors {where} ORDER BY model_name"),
                params,
            )
            .mappings()
            .all()
        )
        return [_map_descriptor(r) for r in rows if r is not None]

    def update_descriptor(
        self, descriptor_id: UUID, data: ModelDescriptorUpdate
    ) -> ModelDescriptor | None:
        """Update a descriptor's fields.  Returns None if not found."""
        existing = self.get_descriptor(descriptor_id)
        if existing is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return existing
        update_data["updated_at"] = _now()
        update_data["id"] = db_uuid(descriptor_id)
        if "capabilities" in update_data:
            cap = update_data["capabilities"]
            update_data["capabilities"] = json.dumps(cap) if cap else None
        # Safe: `sets` keys come from a Pydantic model's field names.
        sets = ", ".join(f"{k} = :{k}" for k in update_data)
        self._connection.execute(
            sa.text(f"UPDATE model_descriptors SET {sets} WHERE id = :id"),
            update_data,
        )
        return self.get_descriptor(descriptor_id)

    def delete_descriptor(self, descriptor_id: UUID) -> bool:
        """Delete a descriptor.  Returns True if deleted."""
        result = self._connection.execute(
            sa.text("DELETE FROM model_descriptors WHERE id = :id"),
            {"id": db_uuid(descriptor_id)},
        )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Model Task Defaults
    # ------------------------------------------------------------------

    def set_task_default(self, data: ModelTaskDefaultCreate) -> ModelTaskDefault:
        """Set or replace the default for a task type.

        Uses INSERT … ON CONFLICT to upsert by *task_type*.
        """
        row_id = uuid4()
        now = _now()
        self._connection.execute(
            sa.text("""
                INSERT INTO model_task_defaults (
                    id, task_type, provider_id, model_descriptor_id,
                    parameters, created_at, updated_at
                ) VALUES (
                    :id, :task_type, :provider_id, :model_descriptor_id,
                    :parameters, :created_at, :updated_at
                )
                ON CONFLICT (task_type) DO UPDATE SET
                    provider_id = EXCLUDED.provider_id,
                    model_descriptor_id = EXCLUDED.model_descriptor_id,
                    parameters = EXCLUDED.parameters,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "id": db_uuid(row_id),
                "task_type": data.task_type,
                "provider_id": db_uuid(data.provider_id),
                "model_descriptor_id": (
                    db_uuid(data.model_descriptor_id) if data.model_descriptor_id else None
                ),
                "parameters": json.dumps(data.parameters) if data.parameters else None,
                "created_at": now,
                "updated_at": now,
            },
        )
        result = self.get_task_default(data.task_type)
        if result is None:
            raise RuntimeError(
                f"Task default not found after upsert: task_type={data.task_type}"
            )
        return result

    def get_task_default(self, task_type: str) -> ModelTaskDefault | None:
        """Return the default for a task type, or None."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM model_task_defaults WHERE task_type = :task_type"),
                {"task_type": task_type},
            )
            .mappings()
            .first()
        )
        return _map_task_default(row) if row else None

    def list_task_defaults(self) -> list[ModelTaskDefault]:
        """Return all task defaults."""
        rows = (
            self._connection.execute(
                sa.text("SELECT * FROM model_task_defaults ORDER BY task_type")
            )
            .mappings()
            .all()
        )
        return [_map_task_default(r) for r in rows if r is not None]

    def update_task_default(
        self, task_type: str, data: ModelTaskDefaultUpdate
    ) -> ModelTaskDefault | None:
        """Update a task default by task_type.  Returns None if not found."""
        existing = self.get_task_default(task_type)
        if existing is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return existing
        update_data["updated_at"] = _now()
        if "parameters" in update_data:
            params_val = update_data["parameters"]
            update_data["parameters"] = json.dumps(params_val) if params_val else None
        for key in ("provider_id", "model_descriptor_id"):
            if key in update_data and update_data[key] is not None:
                update_data[key] = db_uuid(update_data[key])
        # Safe: `sets` keys come from a Pydantic model's field names.
        sets = ", ".join(f"{k} = :{k}" for k in update_data)
        self._connection.execute(
            sa.text(f"UPDATE model_task_defaults SET {sets} WHERE task_type = :task_type"),
            {"task_type": task_type, **update_data},
        )
        return self.get_task_default(task_type)

    def delete_task_default(self, task_type: str) -> bool:
        """Delete a task default.  Returns True if deleted."""
        result = self._connection.execute(
            sa.text("DELETE FROM model_task_defaults WHERE task_type = :task_type"),
            {"task_type": task_type},
        )
        return result.rowcount > 0


# ------------------------------------------------------------------
# Module-level mapping helpers
# ------------------------------------------------------------------


def _map_provider(
    row: RowMapping | dict[str, Any],
) -> ModelProvider:
    return ModelProvider(
        id=to_uuid(row["id"]),
        name=row["name"],
        provider_type=row["provider_type"],
        description=row.get("description"),
        base_url=row.get("base_url"),
        api_key_ref=row.get("api_key_ref"),
        locality=row["locality"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _map_descriptor(
    row: RowMapping | dict[str, Any],
) -> ModelDescriptor:
    return ModelDescriptor(
        id=to_uuid(row["id"]),
        provider_id=to_uuid(row["provider_id"]),
        model_name=row["model_name"],
        display_name=row.get("display_name"),
        description=row.get("description"),
        capabilities=cast("dict[str, Any] | None", _maybe_json(row.get("capabilities"))),
        context_window=row.get("context_window"),
        max_output_tokens=row.get("max_output_tokens"),
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _map_task_default(
    row: RowMapping | dict[str, Any],
) -> ModelTaskDefault:
    return ModelTaskDefault(
        id=to_uuid(row["id"]),
        task_type=row["task_type"],
        provider_id=to_uuid(row["provider_id"]),
        model_descriptor_id=(
            to_uuid(row["model_descriptor_id"]) if row.get("model_descriptor_id") else None
        ),
        parameters=cast("dict[str, Any] | None", _maybe_json(row.get("parameters"))),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
