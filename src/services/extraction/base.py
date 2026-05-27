"""Text extraction abstraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Protocol


class AttachmentData(NamedTuple):
    """Raw attachment extracted from a container document (email, archive)."""

    filename: str
    mime_type: str
    data: bytes


@dataclass
class ExtractionResult:
    """Uniform envelope returned by every Extractor.extract() call.

    Container extractors (email, archive) populate *attachments*; all others
    return an empty list.  Downstream pipeline stages are fully file-type-agnostic
    — they never need to know which extractor produced the result.
    """

    text: str
    attachments: list[AttachmentData] = field(default_factory=list)


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
