"""Tests for the context_packer module — hierarchy-aware chunk expansion."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from services.documents.models import LayoutBlockRow
from services.rag.context_packer import expand_chunks
from services.rag.trace_models import ContextPackingTrace

_DOC_UUID = UUID("00000000-0000-0000-0000-000000000001")
_DOC_UUID_STR = str(_DOC_UUID)
_NOW = datetime.now(UTC)


def _block(
    block_type: str,
    text: str,
    page_number: int = 1,
    reading_order: int = 0,
    document_id: UUID = _DOC_UUID,
) -> LayoutBlockRow:
    return LayoutBlockRow(
        id=uuid4(),
        document_id=document_id,
        page_number=page_number,
        block_type=block_type,  # type: ignore[arg-type]
        text=text,
        parser="test",
        reading_order=reading_order,
        created_at=_NOW,
    )


def _make_repo(blocks: list[LayoutBlockRow]) -> MagicMock:
    repo = MagicMock()
    repo.list_by_document.return_value = blocks
    return repo


def _chunk(
    chunk_id: str = "chunk-0",
    document_id: str = _DOC_UUID_STR,
    page_number: int | None = 1,
    section_heading: str | None = "Introduction",
    chunk_text: str = "Original chunk text.",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "page_number": page_number,
        "section_heading": section_heading,
        "chunk_text": chunk_text,
        "score": 0.9,
    }


# ---------------------------------------------------------------------------
# expand_chunks disabled
# ---------------------------------------------------------------------------


def test_expand_chunks_disabled_returns_chunks_unchanged() -> None:
    """When enabled=False, chunks pass through unchanged with a no-op trace."""
    chunks = [_chunk()]
    layout_repo = _make_repo([])
    result, trace = expand_chunks(chunks, layout_repo=layout_repo, enabled=False, budget_words=2000)
    assert result == chunks
    assert isinstance(trace, ContextPackingTrace)
    assert trace.expansion_applied is False
    assert trace.expanded_chunk_ids == []


def test_expand_chunks_no_chunks() -> None:
    """When chunks list is empty, returns empty with a no-op trace."""
    result, trace = expand_chunks([], layout_repo=MagicMock(), enabled=True, budget_words=2000)
    assert result == []
    assert trace.expansion_applied is False


# ---------------------------------------------------------------------------
# expand_chunks enabled, flat fallback
# ---------------------------------------------------------------------------


def test_expand_chunks_flat_fallback_no_blocks() -> None:
    """Chunks pass through unchanged when the document has no layout blocks."""
    chunks = [_chunk()]
    repo = _make_repo([])
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert result[0]["chunk_text"] == "Original chunk text."
    assert trace.sections_not_found == 1
    assert trace.expansion_applied is False


def test_expand_chunks_flat_fallback_no_section_match() -> None:
    """Chunks pass through unchanged when the section heading doesn't match."""
    blocks = [_block("heading", "Other Section")]
    chunks = [_chunk(section_heading="Introduction")]
    repo = _make_repo(blocks)
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert result[0]["chunk_text"] == "Original chunk text."
    assert trace.sections_not_found == 1
    assert trace.sections_matched == 0


def test_expand_chunks_flat_fallback_no_section_heading() -> None:
    """Chunks without section_heading pass through unchanged."""
    chunks = [_chunk(section_heading=None)]
    repo = _make_repo([_block("heading", "Intro")])
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert result[0]["chunk_text"] == "Original chunk text."
    assert trace.sections_not_found == 1


def test_expand_chunks_flat_fallback_no_document_id() -> None:
    """Chunks without document_id pass through unchanged."""
    chunks = [_chunk(document_id="")]
    repo = _make_repo([_block("heading", "Intro")])
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert result[0]["chunk_text"] == "Original chunk text."
    assert trace.sections_not_found == 1


# ---------------------------------------------------------------------------
# expand_chunks successful expansion
# ---------------------------------------------------------------------------


def test_expand_chunks_adds_parent_heading() -> None:
    """A chunk matching a section gets the parent heading prepended."""
    blocks = [
        _block("heading", "Introduction", reading_order=0),
        _block("paragraph", "Some introductory text.", reading_order=1),
    ]
    chunks = [_chunk(section_heading="Introduction", chunk_text="Deep dive content.")]
    repo = _make_repo(blocks)
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert trace.expansion_applied is True
    assert trace.parent_blocks_added == 1
    assert "Section: Introduction" in result[0]["chunk_text"]
    assert "Deep dive content." in result[0]["chunk_text"]


