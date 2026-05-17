"""Text extraction abstraction."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Protocol


class AttachmentData(NamedTuple):
    """Raw attachment extracted from a container document (email, archive)."""

    filename: str
    mime_type: str
    data: bytes


class Extractor(Protocol):
    """Boundary for file-type-specific text extractors."""

    def extract(self, path: Path) -> str:
        """Return plain text extracted from the file at *path*.

        Returns an empty string when the file is missing, unreadable, or
        produces no extractable text.
        """
        ...
