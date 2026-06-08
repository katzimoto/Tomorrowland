from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from shared.feature_flags import SYSTEM_CONFIG_DEFAULTS


def test_foundation_migration_creates_expected_tables(migrated_engine: Engine) -> None:
    inspector = sa.inspect(migrated_engine)

    assert {
        "users",
        "groups",
        "user_groups",
        "ingestion_sources",
        "source_permissions",
        "documents",
        "ingested_files",
        "system_config",
    } <= set(inspector.get_table_names())


def test_system_config_seed_values_are_inserted(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        rows = connection.execute(sa.text("SELECT key FROM system_config")).scalars().all()

    assert set(rows) == set(SYSTEM_CONFIG_DEFAULTS)


def test_document_source_external_sha_is_unique(migrated_engine: Engine) -> None:
    source_id = uuid4()

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, source_language)
                VALUES (:id, 'Folder', 'folder', 'en')
                """
            ),
            {"id": source_id.hex},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO documents (
                    id, source_id, external_id, source, mime_type, content_sha256
                )
                VALUES (
                    :id, :source_id, 'file:/data/a.txt', 'folder', 'text/plain', :sha
                )
                """
            ),
            {"id": uuid4().hex, "source_id": source_id.hex, "sha": "a" * 64},
        )

    with (
        pytest.raises(sa.exc.IntegrityError),
        migrated_engine.begin() as connection,
    ):
        connection.execute(
            sa.text(
                """
                INSERT INTO documents (
                    id, source_id, external_id, source, mime_type, content_sha256
                )
                VALUES (
                    :id, :source_id, 'file:/data/a.txt', 'folder', 'text/plain', :sha
                )
                """
            ),
            {"id": uuid4().hex, "source_id": source_id.hex, "sha": "a" * 64},
        )

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO documents (
                    id, source_id, external_id, source, mime_type, content_sha256
                )
                VALUES (
                    :id, :source_id, 'file:/data/a.txt', 'folder', 'text/plain', :sha
                )
                """
            ),
            {"id": uuid4().hex, "source_id": source_id.hex, "sha": "b" * 64},
        )

    with migrated_engine.connect() as connection:
        count = connection.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM documents
                WHERE source_id = :source_id AND external_id = 'file:/data/a.txt'
                """
            ),
            {"source_id": source_id.hex},
        ).scalar_one()

    assert count == 2


def test_source_permissions_support_source_level_grants(migrated_engine: Engine) -> None:
    source_id = uuid4()
    group_id = uuid4()

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO groups (id, name) VALUES (:id, 'Analysts')"),
            {"id": group_id.hex},
        )
        connection.execute(
            sa.text(
                "INSERT INTO ingestion_sources (id, name, type, source_language) "
                "VALUES (:id, 'Folder', 'folder', 'en')"
            ),
            {"id": source_id.hex},
        )
        connection.execute(
            sa.text(
                "INSERT INTO source_permissions (source_id, group_id) "
                "VALUES (:source_id, :group_id)"
            ),
            {"source_id": source_id.hex, "group_id": group_id.hex},
        )
        rows = (
            connection.execute(sa.text("SELECT group_id FROM source_permissions")).scalars().all()
        )

    assert [str(r).replace("-", "") for r in rows] == [group_id.hex]


def test_model_provider_registry_tables_created(migrated_engine: Engine) -> None:
    inspector = sa.inspect(migrated_engine)
    tables = set(inspector.get_table_names())
    assert "model_providers" in tables
    assert "model_descriptors" in tables
    assert "model_task_defaults" in tables


def test_model_provider_unique_name(migrated_engine: Engine) -> None:
    provider_id = uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO model_providers (id, name, provider_type) "
                "VALUES (:id, 'UniqueName', 'ollama')"
            ),
            {"id": provider_id.hex},
        )
    with (
        pytest.raises(sa.exc.IntegrityError),
        migrated_engine.begin() as connection,
    ):
        connection.execute(
            sa.text(
                "INSERT INTO model_providers (id, name, provider_type) "
                "VALUES (:id, 'UniqueName', 'openai-compatible')"
            ),
            {"id": uuid4().hex},
        )


def test_model_descriptor_unique_provider_model(migrated_engine: Engine) -> None:
    provider_id = uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO model_providers (id, name, provider_type) "
                "VALUES (:id, 'UniqPM', 'ollama')"
            ),
            {"id": provider_id.hex},
        )
        connection.execute(
            sa.text(
                "INSERT INTO model_descriptors (id, provider_id, model_name) "
                "VALUES (:id, :pid, 'mistral')"
            ),
            {"id": uuid4().hex, "pid": provider_id.hex},
        )
    with (
        pytest.raises(sa.exc.IntegrityError),
        migrated_engine.begin() as connection,
    ):
        connection.execute(
            sa.text(
                "INSERT INTO model_descriptors (id, provider_id, model_name) "
                "VALUES (:id, :pid, 'mistral')"
            ),
            {"id": uuid4().hex, "pid": provider_id.hex},
        )


def test_model_task_default_unique_task_type(migrated_engine: Engine) -> None:
    provider_id = uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO model_providers (id, name, provider_type) "
                "VALUES (:id, 'UniqTT', 'ollama')"
            ),
            {"id": provider_id.hex},
        )
        connection.execute(
            sa.text(
                "INSERT INTO model_task_defaults (id, task_type, provider_id) "
                "VALUES (:id, 'chat', :pid)"
            ),
            {"id": uuid4().hex, "pid": provider_id.hex},
        )
    with (
        pytest.raises(sa.exc.IntegrityError),
        migrated_engine.begin() as connection,
    ):
        connection.execute(
            sa.text(
                "INSERT INTO model_task_defaults (id, task_type, provider_id) "
                "VALUES (:id, 'chat', :pid)"
            ),
            {"id": uuid4().hex, "pid": provider_id.hex},
        )


# ---------------------------------------------------------------------------
# Performance indexes (m3n4o5p6q7r8)
# ---------------------------------------------------------------------------


def test_performance_indexes_exist(migrated_engine: Engine) -> None:
    """The performance-optimisation migration must create indexes on
    documents.version_family_id, documents.external_id, and
    source_permissions.group_id.
    """
    inspector = sa.inspect(migrated_engine)

    # Collect all index names from the relevant tables
    doc_indexes = {idx["name"] for idx in inspector.get_indexes("documents")}
    src_perm_indexes = {idx["name"] for idx in inspector.get_indexes("source_permissions")}

    # Verify the new performance indexes exist
    assert "ix_documents_version_family_id" in doc_indexes, (
        f"Expected ix_documents_version_family_id in {doc_indexes}"
    )
    # Composite index on (source_id, external_id) for dedup lookups
    assert "ix_documents_external_id_source" in doc_indexes, (
        f"Expected ix_documents_external_id_source in {doc_indexes}"
    )
    assert "ix_source_permissions_group_id" in src_perm_indexes, (
        f"Expected ix_source_permissions_group_id in {src_perm_indexes}"
    )
