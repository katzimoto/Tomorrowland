"""Filesystem layout for preview artifacts under ``files_root/previews/``.

Artifacts are addressed by opaque artifact IDs; the DB row's ``files`` map
(artifact_id → relative filename) is the only path source. Resolution
re-validates containment exactly like the download route does.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

_PREVIEWS_DIRNAME = "previews"


class PreviewArtifactStore:
    """Write, resolve, and delete preview artifact files for one deployment."""

    def __init__(self, files_root: Path) -> None:
        self._base = files_root.resolve() / _PREVIEWS_DIRNAME

    def _artifact_dir(self, document_id: UUID, content_sha256: str) -> Path:
        # content_sha256 is hex from our own pipeline, but never trust it as a
        # path segment without validation.
        sha_segment = content_sha256 if content_sha256 else "nosha"
        if not sha_segment.replace("-", "").isalnum():
            raise ValueError("invalid content_sha256 path segment")
        return self._base / str(document_id) / sha_segment

    def write_artifacts(
        self,
        document_id: UUID,
        content_sha256: str,
        artifacts: dict[str, tuple[str, str, bytes]],
    ) -> dict[str, str]:
        """Persist artifacts; returns the artifact_id → relative filename map."""
        target = self._artifact_dir(document_id, content_sha256)
        target.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        for artifact_id, (filename, _content_type, data) in artifacts.items():
            destination = (target / filename).resolve()
            if not destination.is_relative_to(target):
                raise ValueError(f"artifact filename escapes artifact dir: {filename}")
            destination.write_bytes(data)
            files[artifact_id] = filename
        return files

    def resolve(self, document_id: UUID, content_sha256: str, filename: str) -> Path | None:
        """Absolute path for a stored artifact file, or None when missing/unsafe."""
        target = self._artifact_dir(document_id, content_sha256)
        candidate = (target / filename).resolve()
        if not candidate.is_relative_to(self._base):
            logger.warning("artifact path escapes previews root: %s", filename)
            return None
        if not candidate.is_file():
            return None
        return candidate

    def delete(self, document_id: UUID, content_sha256: str) -> None:
        """Remove one version's artifact directory (idempotent)."""
        target = self._artifact_dir(document_id, content_sha256)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