def test_expand_chunks_adds_sibling_text() -> None:
    """A chunk matching a section gets sibling paragraph text included.

    Note: without ``layout_block_id`` in the chunk payload (PR3 adds it),
    the anchor is the first non-heading block in the section.  Sibling
    blocks before the anchor are empty when the anchor is the first block.
    """
    blocks = [
        _block("heading", "Methods", reading_order=0),
        _block("paragraph", "Step A: preparation.", reading_order=1),
        _block("paragraph", "Step B: execution.", reading_order=2),
        _block("paragraph", "Step C: analysis.", reading_order=3),
    ]
    # The chunk matches the Methods section
    chunks = [_chunk(section_heading="Methods", chunk_text="Step B details.")]
    repo = _make_repo(blocks)
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert trace.expansion_applied is True
    assert trace.parent_blocks_added == 1
    assert trace.sibling_blocks_added == 2  # Step B and Step C (anchor is Step A)
    text = result[0]["chunk_text"]
    assert "Section: Methods" in text
    # Step A is the anchor (first non-heading block) — not in siblings
    assert "Step B: execution." in text
    assert "Step C: analysis." in text
    assert "Step B details." in text  # original chunk preserved


def test_expand_chunks_multiple_chunks() -> None:
    """Multiple chunks from the same document each get expanded."""
    blocks = [
        _block("heading", "Section 1", reading_order=0),
        _block("paragraph", "S1 content.", reading_order=1),
        _block("heading", "Section 2", reading_order=2),
        _block("paragraph", "S2 content.", reading_order=3),
    ]
    chunks = [
        _chunk(chunk_id="c1", section_heading="Section 1", chunk_text="C1 text."),
        _chunk(chunk_id="c2", section_heading="Section 2", chunk_text="C2 text."),
    ]
    repo = _make_repo(blocks)
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert trace.expansion_applied is True
    assert trace.sections_matched == 2
    assert len(trace.expanded_chunk_ids) == 2
    assert "Section: Section 1" in result[0]["chunk_text"]
    assert "Section: Section 2" in result[1]["chunk_text"]


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


def test_expand_chunks_budget_drops_expansion() -> None:
    """When expansion would exceed budget, it is dropped (original text preserved)."""
    blocks = [
        _block("heading", "Huge", reading_order=0),
        _block("paragraph", "word " * 500, reading_order=1),  # 500 space-separated tokens
    ]
    chunks = [_chunk(section_heading="Huge", chunk_text="Small original.")]
    repo = _make_repo(blocks)
    # Very tight budget — even the heading "Section: Huge" (2 words) exceeds this
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=1)
    assert trace.expansion_applied is False
    assert trace.dropped_for_budget >= 1
    # Original text must survive unchanged
    assert result[0]["chunk_text"] == "Small original."


# ---------------------------------------------------------------------------
# Same-document guarantee
# ---------------------------------------------------------------------------


def test_expand_chunks_same_document_only() -> None:
    """Expansion only reads blocks from the same document as the chunk."""
    other_doc = UUID("00000000-0000-0000-0000-000000000099")
    blocks = [
        _block("heading", "Other Section", document_id=_DOC_UUID, reading_order=0),
        _block("paragraph", "Content.", document_id=_DOC_UUID, reading_order=1),
    ]
    chunk_from_other = _chunk(
        chunk_id="other-chunk",
        document_id=str(other_doc),
        section_heading="Intro",  # This heading doesn't exist in the blocks
        chunk_text="From another doc.",
    )
    repo = _make_repo(blocks)
    result, trace = expand_chunks(
        [chunk_from_other], layout_repo=repo, enabled=True, budget_words=2000
    )
    # list_by_document returns blocks with "Other Section", but the chunk
    # specifies section_heading="Intro" — no match
    assert trace.sections_not_found == 1
    assert trace.expansion_applied is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_expand_chunks_repo_exception_falls_through() -> None:
    """When LayoutBlockRepository raises, the chunk passes through unchanged."""
    repo = MagicMock()
    repo.list_by_document.side_effect = Exception("DB error")
    chunks = [_chunk()]
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert result[0]["chunk_text"] == "Original chunk text."
    assert trace.sections_not_found == 1


def test_expand_chunks_invalid_uuid_passes_through() -> None:
    """When document_id is not a valid UUID, the chunk passes through."""
    chunks = [_chunk(document_id="not-a-uuid")]
    repo = _make_repo([])
    result, trace = expand_chunks(chunks, layout_repo=repo, enabled=True, budget_words=2000)
    assert result[0]["chunk_text"] == "Original chunk text."
    assert trace.sections_not_found == 1
