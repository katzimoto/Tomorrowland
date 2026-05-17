"""ZIP archive text extractor."""

from __future__ import annotations

import mimetypes
import zipfile
from pathlib import Path

from services.extraction.base import AttachmentData


class ZipExtractor:
    """Extract file listing from ZIP archives."""

    def extract(self, path: Path) -> str:
        """Return a newline-separated list of filenames inside the archive."""
        try:
            with zipfile.ZipFile(path, "r") as zf:
                return "\n".join(zf.namelist())
        except (OSError, zipfile.BadZipFile):
            return ""

    def extract_attachments(self, path: Path) -> list[AttachmentData]:
        """Return every file inside the ZIP as an AttachmentData."""
        try:
            result: list[AttachmentData] = []
            with zipfile.ZipFile(path, "r") as zf:
                for name in zf.namelist():
                    info = zf.getinfo(name)
                    if info.is_dir():
                        continue
                    data = zf.read(name)
                    if not data:
                        continue
                    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    result.append(AttachmentData(filename=name, mime_type=mime, data=data))
            return result
        except Exception:
            return []
