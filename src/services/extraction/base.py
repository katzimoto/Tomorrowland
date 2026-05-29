"""Text extraction abstraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple, Protocol


class AttachmentData(NamedTuple):
    """Raw attachment extracted from a container document (email, archive)."""

    filename: str
    mime_type: str
    data: bytes


@dataclass
class LocationSegment:
    """Character-range location metadata for a contiguous span of extracted text.

    Start and end are character offsets (Python slicing) into
    ``ExtractionResult.text``.  At least one of *page_number* or
    *section_heading* should be set when the information is available.
    """

    start_char: int
    end_char: int
    page_number: int | None = None
    section_heading: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "start_char": self.start_char,
            "end_char": self.end_char,
        }
        if self.page_number is not None:
            d["page_number"] = self.page_number
        if self.section_heading is not None:
            d["section_heading"] = self.section_heading
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> LocationSegment:
        return LocationSegment(
            start_char=d["start_char"],
            end_char=d["end_char"],
            page_number=d.get("page_number"),
            section_heading=d.get("section_heading"),
        )


@dataclass
class ExtractionResult:
    """Uniform envelope returned by every Extractor.extract() call.

    Container extractors (email, archive) populate *attachments*; all others
    return an empty list.  Downstream pipeline stages are fully file-type-agnostic
    — they never need to know which extractor produced the result.
    """

    text: str
    attachments: list[AttachmentData] = field(default_factory=list)
    location_segments: list[LocationSegment] = field(default_factory=list)


class Extractor(Protocol):
    """Boundary for file-type-specific text extractors."""

    def extract(self, path: Path) -> ExtractionResult:
        """Return extracted content from the file at *path*.

        ``ExtractionResult.text`` is the plain text of the document (empty string
        when the file is missing, unreadable, or produces no extractable text).
        ``ExtractionResult.attachments`` is non-empty only for container formats
        (email, archive) whose embedded files should enter the pipeline as child
        documents.
        """
        ...
