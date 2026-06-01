"""TAR archive text extractor."""

from __future__ import annotations

import logging
import mimetypes
import tarfile
from pathlib import Path

from services.extraction.base import AttachmentData, ExtractionResult

logger = logging.getLogger(__name__)


class TarExtractor:
    """Extract file listing and contents from TAR archives.

    A single pass over the archive collects both the member names (for search
    indexing) and the raw file bytes (so the pipeline can create child
    documents).  The archive is opened only once.
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Return the archive file listing as text and each member as an attachment."""
        names: list[str] = []
        attachments: list[AttachmentData] = []
        try:
            with tarfile.open(path, "r:*") as tf:
                for member in tf.getmembers():
                    names.append(member.name)
                    if not member.isfile():
                        continue
                    f = tf.extractfile(member)
                    if f is None:
                        continue
                    data = f.read()
                    if not data:
                        continue
                    mime = mimetypes.guess_type(member.name)[0] or "application/octet-stream"
                    attachments.append(
                        AttachmentData(filename=member.name, mime_type=mime, data=data)
                    )
        except (OSError, tarfile.TarError):
            return ExtractionResult(text="")
        except Exception:  # noqa: BLE001
            logger.debug("tar extraction failed for path=%s", path, exc_info=True)
            return ExtractionResult(text="")
        return ExtractionResult(text="\n".join(names), attachments=attachments)
