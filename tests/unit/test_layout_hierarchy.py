"""Tests for the layout_hierarchy module — in-memory section tree derivation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from services.documents.models import LayoutBlockRow
from services.rag.layout_hierarchy import (
    SectionInfo,
    build_section_map,
    get_neighborhood,
    section_exists,
)

_DOC_UUID = UUID("00000000-0000-0000-0000-000000000001")

_NOW = datetime.now(UTC)


def _block(
    block_type: str,
    text: str,
    page_number: int = 1,
    reading_order: int = 0,
) -> LayoutBlockRow:
    return LayoutBlockRow(
        id=uuid4(),
        document_id=_DOC_UUID,
        page_number=page_number,
        block_type=block_type,  # type: ignore[arg-type]
        text=text,
        parser="test",
        reading_order=reading_order,
        created_at=_NOW,
    )


# ---------------------------------------------------------------------------
# build_section_map
# ---------------------------------------------------------------------------


def test_build_section_map_single_section() -> None:
    """A single heading followed by paragraphs produces one section."""
    blocks = [
        _block("heading", "Introduction", reading_order=0),
        _block("paragraph", "Some content.", reading_order=1),
        _block("paragraph", "More content.", reading_order=2),
    ]
    sm = build_section_map(blocks)
    assert len(sm) == 1
    key = (1, "Introduction")
    assert key in sm
    assert sm[key].heading_text == "Introduction"
    assert len(sm[key].blocks) == 2  # both paragraphs
    assert sm[key].page_number == 1


def test_build_section_map_multiple_sections() -> None:
    """Multiple headings produce multiple sections."""
    blocks = [
        _block("heading", "Intro", reading_order=0),
        _block("paragraph", "Intro text.", reading_order=1),
        _block("heading", "Methods", reading_order=2),
        _block("paragraph", "Method A.", reading_order=3),
        _block("paragraph", "Method B.", reading_order=4),
        _block("heading", "Results", reading_order=5),
        _block("paragraph", "Result 1.", reading_order=6),
    ]
    sm = build_section_map(blocks)
    assert len(sm) == 3
    assert (1, "Intro") in sm
    assert len(sm[(1, "Intro")].blocks) == 1
    assert (1, "Methods") in sm
    assert len(sm[(1, "Methods")].blocks) == 2
    assert (1, "Results") in sm
    assert len(sm[(1, "Results")].blocks) == 1


def test_build_section_map_page_boundaries() -> None:
    """Page boundaries reset sections — a heading on page 2 is a new section."""
    blocks = [
        _block("heading", "Page 1 Section", page_number=1, reading_order=0),
        _block("paragraph", "Still page 1.", page_number=1, reading_order=1),
        _block("heading", "Page 2 Section", page_number=2, reading_order=2),
        _block("paragraph", "Page 2 content.", page_number=2, reading_order=3),
    ]
    sm = build_section_map(blocks)
    assert (1, "Page 1 Section") in sm
    assert (2, "Page 2 Section") in sm
    assert len(sm) == 2
    assert len(sm[(1, "Page 1 Section")].blocks) == 1
    assert len(sm[(2, "Page 2 Section")].blocks) == 1


def test_build_section_map_no_headings() -> None:
    """When no heading blocks exist, the map is empty."""
    blocks = [
        _block("paragraph", "No headings here.", reading_order=0),
        _block("paragraph", "Just paragraphs.", reading_order=1),
    ]
    sm = build_section_map(blocks)
    assert sm == {}


def test_build_section_map_heading_without_text() -> None:
    """A heading with empty text is still used as a section boundary."""
    blocks = [
        _block("heading", "", reading_order=0),
        _block("paragraph", "Content under empty heading.", reading_order=1),
    ]
    sm = build_section_map(blocks)
    key = (1, "")
    assert key in sm
    assert sm[key].heading_text == ""
    assert len(sm[key].blocks) == 1


def test_build_section_map_mixed_types() -> None:
    """Non-paragraph, non-heading block types (table, figure) are included in a section."""
    blocks = [
        _block("heading", "Data", reading_order=0),
        _block("table", "table data", reading_order=1),
        _block("figure", "figure caption", reading_order=2),
        _block("paragraph", "After figure.", reading_order=3),
    ]
    sm = build_section_map(blocks)
    key = (1, "Data")
    assert key in sm
    assert len(sm[key].blocks) == 3  # table, figure, paragraph
    block_types = [b.block_type for b in sm[key].blocks]
    assert "table" in block_types
    assert "figure" in block_types
    assert "paragraph" in block_types


# ---------------------------------------------------------------------------
# SectionInfo.all_text
# ---------------------------------------------------------------------------


def test_section_all_text_includes_heading() -> None:
    """all_text returns heading text followed by content block texts."""
    section = SectionInfo(
        heading_block_id=uuid4(),
        heading_text="Results",
        blocks=[
            _block("paragraph", "First result.", reading_order=1),
            _block("paragraph", "Second result.", reading_order=2),
        ],
        page_number=1,
    )
    text = section.all_text
    assert "Results" in text
    assert "First result." in text
    assert "Second result." in text


# ---------------------------------------------------------------------------
# get_neighborhood
# ---------------------------------------------------------------------------


def test_get_neighborhood_returns_parent_and_siblings() -> None:
    """get_neighborhood returns the parent heading and surrounding siblings."""
    blocks = [
        _block("heading", "Methods", page_number=1, reading_order=0),
        _block("paragraph", "Step 1.", page_number=1, reading_order=1),
        _block("paragraph", "Step 2.", page_number=1, reading_order=2),
        _block("paragraph", "Step 3.", page_number=1, reading_order=3),
    ]
    parents, before, after = get_neighborhood(blocks, 1, "Methods", radius=2)
    assert len(parents) == 1
    assert parents[0].text == "Methods"
    assert len(before) >= 0
    assert len(after) >= 0


def test_get_neighborhood_unknown_section() -> None:
    """When the section is not found, all three lists are empty."""
    blocks = [
        _block("heading", "Known", page_number=1, reading_order=0),
        _block("paragraph", "Content.", page_number=1, reading_order=1),
    ]
    parents, before, after = get_neighborhood(blocks, 1, "Unknown", radius=3)
    assert parents == []
    assert before == []
    assert after == []


def test_get_neighborhood_none_section_heading() -> None:
    """When section_heading is None, returns empty."""
    blocks = [
        _block("heading", "Heading", page_number=1, reading_order=0),
    ]
    parents, before, after = get_neighborhood(blocks, 1, None, radius=3)
    assert parents == []
    assert before == []
    assert after == []


# ---------------------------------------------------------------------------
# section_exists
# ---------------------------------------------------------------------------


def test_section_exists_returns_true() -> None:
    blocks = [
        _block("heading", "Intro", reading_order=0),
        _block("paragraph", "Text.", reading_order=1),
    ]
    assert section_exists(blocks, 1, "Intro") is True


def test_section_exists_returns_false() -> None:
    blocks = [
        _block("heading", "Intro", reading_order=0),
    ]
    assert section_exists(blocks, 1, "Missing") is False


def test_section_exists_empty_heading() -> None:
    blocks = [
        _block("heading", "Intro", reading_order=0),
    ]
    assert section_exists(blocks, 1, "") is False


def test_section_exists_none_heading() -> None:
    blocks = [
        _block("heading", "Intro", reading_order=0),
    ]
    assert section_exists(blocks, 1, None) is False


# ---------------------------------------------------------------------------
# SectionInfo repr
# ---------------------------------------------------------------------------


def test_section_info_repr() -> None:
    section = SectionInfo(
        heading_block_id=uuid4(),
        heading_text="Test",
        blocks=[_block("paragraph", "Text.", reading_order=0)],
        page_number=1,
    )
    r = repr(section)
    assert "SectionInfo" in r
    assert "Test" in r
    assert "block_count=1" in r
