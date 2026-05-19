"""Vault export — group-scoped Markdown bundle of document intelligence."""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from services.documents.repository import DocumentRepository
from services.intelligence.repository import IntelligenceRepository
from shared.db import db_uuid

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


class VaultExportService:
    """Export all documents in a group as a zip of Markdown files.

    Each Markdown file contains the document title, summary, key points,
    entities, and tags.  The caller is responsible for ACL verification.

    ``[[Document Title]]`` wikilinks found in summary and key-point text are
    resolved to Markdown links pointing to the document detail page.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._intel = IntelligenceRepository(connection)
        self._docs = DocumentRepository(connection)

    # ------------------------------------------------------------------
    # Title→ID cache for wikilink resolution
    # ------------------------------------------------------------------

    def _build_title_cache(self, group_id: UUID) -> dict[str, str]:
        """Return {lowercase_title: document_id_string} for all docs in *group_id*."""
        rows = self._connection.execute(
            sa.text("""
                SELECT d.id, d.title
                FROM documents d
                JOIN source_permissions sp ON sp.source_id = d.source_id
                WHERE sp.group_id = :group_id
                  AND d.title IS NOT NULL
                  AND d.title != ''
            """),
            {"group_id": db_uuid(group_id)},
        ).mappings()
        return {str(row["title"]).casefold(): str(row["id"]) for row in rows}

    @staticmethod
    def _resolve_wikilinks(text: str, title_cache: dict[str, str]) -> str:
        """Replace ``[[Title]]`` with ``[Title](/documents/{id})``."""

        def _replacer(match: re.Match[str]) -> str:
            title = match.group(1).strip()
            doc_id = title_cache.get(title.casefold())
            if doc_id:
                return f"[{title}](/documents/{doc_id})"
            return match.group(0)

        return _WIKILINK_RE.sub(_replacer, text)

    # ------------------------------------------------------------------
    # Tag index
    # ------------------------------------------------------------------

    def get_tag_index(
        self, group_id: UUID | None = None, *, allow_all: bool = False
    ) -> list[dict[str, Any]]:
        """Return a tag cloud for *group_id* (or all docs when *allow_all*).

        Each entry contains ``tag``, ``document_count``, and ``documents``
        (list of ``{id, title}``).
        """
        if allow_all:
            rows = self._connection.execute(
                sa.text("""
                    SELECT dt.tag, d.id AS doc_id, d.title
                    FROM document_tags dt
                    JOIN documents d ON d.id = dt.document_id
                    ORDER BY dt.tag, d.title
                """),
            ).mappings()
        else:
            rows = self._connection.execute(
                sa.text("""
                    SELECT dt.tag, d.id AS doc_id, d.title
                    FROM document_tags dt
                    JOIN documents d ON d.id = dt.document_id
                    JOIN source_permissions sp ON sp.source_id = d.source_id
                    WHERE sp.group_id = :group_id
                    ORDER BY dt.tag, d.title
                """),
                {"group_id": db_uuid(group_id)} if group_id else {},
            ).mappings()

        index: dict[str, dict[str, Any]] = {}
        for row in rows:
            tag = str(row["tag"])
            entry = index.setdefault(tag, {"tag": tag, "document_count": 0, "documents": []})
            entry["document_count"] += 1
            entry["documents"].append(
                {"id": str(row["doc_id"]), "title": str(row["title"] or "Untitled")}
            )
        return list(index.values())

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, group_id: UUID) -> io.BytesIO:
        """Build a zip archive of Markdown exports for *group_id*.

        ``[[Title]]`` wikilinks are resolved against all documents in the
        group.  Returns an in-memory ``BytesIO`` buffer containing the zip.
        """
        title_cache = self._build_title_cache(group_id)

        doc_rows = self._connection.execute(
            sa.text("""
                SELECT d.id
                FROM documents d
                JOIN source_permissions sp ON sp.source_id = d.source_id
                WHERE sp.group_id = :group_id
                ORDER BY d.created_at DESC
            """),
            {"group_id": db_uuid(group_id)},
        ).mappings()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for row in doc_rows:
                doc_id = UUID(str(row["id"]))
                markdown = self._build_markdown(doc_id, title_cache)
                if markdown is None:
                    continue
                zf.writestr(f"{doc_id}.md", markdown)

        buf.seek(0)
        return buf

    def _build_markdown(
        self, doc_id: UUID, title_cache: dict[str, str] | None = None
    ) -> str | None:
        """Build a Markdown string for *doc_id*, or None if the doc is gone.

        When *title_cache* is provided, ``[[Title]]`` wikilinks in the
        summary and key points are resolved to document links.
        """
        doc = self._docs.get_by_id(doc_id)
        if doc is None:
            return None
        title = doc.title or "Untitled"
        lines: list[str] = [
            f"# {title}",
            "",
            f"- **Document ID:** `{doc_id}`",
            f"- **Source:** {doc.source}",
            f"- **Language:** {doc.source_language or 'unknown'}",
            "",
        ]

        summary = self._intel.get_summary(doc_id)
        if summary is not None:
            text = summary["summary"]
            if title_cache:
                text = self._resolve_wikilinks(text, title_cache)
            lines.extend(["## Summary", "", text, ""])

        key_points = self._intel.get_key_points(doc_id)
        if key_points:
            lines.append("## Key Points")
            lines.append("")
            for kp in key_points:
                resolved = self._resolve_wikilinks(kp, title_cache) if title_cache else kp
                lines.append(f"- {resolved}")
            lines.append("")

        entities = self._intel.get_entities(doc_id)
        if entities:
            lines.append("## Entities")
            lines.append("")
            lines.append("| Name | Type | Frequency |")
            lines.append("|------|------|-----------|")
            for e in entities:
                lines.append(f"| {e['name']} | {e['type']} | {e['frequency']} |")
            lines.append("")

        tags = self._intel.get_tags(doc_id)
        if tags:
            lines.extend(["## Tags", "", ", ".join(tags), ""])

        return "\n".join(lines)
