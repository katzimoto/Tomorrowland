"""In-memory section tree derived from flat layout blocks.

Pure functions — no I/O, no state.  Builds a section hierarchy from
the reading-order-sorted blocks of a single document by grouping blocks
by (page, heading boundary).

Usage::

    from services.documents.layout_block_repository import LayoutBlockRepository
    from services.rag.layout_hierarchy import build_section_map

    repo = LayoutBlockRepository(connection)
    blocks = repo.list_by_document(document_id)
    section_map = build_section_map(blocks)
    section = section_map.get((1, "Introduction"))
    # section == SectionInfo(heading_text="Introduction", blocks=[...])
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from services.documents.layout_block_repository import LayoutBlockRepository

from services.documents.models import LayoutBlockRow

# The key type used to look up a section in the map.
# Combines (page_number, section_heading_text) to match chunk metadata.
SectionKey = tuple[int | None, str | None]


class SectionInfo:
    """Describes one section derived from a heading boundary.

    A section starts at a ``heading`` block and continues until the next
    ``heading`` block on the same page, or until the end of the page.
    """

    __slots__ = (
        "heading_block_id",
        "heading_text",
        "blocks",
        "page_number",
    )

    def __init__(
        self,
        heading_block_id: UUID,
        heading_text: str,
        blocks: list[LayoutBlockRow],
        page_number: int | None,
    ) -> None:
        self.heading_block_id = heading_block_id
        self.heading_text = heading_text
        self.blocks = blocks
        self.page_number = page_number

    @property
    def all_text(self) -> str:
        """All block text in this section joined with newlines (heading first)."""
        parts: list[str] = [self.heading_text]
        for b in self.blocks:
            if b.text and b.block_type != "heading":
                parts.append(b.text)
        return "\n".join(p for p in parts if p)

    @property
    def sibling_block_texts(self) -> list[str]:
        """Text of non-heading sibling blocks (content within the section)."""
        return [b.text for b in self.blocks if b.text and b.block_type != "heading"]

    def __repr__(self) -> str:
        return (
            f"SectionInfo(heading={self.heading_text!r}, "
            f"block_count={len(self.blocks)}, page={self.page_number})"
        )


def build_section_map(
    blocks: list[LayoutBlockRow],
) -> dict[SectionKey, SectionInfo]:
    """Build a (page_number, heading_text) → SectionInfo map from flat blocks.

    Parameters
    ----------
    blocks:
        Layout blocks for a single document, ordered by ``reading_order``.
        This is the output of ``LayoutBlockRepository.list_by_document()``.

    Returns
    -------
    dict[SectionKey, SectionInfo]:
        Maps ``(page_number, heading_text)`` to the section's heading block
        and its child content blocks.

    Rules
    -----
    - A ``heading`` block starts a new section.
    - All non-heading blocks after a heading belong to that section until
      the next heading or end of page.
    - When no heading is found on a page, non-heading blocks are assigned
      to a synthetic ``None``-keyed entry (meaning the packer will not
      find a match, and the chunk falls through to flat behaviour).
    - Blocks with ``block_type == "heading"`` that lack meaningful text
      are still used as section boundaries but their ``heading_text`` is
      stored as-is.
    """
    section_map: dict[SectionKey, SectionInfo] = {}

    current_heading_id: UUID | None = None
    current_heading_text: str | None = None
    current_blocks: list[LayoutBlockRow] = []
    current_page: int | None = None

    def _flush() -> None:
        nonlocal current_heading_id, current_heading_text, current_blocks, current_page
        if current_heading_id is not None and current_heading_text is not None:
            key = (current_page, current_heading_text)
            if key not in section_map:
                section_map[key] = SectionInfo(
                    heading_block_id=current_heading_id,
                    heading_text=current_heading_text,
                    blocks=list(current_blocks),
                    page_number=current_page,
                )
        current_heading_id = None
        current_heading_text = None
        current_blocks = []

    for block in blocks:
        # Page boundary: flush current section
        if block.page_number != current_page and current_heading_id is not None:
            _flush()

        current_page = block.page_number

        if block.block_type == "heading":
            # Flush previous section before starting a new one
            if current_heading_id is not None:
                _flush()
            heading_text = block.text or ""
            current_heading_id = block.id
            current_heading_text = heading_text
            current_blocks = []
        else:
            if current_heading_id is not None:
                current_blocks.append(block)
            # Blocks before the first heading are ignored (no section to
            # attribute them to — falls through to flat behaviour).

    # Flush final section
    _flush()

    return section_map


def get_neighborhood(
    blocks: list[LayoutBlockRow],
    page_number: int | None,
    section_heading: str | None,
    *,
    radius: int = 3,
) -> tuple[list[LayoutBlockRow], list[LayoutBlockRow], list[LayoutBlockRow]]:
    """Return (parent_headings, sibling_before, sibling_after) for a section.

    Parameters
    ----------
    blocks:
        Layout blocks for a single document, ordered by ``reading_order``.
    page_number:
        Target page number from the chunk's payload.
    section_heading:
        Target section heading text from the chunk's payload.    radius:
        Maximum number of siblings to return before and after the anchor.

    Returns
    -------
    tuple:
        - **parent_headings**: heading block(s) that contain this section.
          Usually one heading; empty when no heading is found.
        - **sibling_before**: non-heading blocks preceding the anchor
          position within the same section, up to ``radius``.
        - **sibling_after**: non-heading blocks following the anchor
          position within the same section, up to ``radius``.

    Notes
    -----
    The anchor position is the **first non-heading block** in the section.
    Since PR1 does not yet have ``layout_block_id`` in the chunk payload
    (that is PR3 — precise linkage), we cannot pinpoint which block within
    a section a chunk corresponds to.  Anchoring at the first content block
    is a reasonable approximation for PR1: it always includes the parent
    heading and the earliest sibling context.  PR3 will swap to precise
    ``layout_block_id``-based anchoring when the chunk payload carries it.

    When the section is not found (no heading matches), returns three
    empty lists — the caller falls through to flat behaviour."""
    section_map = build_section_map(blocks)
    key = (page_number, section_heading)
    section = section_map.get(key)
    if section is None or not section.blocks:
        return [], [], []

    # Find the anchor position within the section's blocks.
    # The anchor is the first non-heading block that has text.
    anchor_idx = 0
    for i, b in enumerate(section.blocks):
        if b.text and b.block_type != "heading":
            anchor_idx = i
            break

    sibling_before = section.blocks[max(0, anchor_idx - radius) : anchor_idx]
    sibling_after = section.blocks[
        anchor_idx + 1 : min(len(section.blocks), anchor_idx + radius + 1)
    ]

    parent_headings: list[LayoutBlockRow] = []

    # Include the section heading as the parent heading.
    # We reconstruct it from the heading block in the original list.
    for b in blocks:
        if b.id == section.heading_block_id:
            parent_headings.append(b)
            break

    return parent_headings, sibling_before, sibling_after


def resolve_chunk_layout_block_ids(
    chunks: list[dict[str, Any]],
    document_id: UUID,
    layout_repo: LayoutBlockRepository,
) -> None:
    """Try to add ``layout_block_id`` to each chunk dict (mutates in place).

    Called at Qdrant index time (PR3) after page_number / section_heading
    have been resolved.  Looks up layout blocks from the database and, for
    each chunk, finds the first non-heading block in the matching section
    whose text appears in the chunk — that block becomes the anchor used
    by the context packer at query time.

    When layout blocks are missing, unavailable, or no match is found the
    chunk is left unchanged and the packer will fall back to
    ``(page_number, section_heading)`` matching.

    Parameters
    ----------
    chunks:
        List of chunk dicts (with ``page_number``, ``section_heading``,
        and ``text`` keys).  Mutated in place.
    document_id:
        Document UUID whose layout blocks to look up.
    layout_repo:
        ``LayoutBlockRepository`` instance (duck-typed — only needs
        ``list_by_document``).
    """
    if not chunks:
        return

    try:
        blocks = layout_repo.list_by_document(document_id)
    except Exception:
        return

    if not blocks:
        return

    section_map = build_section_map(blocks)

    for chunk in chunks:
        page_raw = chunk.get("page_number")
        heading_raw = chunk.get("section_heading")
        chunk_text = chunk.get("text")

        if page_raw is None or heading_raw is None or not chunk_text:
            continue

        page: int | None = page_raw if isinstance(page_raw, int) else None
        heading: str = str(heading_raw)
        section = section_map.get((page, heading))
        if section is None or not section.blocks:
            continue

        # Find the first content block in this section whose text
        # appears in the chunk — that block is the best anchor.
        chunk_text_str = str(chunk_text)
        for block in section.blocks:
            if block.text and block.text in chunk_text_str:
                chunk["layout_block_id"] = str(block.id)
                break


def section_exists(
    blocks: list[LayoutBlockRow],
    page_number: int | None,
    section_heading: str | None,
) -> bool:
    """Return True when a section matching *(page_number, section_heading)* exists.

    Cheap check — builds the section map internally.
    """
    if not section_heading:
        return False
    key = (page_number, section_heading)
    return key in build_section_map(blocks)


def get_neighborhood_by_block_id(
    blocks: list[LayoutBlockRow],
    layout_block_id: str,
    *,
    radius: int = 3,
) -> tuple[list[LayoutBlockRow], list[LayoutBlockRow], list[LayoutBlockRow]]:
    """Return (parent_headings, sibling_before, sibling_after) anchored at a specific block.

    Unlike :func:`get_neighborhood`, which anchors at the first non-heading
    block in a section (heuristic), this function uses a precise
    ``layout_block_id`` from the chunk payload (PR3) to anchor at the exact
    block the chunk's text starts from.

    Parameters
    ----------
    blocks:
        Layout blocks for a single document, ordered by ``reading_order``.
    layout_block_id:
        UUID string of the anchor layout block (from the chunk's Qdrant payload).
    radius:
        Maximum number of siblings to return before and after the anchor.

    Returns
    -------
    tuple:
        - **parent_headings**: heading block(s) that contain this block.
        - **sibling_before**: non-heading blocks preceding the anchor within
          the same section, up to ``radius``.
        - **sibling_after**: non-heading blocks following the anchor within
          the same section, up to ``radius``.

    When the block ID is not found, returns three empty lists — the caller
    should fall back to :func:`get_neighborhood`.
    """
    try:
        target_id = UUID(layout_block_id)
    except (ValueError, TypeError):
        return [], [], []

    # Find the anchor block and its position in the full block list.
    anchor_block: LayoutBlockRow | None = None
    anchor_pos: int = -1
    for i, b in enumerate(blocks):
        if b.id == target_id:
            anchor_block = b
            anchor_pos = i
            break

    if anchor_block is None:
        return [], [], []

    # Build the section map to find which section this block belongs to.
    section_map = build_section_map(blocks)

    # Find the section containing this block's (page, section_heading).
    # First, find the section heading for this block by walking backwards
    # to the nearest preceding heading block.
    current_section_key: SectionKey | None = None
    for i in range(anchor_pos, -1, -1):
        b = blocks[i]
        if b.block_type == "heading" and b.text:
            current_section_key = (b.page_number, b.text)
            break

    if current_section_key is None or current_section_key not in section_map:
        return [], [], []

    section = section_map[current_section_key]
    if not section.blocks:
        return [], [], []

    # Find the anchor's position within the section's content blocks.
    anchor_section_idx: int = -1
    for i, b in enumerate(section.blocks):
        if b.id == target_id:
            anchor_section_idx = i
            break

    if anchor_section_idx == -1:
        # Block not in this section's content blocks — fall back to
        # first content block heuristic.
        anchor_section_idx = 0

    sibling_before = section.blocks[max(0, anchor_section_idx - radius) : anchor_section_idx]
    sibling_after = section.blocks[
        anchor_section_idx + 1 : min(len(section.blocks), anchor_section_idx + radius + 1)
    ]

    parent_headings: list[LayoutBlockRow] = []
    for b in blocks:
        if b.id == section.heading_block_id:
            parent_headings.append(b)
            break

    return parent_headings, sibling_before, sibling_after
