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


def test_document_source_external_id_is_unique(migrated_engine: Engine) -> None:
    source_id = uuid4()
    doc_id = uuid4()

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
                INSERT INTO documents (id, source_id, external_id, source, mime_type)
                VALUES (:id, :source_id, 'file:/data/a.txt', 'folder', 'text/plain')
                """
            ),
            {"id": doc_id.hex, "source_id": source_id.hex},
        )
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO documents (id, source_id, external_id, source, mime_type)
                    VALUES (:id, :source_id, 'file:/data/a.txt', 'folder', 'text/plain')
                    """
                ),
                {"id": uuid4().hex, "source_id": source_id.hex},
            )


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

    assert rows == [group_id.hex]
