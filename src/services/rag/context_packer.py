"""Context packing — expand chunk text with parent/sibling layout blocks.

``expand_chunks()`` runs after retrieval (and optional reranking) and
before ``_assemble_context()``.  When the hierarchy expansion feature is
enabled, it looks up each chunk's ``(document_id, page_number,
section_heading)`` in the document's layout blocks (via
``LayoutBlockRepository``) and prepends the parent heading + adjacent
sibling text to the chunk's ``chunk_text``.

Design rules
------------
- **Same-document only**: expansion never adds blocks from another document.
- **No eviction**: expanded chunks compete for ``max_tokens_context``
  alongside original chunks via the existing budget in _assemble_context.
  The packer never removes an original chunk.
- **Flat fallback**: any chunk whose document lacks layout blocks, or whose
  ``(page, section_heading)`` is not found, passes through unchanged.
- **Permission-safe**: expansion sources all blocks from the same document
  whose chunks were already authorised by the retrieval ACL.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from services.documents.layout_block_repository import LayoutBlockRepository
from services.rag.layout_hierarchy import build_section_map, get_neighborhood
from services.rag.trace_models import ContextPackingTrace

logger = logging.getLogger(__name__)

_EXPANSION_RADIUS = 3
"""Default number of siblings to include before and after the anchor."""


def expand_chunks(
    chunks: list[dict[str, Any]],
    *,
    layout_repo: LayoutBlockRepository,
    enabled: bool,
    budget_words: int,
) -> tuple[list[dict[str, Any]], ContextPackingTrace]:
    """Expand chunk text with parent/sibling layout blocks from the same document.

    Parameters
    ----------
    chunks:
        The final chunk list (already deduplicated, filtered, and truncated
        to top-k) that will be passed to ``_assemble_context``.
    layout_repo:
        Repository for reading layout blocks from the database.
    enabled:
        When False, returns chunks unchanged with an empty trace.
    budget_words:
        Total word budget for context assembly. Used as a rough cap for
        expansion — if estimated expansion exceeds the available budget,
        expansions are dropped.

    Returns
    -------
    tuple[list[dict[str, Any]], ContextPackingTrace]:
        - (Possibly expanded) chunks
        - Trace of what was expanded and why
    """
    # Accumulate trace fields in mutable locals, then build the frozen trace at the end.
    expansion_applied = False
    expanded_chunk_ids: list[str] = []
    parent_blocks_added = 0
    sibling_blocks_added = 0
    dropped_for_budget = 0
    sections_matched = 0
    sections_not_found = 0

    if not enabled or not chunks:
        return chunks, ContextPackingTrace(budget_words=budget_words)

    total_expansion_words = 0

    for chunk in chunks:
        document_id_str: str | None = chunk.get("document_id")
        page_number: int | None = chunk.get("page_number")
        section_heading: str | None = chunk.get("section_heading")
        chunk_id: str | None = chunk.get("chunk_id")

        if not document_id_str or not section_heading:
            sections_not_found += 1
            continue

        try:
            doc_uuid = UUID(document_id_str)
        except (ValueError, TypeError):
            sections_not_found += 1
            continue

        # Load blocks for this document
        try:
            blocks = layout_repo.list_by_document(doc_uuid)
        except Exception:
            logger.warning(
                "Layout blocks unavailable for document_id=%s — flat fallback",
                document_id_str,
            )
            sections_not_found += 1
            continue

        if not blocks:
            sections_not_found += 1
            continue

        # Check if the section exists
        section_map = build_section_map(blocks)
        key = (page_number, section_heading)
        section = section_map.get(key)

        if section is None:
            sections_not_found += 1
            continue

        sections_matched += 1

        # Get neighborhood: parent headings + sibling blocks
        parent_headings, sibling_before, sibling_after = get_neighborhood(
            blocks,
            page_number,
            section_heading,
            radius=_EXPANSION_RADIUS,
        )

        if not parent_headings and not sibling_before and not sibling_after:
            sections_not_found += 1
            continue

        # Build expanded text
        expanded_parts: list[str] = []

        for h in parent_headings:
            if h.text:
                expanded_parts.append(f"Section: {h.text}")
                parent_blocks_added += 1

        for sib in sibling_before:
            if sib.text:
                expanded_parts.append(sib.text)
                sibling_blocks_added += 1

        # Insert the original chunk text
        original_text = chunk.get("chunk_text", "")

        for sib in sibling_after:
            if sib.text:
                expanded_parts.append(sib.text)
                sibling_blocks_added += 1

        if not expanded_parts:
            continue

        expansion_text = "\n".join(expanded_parts)
        expansion_word_count = len(expansion_text.split())

        # Budget check: if we've already exceeded budget, drop this expansion
        if total_expansion_words + expansion_word_count > budget_words:
            dropped_for_budget += 1
            continue

        # Prepend expansion text to the chunk's existing text
        new_text = f"{expansion_text}\n\n{original_text}" if original_text else expansion_text
        chunk["chunk_text"] = new_text
        total_expansion_words += expansion_word_count

        if chunk_id:
            expanded_chunk_ids.append(chunk_id)
        expansion_applied = True

    trace = ContextPackingTrace(
        expansion_applied=expansion_applied,
        expanded_chunk_ids=expanded_chunk_ids,
        parent_blocks_added=parent_blocks_added,
        sibling_blocks_added=sibling_blocks_added,
        budget_words=budget_words,
        dropped_for_budget=dropped_for_budget,
        sections_matched=sections_matched,
        sections_not_found=sections_not_found,
    )
    return chunks, trace
