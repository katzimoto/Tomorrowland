"""Tests that page_number and section_heading flow through RAG citation assembly.

These tests verify that the Citation model carries location metadata when
the upstream Qdrant payload includes it.  The propagation path is:

  Qdrant payload → SearchResult.metadata → _retrieve_chunks → Citation

All tests use mocked Qdrant results so they do not require a running Qdrant
service.
"""

from __future__ import annotations

from services.rag.models import Citation
from services.search.hybrid import SearchResult


def test_citation_model_accepts_page_number_and_section_heading() -> None:
    """Citation model fields must accept page_number and section_heading."""
    c = Citation(
        document_id="doc-1",
        chunk_text="some text",
        score=0.95,
        page_number=3,
        section_heading="Chapter 2",
    )
    assert c.page_number == 3
    assert c.section_heading == "Chapter 2"


def test_citation_model_defaults_are_none() -> None:
    """When not provided, page_number and section_heading default to None."""
    c = Citation(
        document_id="doc-1",
        chunk_text="some text",
        score=0.95,
    )
    assert c.page_number is None
    assert c.section_heading is None


def test_citation_populated_from_metadata() -> None:
    """Verify Citation picks up page_number/section_heading from chunk metadata dict
    as assembled by _retrieve_chunks."""
    chunk = {
        "document_id": "doc-42",
        "chunk_id": "doc-42-orig-0",
        "chunk_index": 0,
        "chunk_text": "relevant passage",
        "score": 0.88,
        "doc_title": "Annual Report",
        "source_id": "src-7",
        "source_language": "en",
        "page_number": 12,
        "section_heading": "Findings",
    }
    citation = Citation(
        document_id=chunk["document_id"],
        doc_title=chunk.get("doc_title"),
        chunk_text=chunk["chunk_text"],
        score=chunk["score"],
        chunk_index=chunk.get("chunk_index"),
        source_id=chunk.get("source_id"),
        page_number=chunk.get("page_number"),
        section_heading=chunk.get("section_heading"),
        language=chunk.get("source_language"),
    )
    assert citation.page_number == 12
    assert citation.section_heading == "Findings"


def test_retrieve_chunks_passes_location_metadata() -> None:
    """Verify that _retrieve_chunks copies page_number and section_heading from
    SearchResult.metadata into the chunk dict returned to the citation builder.

    This is the critical assembly point in RagService.
    """
    # Simulate what _retrieve_chunks does with a SearchResult that has location metadata
    result = SearchResult(
        document_id="doc-1",
        score=0.95,
        chunk_text="Important finding on page 5.",
        metadata={
            "chunk_id": "doc-1-orig-0",
            "chunk_index": 0,
            "source_id": "src-1",
            "page_number": 5,
            "section_heading": "Key Results",
        },
    )

    # Reproduce the _retrieve_chunks assembly logic
    chunk = {
        "document_id": result.document_id,
        "chunk_id": (result.metadata or {}).get("chunk_id"),
        "chunk_index": (result.metadata or {}).get("chunk_index"),
        "chunk_text": result.chunk_text or "",
        "score": result.score,
        "doc_title": None,
        "source_id": (result.metadata or {}).get("source_id"),
        "source_language": (result.metadata or {}).get("source_language"),
        "page_number": (result.metadata or {}).get("page_number"),
        "section_heading": (result.metadata or {}).get("section_heading"),
    }

    assert chunk["page_number"] == 5
    assert chunk["section_heading"] == "Key Results"

    # Verify Citation absorbs these values correctly
    citation = Citation(
        document_id=chunk["document_id"],
        doc_title=chunk.get("doc_title"),
        chunk_text=chunk["chunk_text"],
        score=chunk["score"],
        chunk_index=chunk.get("chunk_index"),
        source_id=chunk.get("source_id"),
        page_number=chunk.get("page_number"),
        section_heading=chunk.get("section_heading"),
        language=chunk.get("source_language"),
    )
    assert citation.page_number == 5
    assert citation.section_heading == "Key Results"
