"""Original file storage — move connector-owned temp files into files_root/originals/.

Called by the ingest loop (scheduler and sync-now) **before** creating the document
record.  The returned path is stored in ``documents.path`` so the download
endpoint can serve it without any additional lookup.

Audio and video files are intentionally excluded — they cannot be meaningfully
served as downloadable originals and are filtered out at ingestion time.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

_SKIP_MIME_PREFIXES = ("audio/", "video/")


def move_to_originals(
    path: str | None,
    mime_type: str,
    files_root: Path,
) -> str | None:
    """Return a durable storage path for *path* under ``files_root/originals/``.

    Rules:
    - Returns ``None`` for no-op cases: *path* is ``None``, MIME is audio/video,
      or the source file no longer exists (logs a warning).
    - If *path* is already inside *files_root* it is already persistent — returned
      as-is without copying.
    - Otherwise the file is moved with ``shutil.move``.  On the same filesystem
      this is an O(1) rename; cross-device transparently falls back to copy+delete.

    The caller should use the returned path (when not ``None``) in place of the
    original *path* when persisting the document record.  If ``None`` is returned
    the caller should keep using the original *path* unchanged.
    """
    if path is None:
        return None
    if any(mime_type.startswith(p) for p in _SKIP_MIME_PREFIXES):
        return None

    src = Path(path).resolve()
    if not src.exists():
        logger.warning("original_store: source file not found, skipping path=%s", path)
        return None

    resolved_root = files_root.resolve()
    if src.is_relative_to(resolved_root):
        # Already under files_root (e.g. Folder connector) — no move needed.
        return str(src)

    # Move to files_root/originals/<uuid><original-suffix> so the file outlives
    # the temp directory it was written to by the connector.
    originals_dir = resolved_root / "originals"
    originals_dir.mkdir(parents=True, exist_ok=True)
    dest = originals_dir / f"{uuid4()}{src.suffix}"
    try:
        shutil.move(str(src), dest)
    except Exception:
        logger.exception("original_store: failed to move src=%s dest=%s", src, dest)
        return None
    logger.debug("original_store: moved src=%s dest=%s", src, dest)
    return str(dest)
