"""ZIP archive text extractor."""

from __future__ import annotations

import mimetypes
import zipfile
from pathlib import Path

from services.extraction.base import AttachmentData, ExtractionResult


class ZipExtractor:
    """Extract file listing and contents from ZIP archives.

    A single pass over the archive collects both the member names (for search
    indexing) and the raw file bytes (so the pipeline can create child
    documents).  The archive is opened only once.
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Return the archive file listing as text and each member as an attachment."""
        names: list[str] = []
        attachments: list[AttachmentData] = []
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for info in zf.infolist():
                    names.append(info.filename)
                    if info.is_dir():
                        continue
                    data = zf.read(info.filename)
                    if not data:
                        continue
                    mime = mimetypes.guess_type(info.filename)[0] or "application/octet-stream"
                    attachments.append(
                        AttachmentData(filename=info.filename, mime_type=mime, data=data)
                    )
        except (OSError, zipfile.BadZipFile):
            return ExtractionResult(text="")
        except Exception:  # noqa: BLE001
            return ExtractionResult(text="")
        return ExtractionResult(text="\n".join(names), attachments=attachments)
