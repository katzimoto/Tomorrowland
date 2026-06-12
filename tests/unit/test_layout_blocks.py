"""Unit tests for layout block repository and model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from services.documents.layout_block_repository import LayoutBlockRepository
from services.documents.models import LayoutBlockRow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_source(connection: sa.Connection) -> UUID:
    source_id = uuid4()
    connection.execute(
        sa.text("""
            INSERT INTO ingestion_sources (id, name, type, source_language)
            VALUES (:id, :name, 'folder', 'en')
            """),
        {"id": source_id.hex, "name": "test-source"},
    )
    return source_id


def _create_document(connection: sa.Connection) -> UUID:
    source_id = _create_source(connection)
    doc_id = uuid4()
    connection.execute(
        sa.text("""
            INSERT INTO documents (id, source_id, external_id, source, mime_type, status)
            VALUES (:id, :source_id, 'test-doc-1', 'folder', 'text/plain', 'pending')
            """),
        {"id": doc_id.hex, "source_id": source_id.hex},
    )
    return doc_id


def _sample_blocks(parser: str = "pypdf") -> list[dict[str, object]]:
    """Return three layout blocks spanning two pages."""
    return [
        {
            "page_number": 1,
            "block_type": "heading",
            "text": "Introduction",
            "parser": parser,
            "confidence": 0.95,
            "reading_order": 0,
        },
        {
            "page_number": 1,
            "block_type": "paragraph",
            "text": "This is the first paragraph of the document.",
            "parser": parser,
            "confidence": 0.90,
            "reading_order": 1,
        },
        {
            "page_number": 1,
            "block_type": "table",
            "text": None,
            "bbox": [10.0, 20.0, 200.0, 100.0],
            "parser": parser,
            "confidence": 0.85,
            "reading_order": 2,
        },
        {
            "page_number": 2,
            "block_type": "paragraph",
            "text": "Second page paragraph.",
            "parser": parser,
            "confidence": None,
            "reading_order": 3,
        },
    ]


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestLayoutBlockRepository:
    def test_bulk_upsert_inserts_blocks(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)

            count = repo.bulk_upsert(doc_id, _sample_blocks())

        assert count == 4

    def test_list_by_document_returns_all_blocks(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())

            blocks = repo.list_by_document(doc_id)

        assert len(blocks) == 4
        assert blocks[0].block_type == "heading"
        assert blocks[1].block_type == "paragraph"
        assert blocks[2].block_type == "table"
        assert blocks[3].block_type == "paragraph"
        # reading_order is honoured
        assert blocks[0].reading_order == 0
        assert blocks[3].reading_order == 3

    def test_list_by_document_filters_by_block_type(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())

            headings = repo.list_by_document(doc_id, block_type="heading")
            tables = repo.list_by_document(doc_id, block_type="table")

        assert len(headings) == 1
        assert headings[0].block_type == "heading"
        assert len(tables) == 1
        assert tables[0].block_type == "table"

    def test_bulk_upsert_replaces_existing_blocks(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)

            # First insert
            repo.bulk_upsert(doc_id, _sample_blocks())
            assert repo.count_by_document(doc_id) == 4

            # Replace with fewer blocks
            new_blocks = [
                {
                    "page_number": 1,
                    "block_type": "paragraph",
                    "text": "Replacement text.",
                    "parser": "docling",
                    "reading_order": 0,
                }
            ]
            count = repo.bulk_upsert(doc_id, new_blocks)

            blocks = repo.list_by_document(doc_id)

        assert count == 1
        assert len(blocks) == 1
        assert blocks[0].parser == "docling"
        assert blocks[0].text == "Replacement text."

    def test_bulk_upsert_empty_blocks_deletes_all(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())
            assert repo.count_by_document(doc_id) == 4

            count = repo.bulk_upsert(doc_id, [])

            blocks = repo.list_by_document(doc_id)

        assert count == 0
        assert blocks == []

    def test_has_blocks_returns_true_when_blocks_exist(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())

            result = repo.has_blocks(doc_id)

        assert result is True

    def test_has_blocks_returns_false_when_no_blocks(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)

            result = repo.has_blocks(doc_id)

        assert result is False

    def test_page_summary_counts_by_page_and_type(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())

            summary = repo.page_summary(doc_id)

        # Two pages: page 1 has heading (1), paragraph (1), table (1);
        # page 2 has paragraph (1)
        page_1_items = [s for s in summary if s["page_number"] == 1]
        page_2_items = [s for s in summary if s["page_number"] == 2]

        assert len(page_1_items) == 3
        assert len(page_2_items) == 1

    def test_delete_by_document_removes_all_blocks(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())
            assert repo.count_by_document(doc_id) == 4

            deleted = repo.delete_by_document(doc_id)

            assert deleted == 4
            assert repo.count_by_document(doc_id) == 0

    def test_bulk_upsert_invalid_block_type_raises(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)

            with pytest.raises(ValueError, match="Invalid block_type"):
                repo.bulk_upsert(
                    doc_id,
                    [{"block_type": "not_a_real_type", "parser": "pypdf"}],
                )

    def test_bbox_deserialized_to_tuple(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())

            blocks = repo.list_by_document(doc_id)
            table_block = [b for b in blocks if b.block_type == "table"][0]

        assert table_block.bbox == (10.0, 20.0, 200.0, 100.0)

    def test_no_bbox_yields_none(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())

            blocks = repo.list_by_document(doc_id)
            heading_block = [b for b in blocks if b.block_type == "heading"][0]

        assert heading_block.bbox is None

    def test_confidence_is_float_or_none(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            doc_id = _create_document(connection)
            repo = LayoutBlockRepository(connection)
            repo.bulk_upsert(doc_id, _sample_blocks())

            blocks = repo.list_by_document(doc_id)
            heading = [b for b in blocks if b.block_type == "heading"][0]
            last_para = blocks[-1]

        assert isinstance(heading.confidence, float)
        assert heading.confidence == 0.95
        assert last_para.confidence is None


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

_NOW = datetime.now(UTC)


class TestLayoutBlockRow:
    def test_model_accepts_valid_block_type(self) -> None:
        row = LayoutBlockRow(
            id=uuid4(),
            document_id=uuid4(),
            page_number=1,
            block_type="paragraph",
            text="Hello",
            parser="pypdf",
            reading_order=0,
            created_at=_NOW,
        )
        assert row.block_type == "paragraph"

    def test_model_with_bbox(self) -> None:
        row = LayoutBlockRow(
            id=uuid4(),
            document_id=uuid4(),
            block_type="figure",
            bbox=(0.0, 0.0, 100.0, 50.0),
            parser="docling",
            created_at=_NOW,
        )
        assert row.bbox == (0.0, 0.0, 100.0, 50.0)

    def test_model_all_block_types_accepted(self) -> None:
        valid_types = [
            "paragraph",
            "heading",
            "table",
            "figure",
            "caption",
            "footer",
            "header",
        ]
        for bt in valid_types:
            row = LayoutBlockRow(
                id=uuid4(),
                document_id=uuid4(),
                block_type=bt,  # type: ignore[arg-type]
                parser="pypdf",
                created_at=_NOW,
            )
            assert row.block_type == bt
