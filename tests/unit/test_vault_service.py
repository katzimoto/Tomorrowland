"""Unit tests for VaultExportService — group-scoped Markdown export."""

from __future__ import annotations

import zipfile
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from services.intelligence.repository import IntelligenceRepository
from services.vault.service import VaultExportService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_group_with_source(
    connection: sa.Connection,
    group_name: str = "test-group",
    source_name: str = "test-source",
) -> tuple[UUID, UUID]:
    """Return (group_id, source_id) after creating them and granting access."""
    auth = AuthRepository(connection)
    group_id = auth.ensure_group(group_name)
    source_id = auth.create_ingestion_source(source_name)
    auth.grant_source_to_group(source_id, group_id)
    return group_id, source_id


def _create_doc(
    connection: sa.Connection,
    source_id: UUID,
    title: str = "Test Document",
) -> UUID:
    repo = DocumentRepository(connection)
    doc = repo.create(
        source_id=source_id,
        external_id=f"doc-{uuid4().hex[:8]}",
        source="folder",
        mime_type="text/plain",
        title=title,
    )
    assert doc is not None
    return doc.id


def _add_tags(connection: sa.Connection, doc_id: UUID, tags: list[str]) -> None:
    IntelligenceRepository(connection).replace_tags(doc_id, tags)


def _add_summary(connection: sa.Connection, doc_id: UUID, summary: str) -> None:
    IntelligenceRepository(connection).upsert_summary(doc_id, summary, model="test-model")


def _add_entity(
    connection: sa.Connection, doc_id: UUID, name: str, entity_type: str = "organization"
) -> None:
    intel = IntelligenceRepository(connection)
    entity_id = intel.upsert_entity(name, entity_type)
    intel.link_document_entity(doc_id, entity_id, frequency=3)


# ---------------------------------------------------------------------------
# _resolve_wikilinks (static, no DB)
# ---------------------------------------------------------------------------


def test_resolve_wikilinks_known_title_becomes_link() -> None:
    cache = {"alpha doc": "doc-id-111"}
    result = VaultExportService._resolve_wikilinks("See [[Alpha Doc]] for details.", cache)
    assert result == "See [Alpha Doc](/documents/doc-id-111) for details."


def test_resolve_wikilinks_unknown_title_left_unchanged() -> None:
    cache: dict[str, str] = {}
    result = VaultExportService._resolve_wikilinks("See [[Missing Doc]] here.", cache)
    assert result == "See [[Missing Doc]] here."


def test_resolve_wikilinks_case_insensitive_lookup() -> None:
    cache = {"alpha doc": "doc-id-111"}
    result = VaultExportService._resolve_wikilinks("Ref [[ALPHA DOC]] here.", cache)
    assert result == "Ref [ALPHA DOC](/documents/doc-id-111) here."


def test_resolve_wikilinks_multiple_in_one_string() -> None:
    cache = {"alpha": "aaa", "beta": "bbb"}
    result = VaultExportService._resolve_wikilinks("[[Alpha]] and [[Beta]].", cache)
    assert result == "[Alpha](/documents/aaa) and [Beta](/documents/bbb)."


def test_resolve_wikilinks_strips_whitespace_inside_brackets() -> None:
    cache = {"alpha": "aaa"}
    result = VaultExportService._resolve_wikilinks("[[ Alpha ]]", cache)
    assert result == "[Alpha](/documents/aaa)"


# ---------------------------------------------------------------------------
# get_tag_index
# ---------------------------------------------------------------------------


