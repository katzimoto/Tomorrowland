from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from services.intelligence.repository import IntelligenceRepository


@pytest.fixture
def engine(tmp_path) -> Engine:
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.begin() as conn:
        conn.execute(
            sa.text("""
            CREATE TABLE document_summaries (
                document_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT DEFAULT 'available',
                summary_bullets TEXT,
                language TEXT,
                document_type TEXT,
                source_text TEXT,
                input_chars INTEGER,
                content_hash TEXT,
                error_type TEXT,
                error_summary TEXT,
                last_attempted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        conn.execute(
            sa.text("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                UNIQUE (name, type)
            )
        """)
        )
        conn.execute(
            sa.text("""
            CREATE TABLE document_entities (
                document_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                frequency INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (document_id, entity_id)
            )
        """)
        )
        conn.execute(
            sa.text("""
            CREATE TABLE document_tags (
                document_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (document_id, tag)
            )
        """)
        )
    return eng


def test_upsert_summary_creates_and_updates(engine: Engine) -> None:
    with engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        document_id = uuid4()
        repo.upsert_summary(document_id, "First summary", "mistral")

        row = repo.get_summary(document_id)
        assert row is not None
        assert row["summary"] == "First summary"
        assert row["model"] == "mistral"

        repo.upsert_summary(document_id, "Updated summary", "llama3")
        row = repo.get_summary(document_id)
        assert row["summary"] == "Updated summary"
        assert row["model"] == "llama3"


def test_get_summary_returns_none_when_missing(engine: Engine) -> None:
    with engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        result = repo.get_summary(uuid4())
        assert result is None


def test_upsert_entity_deduplicates_by_name_type(engine: Engine) -> None:
    with engine.begin() as connection:
        repo = IntelligenceRepository(connection)

        e1 = repo.upsert_entity("Alice", "person")
        e2 = repo.upsert_entity("Alice", "person")
        e3 = repo.upsert_entity("Alice", "organization")

        assert e1 == e2
        assert e1 != e3


def test_link_document_entity_increments_frequency(engine: Engine) -> None:
    with engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        document_id = uuid4()
        entity_id = repo.upsert_entity("Bob", "person")

        repo.link_document_entity(document_id, entity_id, frequency=2)
        repo.link_document_entity(document_id, entity_id, frequency=3)

        entities = repo.get_entities(document_id)
        assert len(entities) == 1
        assert entities[0]["frequency"] == 5


def test_get_entities_returns_sorted(engine: Engine) -> None:
    with engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        document_id = uuid4()

        e1 = repo.upsert_entity("Charlie", "person")
        e2 = repo.upsert_entity("Acme", "organization")

        repo.link_document_entity(document_id, e1, frequency=1)
        repo.link_document_entity(document_id, e2, frequency=5)

        entities = repo.get_entities(document_id)
        assert len(entities) == 2
        # Higher frequency first
        assert entities[0]["name"] == "Acme"
        assert entities[1]["name"] == "Charlie"


def test_replace_tags(engine: Engine) -> None:
    with engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        document_id = uuid4()

        repo.replace_tags(document_id, ["finance", "Q3"])
        assert set(repo.get_tags(document_id)) == {"finance", "Q3"}

        repo.replace_tags(document_id, ["tech", "AI"])
        assert set(repo.get_tags(document_id)) == {"AI", "tech"}

        repo.replace_tags(document_id, [])
        assert repo.get_tags(document_id) == []


def test_get_tags_returns_empty_when_missing(engine: Engine) -> None:
    with engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        result = repo.get_tags(uuid4())
        assert result == []
