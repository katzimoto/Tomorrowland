"""TAR archive text extractor."""

from __future__ import annotations

import mimetypes
import tarfile
from pathlib import Path

from services.extraction.base import AttachmentData


class TarExtractor:
    """Extract file listing from TAR archives."""

    def extract(self, path: Path) -> str:
        """Return a newline-separated list of filenames inside the archive."""
        try:
            with tarfile.open(path, "r:*") as tf:
                return "\n".join(m.name for m in tf.getmembers())
        except (OSError, tarfile.TarError):
            return ""

    def extract_attachments(self, path: Path) -> list[AttachmentData]:
        """Return every regular file inside the TAR as an AttachmentData."""
        try:
            result: list[AttachmentData] = []
            with tarfile.open(path, "r:*") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    f = tf.extractfile(member)
                    if f is None:
                        continue
                    data = f.read()
                    if not data:
                        continue
                    mime = mimetypes.guess_type(member.name)[0] or "application/octet-stream"
                    result.append(AttachmentData(filename=member.name, mime_type=mime, data=data))
            return result
        except Exception:
            return []