def test_get_tag_index_empty_group_returns_empty_list(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, _ = _setup_group_with_source(conn)
        service = VaultExportService(conn)
        result = service.get_tag_index(group_id)
    assert result == []


def test_get_tag_index_groups_docs_by_tag(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, source_id = _setup_group_with_source(conn)
        doc_a = _create_doc(conn, source_id, "Alpha")
        doc_b = _create_doc(conn, source_id, "Beta")
        _add_tags(conn, doc_a, ["security", "ai"])
        _add_tags(conn, doc_b, ["security"])
        service = VaultExportService(conn)
        index = service.get_tag_index(group_id)

    by_tag = {entry["tag"]: entry for entry in index}
    assert "security" in by_tag
    assert by_tag["security"]["document_count"] == 2
    assert "ai" in by_tag
    assert by_tag["ai"]["document_count"] == 1
    # verify document ids are present (normalize: SQLite stores undashed hex)
    security_ids = {UUID(d["id"]) for d in by_tag["security"]["documents"]}
    assert doc_a in security_ids
    assert doc_b in security_ids


def test_get_tag_index_allow_all_returns_across_groups(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        _, source_a = _setup_group_with_source(conn, "group-a", "source-a")
        _, source_b = _setup_group_with_source(conn, "group-b", "source-b")
        doc_a = _create_doc(conn, source_a, "DocA")
        doc_b = _create_doc(conn, source_b, "DocB")
        _add_tags(conn, doc_a, ["cross"])
        _add_tags(conn, doc_b, ["cross"])
        service = VaultExportService(conn)
        index = service.get_tag_index(allow_all=True)

    by_tag = {entry["tag"]: entry for entry in index}
    assert "cross" in by_tag
    assert by_tag["cross"]["document_count"] == 2


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_export_empty_group_creates_empty_zip(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, _ = _setup_group_with_source(conn)
        service = VaultExportService(conn)
        buf = service.export(group_id)

    with zipfile.ZipFile(buf) as zf:
        assert zf.namelist() == []


def test_export_creates_md_file_per_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, source_id = _setup_group_with_source(conn)
        doc_a = _create_doc(conn, source_id, "Alpha")
        doc_b = _create_doc(conn, source_id, "Beta")
        service = VaultExportService(conn)
        buf = service.export(group_id)

    with zipfile.ZipFile(buf) as zf:
        names = set(zf.namelist())
        assert f"{doc_a}.md" in names
        assert f"{doc_b}.md" in names


def test_export_md_contains_title(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, source_id = _setup_group_with_source(conn)
        doc_id = _create_doc(conn, source_id, "My Report")
        service = VaultExportService(conn)
        buf = service.export(group_id)

    with zipfile.ZipFile(buf) as zf:
        content = zf.read(f"{doc_id}.md").decode()
    assert "# My Report" in content


# ---------------------------------------------------------------------------
# _build_markdown
# ---------------------------------------------------------------------------


def test_build_markdown_minimal_doc(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, source_id = _setup_group_with_source(conn)
        doc_id = _create_doc(conn, source_id, "Minimal")
        service = VaultExportService(conn)
        md = service._build_markdown(doc_id)

    assert md is not None
    assert "# Minimal" in md
    assert str(doc_id) in md


def test_build_markdown_returns_none_for_missing_doc(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        service = VaultExportService(conn)
        result = service._build_markdown(uuid4())
    assert result is None


def test_build_markdown_includes_summary(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, source_id = _setup_group_with_source(conn)
        doc_id = _create_doc(conn, source_id, "Summarised")
        _add_summary(conn, doc_id, "This is the summary text.")
        service = VaultExportService(conn)
        md = service._build_markdown(doc_id)

    assert md is not None
    assert "## Summary" in md
    assert "This is the summary text." in md


def test_build_markdown_includes_entities_table(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, source_id = _setup_group_with_source(conn)
        doc_id = _create_doc(conn, source_id, "Entity Doc")
        _add_entity(conn, doc_id, "Acme Corp", "organization")
        service = VaultExportService(conn)
        md = service._build_markdown(doc_id)

    assert md is not None
    assert "## Entities" in md
    assert "Acme Corp" in md


def test_build_markdown_includes_tags(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, source_id = _setup_group_with_source(conn)
        doc_id = _create_doc(conn, source_id, "Tagged Doc")
        _add_tags(conn, doc_id, ["security", "compliance"])
        service = VaultExportService(conn)
        md = service._build_markdown(doc_id)

    assert md is not None
    assert "## Tags" in md
    assert "security" in md
    assert "compliance" in md


def test_build_markdown_resolves_wikilinks_in_summary(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        group_id, source_id = _setup_group_with_source(conn)
        doc_a = _create_doc(conn, source_id, "Target Doc")
        doc_b = _create_doc(conn, source_id, "Referencing Doc")
        _add_summary(conn, doc_b, "See [[Target Doc]] for more information.")
        service = VaultExportService(conn)
        cache = service._build_title_cache(group_id)
        md = service._build_markdown(doc_b, title_cache=cache)

    assert md is not None
    # The link target is the cached id string (dialect-specific formatting).
    assert f"[Target Doc](/documents/{cache['target doc']})" in md
    assert UUID(cache["target doc"]) == doc_a
