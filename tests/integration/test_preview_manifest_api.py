from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import (
    DocumentRelationshipRepository,
    DocumentRepository,
)
from services.preview.render import render_document_preview
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32
FIXTURES = Path(__file__).parent.parent / "fixtures" / "mail"


def _settings(files_root: Path) -> Settings:
    return Settings(
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        rabbitmq_enabled=False,
        feature_meilisearch_search=False,
        files_root=files_root,
    )


def _setup_users(engine: Engine) -> None:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
        auth_repo.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )
        auth_repo.create_local_user(
            email="outsider@example.com",
            password_hash=hash_password("secret"),
            display_name="Outsider",
            is_admin=False,
            group_names=["others"],
        )


def _token(client: TestClient, email: str) -> str:
    login = client.post("/auth/login", json={"email": email, "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _create_doc(
    engine: Engine,
    *,
    group_name: str = "users",
    mime_type: str = "message/rfc822",
    path: str | None = None,
    sha256: str = "shaone",
    external_id: str = "mail:msg-1",
) -> tuple[str, str]:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("Mail Source")
        auth_repo.grant_source_to_group(source_id, group_id)
        doc = DocumentRepository(connection).create(
            source_id=source_id,
            external_id=external_id,
            source="folder",
            mime_type=mime_type,
            title="Test Mail",
            path=path,
            sha256=sha256,
        )
        assert doc is not None
        return str(source_id), str(doc.id)


def _copy_fixture(files_root: Path, name: str) -> Path:
    files_root.mkdir(parents=True, exist_ok=True)
    target = files_root / name
    shutil.copyfile(FIXTURES / name, target)
    return target


def _client(engine: Engine, files_root: Path) -> TestClient:
    return TestClient(create_app(engine, _settings(files_root)))


def test_email_manifest_lifecycle_pending_to_ready(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    eml = _copy_fixture(files_root, "html-inline.eml")
    _source_id, doc_id = _create_doc(migrated_engine, path=str(eml))
    client = _client(migrated_engine, files_root)
    token = _token(client, "user@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    first = client.get(f"/preview/{doc_id}/manifest", headers=auth)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "pending"
    assert body["renderer"] == "email"
    assert body["retry_after_ms"] is not None

    # The job row was enqueued even with RabbitMQ disabled.
    with migrated_engine.begin() as connection:
        count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM pipeline_jobs WHERE job_type = 'preview_render'"
        ).scalar()
    assert count == 1

    # Drive the render the way the preview worker would.
    with migrated_engine.begin() as connection:
        status = render_document_preview(connection, _settings(files_root), UUID(doc_id))
    assert status == "ready"

    second = client.get(f"/preview/{doc_id}/manifest", headers=auth)
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "ready"
    assert body["email"]["subject"] == "Design proposal"
    assert body["email"]["blocked_remote_images"] == 1
    assert body["retry_after_ms"] is None
    artifact_ids = {a["id"] for a in body["artifacts"]}
    assert {"body-html", "body-text"} <= artifact_ids


def test_email_html_artifact_served_with_csp(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    eml = _copy_fixture(files_root, "malicious.eml")
    _source_id, doc_id = _create_doc(migrated_engine, path=str(eml))
    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}

    client.get(f"/preview/{doc_id}/manifest", headers=auth)
    with migrated_engine.begin() as connection:
        render_document_preview(connection, _settings(files_root), UUID(doc_id))

    response = client.get(f"/preview/{doc_id}/artifact/body-html", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "<script" not in response.text
    assert "javascript:" not in response.text

    missing = client.get(f"/preview/{doc_id}/artifact/no-such-artifact", headers=auth)
    assert missing.status_code == 404


def test_manifest_requires_source_grant(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    eml = _copy_fixture(files_root, "plain.eml")
    _source_id, doc_id = _create_doc(migrated_engine, path=str(eml))
    client = _client(migrated_engine, files_root)
    outsider = {"Authorization": f"Bearer {_token(client, 'outsider@example.com')}"}

    response = client.get(f"/preview/{doc_id}/manifest", headers=outsider)
    assert response.status_code in (403, 404)
    artifact = client.get(f"/preview/{doc_id}/artifact/body-html", headers=outsider)
    assert artifact.status_code in (403, 404)


def test_text_document_manifest_ready_immediately(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    files_root.mkdir()
    text_file = files_root / "note.txt"
    text_file.write_text("hello")
    _source_id, doc_id = _create_doc(
        migrated_engine, mime_type="text/plain", path=str(text_file), external_id="file:note"
    )
    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}

    response = client.get(f"/preview/{doc_id}/manifest", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["renderer"] == "text"
    assert body["artifacts"] == []

    # No render job for ready-immediate kinds.
    with migrated_engine.begin() as connection:
        count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM pipeline_jobs WHERE job_type = 'preview_render'"
        ).scalar()
    assert count == 0


def test_office_document_enqueues_worker_render(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    files_root.mkdir()
    docx = files_root / "doc1.docx"
    docx.write_bytes(b"fake-docx")
    _source_id, doc_id = _create_doc(
        migrated_engine,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        path=str(docx),
        external_id="file:doc1",
    )
    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}

    body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    assert body["status"] == "pending"
    assert body["kind"] == "office_doc"
    assert body["renderer"] == "libreoffice_pdf"

    with migrated_engine.begin() as connection:
        count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM pipeline_jobs WHERE job_type = 'preview_render'"
        ).scalar()
    assert count == 1


def test_corrupt_email_fails_terminally(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    files_root.mkdir()
    missing = files_root / "gone.eml"  # path recorded but file absent
    _source_id, doc_id = _create_doc(migrated_engine, path=str(missing))
    client = _client(migrated_engine, files_root)
    admin = {"Authorization": f"Bearer {_token(client, 'admin@example.com')}"}
    user = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}

    client.get(f"/preview/{doc_id}/manifest", headers=user)
    with migrated_engine.begin() as connection:
        status = render_document_preview(connection, _settings(files_root), UUID(doc_id))
    assert status == "failed"

    body = client.get(f"/preview/{doc_id}/manifest", headers=user).json()
    assert body["status"] == "failed"
    assert body["error"]["category"] == "not_found"
    assert body["error"]["detail"] is None  # non-admin sees no detail

    # Failed is terminal: rendering again does not flip the status.
    with migrated_engine.begin() as connection:
        assert render_document_preview(connection, _settings(files_root), UUID(doc_id)) == "failed"

    admin_body = client.get(f"/preview/{doc_id}/manifest", headers=admin).json()
    assert admin_body["error"]["category"] == "not_found"


def test_oversized_email_fails_with_category(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    eml = _copy_fixture(files_root, "plain.eml")
    _source_id, doc_id = _create_doc(migrated_engine, path=str(eml))
    settings = _settings(files_root)
    settings.preview_max_file_bytes = 10

    with migrated_engine.begin() as connection:
        status = render_document_preview(connection, settings, UUID(doc_id))
    assert status == "failed"

    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}
    body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    assert body["error"]["category"] == "file_too_large"


def test_admin_rerender_resets_failed_state(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    eml = _copy_fixture(files_root, "plain.eml")
    _source_id, doc_id = _create_doc(migrated_engine, path=str(eml))
    client = _client(migrated_engine, files_root)
    admin = {"Authorization": f"Bearer {_token(client, 'admin@example.com')}"}
    user = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}

    # Force a failure with a tiny size limit, then rerender with sane limits.
    failing = _settings(files_root)
    failing.preview_max_file_bytes = 10
    client.get(f"/preview/{doc_id}/manifest", headers=user)
    with migrated_engine.begin() as connection:
        assert render_document_preview(connection, failing, UUID(doc_id)) == "failed"

    forbidden = client.post(f"/admin/preview/{doc_id}/rerender", headers=user)
    assert forbidden.status_code == 403

    rerender = client.post(f"/admin/preview/{doc_id}/rerender", headers=admin)
    assert rerender.status_code == 200
    assert rerender.json()["status"] == "pending"

    # Next manifest request re-creates the row; render now succeeds.
    body = client.get(f"/preview/{doc_id}/manifest", headers=user).json()
    assert body["status"] == "pending"
    with migrated_engine.begin() as connection:
        assert render_document_preview(connection, _settings(files_root), UUID(doc_id)) == "ready"


def test_attachment_resolved_to_child_document(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    eml = _copy_fixture(files_root, "attachments.eml")
    _source_id, doc_id = _create_doc(migrated_engine, path=str(eml))

    with migrated_engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        parent = doc_repo.get_by_id(UUID(doc_id))
        assert parent is not None
        child = doc_repo.create(
            source_id=parent.source_id,
            external_id="mail:msg-1::attachment::contract.pdf::abc",
            source="folder",
            mime_type="application/pdf",
            title="contract.pdf",
            sha256="childsha",
        )
        assert child is not None
        DocumentRelationshipRepository(connection).create_relationship(
            parent_id=UUID(doc_id),
            child_id=child.id,
            relationship_type="attachment",
            path_in_parent="contract.pdf",
        )
        render_document_preview(connection, _settings(files_root), UUID(doc_id))
        child_id = str(child.id)

    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}
    body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    attachments = {a["filename"]: a for a in body["email"]["attachments"]}
    assert attachments["contract.pdf"]["document_id"] == child_id
    assert attachments["contract.pdf"]["preview_available"] is True
    assert attachments["appendix.txt"]["document_id"] is None


def test_new_version_gets_fresh_manifest(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    eml = _copy_fixture(files_root, "plain.eml")
    _source_id, doc_id = _create_doc(migrated_engine, path=str(eml), sha256="shaone")
    with migrated_engine.begin() as connection:
        render_document_preview(connection, _settings(files_root), UUID(doc_id))

    # Same source item re-ingested with different content → new document row.
    with migrated_engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        parent = doc_repo.get_by_id(UUID(doc_id))
        assert parent is not None
        newer = doc_repo.create(
            source_id=parent.source_id,
            external_id="mail:msg-1",
            source="folder",
            mime_type="message/rfc822",
            title="Test Mail v2",
            path=str(eml),
            sha256="shatwo",
        )
        assert newer is not None
        newer_id = str(newer.id)

    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}
    old_body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    new_body = client.get(f"/preview/{newer_id}/manifest", headers=auth).json()
    assert old_body["status"] == "ready"
    assert new_body["status"] == "pending"
    assert old_body["cache_key"] != new_body["cache_key"]


def test_msg_manifest_renders_through_worker_path(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    files_root.mkdir()
    # A real .msg binary cannot be generated offline; mock extract_msg.Message
    # at the renderer boundary (the repo's established pattern for MSG).
    msg_path = files_root / "sample.msg"
    msg_path.write_bytes(b"placeholder-msg-bytes")
    _source_id, doc_id = _create_doc(
        migrated_engine,
        mime_type="application/vnd.ms-outlook",
        path=str(msg_path),
        external_id="mail:outlook-1",
    )
    fake_msg = SimpleNamespace(
        subject="Outlook preview",
        sender="alice@example.com",
        to="bob@example.com",
        cc="",
        bcc="",
        date="2026-01-10T09:00:00",
        messageId="<o-1@example.com>",
        inReplyTo=None,
        htmlBody=b"<p>Outlook body</p>",
        body="Outlook body",
        attachments=[],
        close=lambda: None,
    )

    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}

    first = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    assert first["status"] == "pending"
    assert first["kind"] == "email"

    with (
        patch("services.preview.msg_renderer.extract_msg.Message", return_value=fake_msg),
        migrated_engine.begin() as connection,
    ):
        status = render_document_preview(connection, _settings(files_root), UUID(doc_id))
    assert status == "ready"

    body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    assert body["status"] == "ready"
    assert body["email"]["subject"] == "Outlook preview"
    assert body["email"]["has_html_body"] is True


def _make_pdf_bytes(pages: int) -> bytes:
    import io as _io

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = _io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_office_docx_manifest_renders_to_pdf(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    files_root.mkdir()
    docx = files_root / "report.docx"
    docx.write_bytes(b"fake-docx-bytes")
    _source_id, doc_id = _create_doc(
        migrated_engine,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        path=str(docx),
        external_id="file:report",
    )
    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}

    first = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    assert first["status"] == "pending"
    assert first["renderer"] == "libreoffice_pdf"
    assert first["kind"] == "office_doc"

    pdf_bytes = _make_pdf_bytes(4)

    def _fake_convert(src: Path, out_dir: Path, timeout: float) -> Path:
        target = out_dir / f"{src.stem}.pdf"
        target.write_bytes(pdf_bytes)
        return target

    with (
        patch("services.preview.office_pdf._convert_to_pdf", side_effect=_fake_convert),
        migrated_engine.begin() as connection,
    ):
        status = render_document_preview(connection, _settings(files_root), UUID(doc_id))
    assert status == "ready"

    body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    assert body["status"] == "ready"
    assert body["renderer"] == "libreoffice_pdf"
    assert body["office"]["pdf_artifact_id"] == "converted-pdf"
    assert body["office"]["page_count"] == 4
    assert body["navigation"]["unit"] == "page"
    assert body["navigation"]["count"] == 4

    artifact = client.get(f"/preview/{doc_id}/artifact/converted-pdf", headers=auth)
    assert artifact.status_code == 200
    assert artifact.headers["content-type"] == "application/pdf"
    assert artifact.content == pdf_bytes


def test_office_pptx_navigation_unit_is_slide(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    files_root.mkdir()
    pptx = files_root / "deck.pptx"
    pptx.write_bytes(b"fake-pptx")
    _source_id, doc_id = _create_doc(
        migrated_engine,
        mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        path=str(pptx),
        external_id="file:deck",
    )
    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}
    client.get(f"/preview/{doc_id}/manifest", headers=auth)

    def _fake_convert(src: Path, out_dir: Path, timeout: float) -> Path:
        target = out_dir / f"{src.stem}.pdf"
        target.write_bytes(_make_pdf_bytes(2))
        return target

    with (
        patch("services.preview.office_pdf._convert_to_pdf", side_effect=_fake_convert),
        migrated_engine.begin() as connection,
    ):
        render_document_preview(connection, _settings(files_root), UUID(doc_id))

    body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    assert body["kind"] == "office_slides"
    assert body["navigation"]["unit"] == "slide"


def test_office_render_fails_when_soffice_unavailable(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    files_root.mkdir()
    docx = files_root / "x.docx"
    docx.write_bytes(b"fake")
    _source_id, doc_id = _create_doc(
        migrated_engine,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        path=str(docx),
        external_id="file:x",
    )
    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}
    client.get(f"/preview/{doc_id}/manifest", headers=auth)

    with (
        patch("services.preview.office_pdf.subprocess.run", side_effect=FileNotFoundError()),
        migrated_engine.begin() as connection,
    ):
        status = render_document_preview(connection, _settings(files_root), UUID(doc_id))
    assert status == "failed"

    body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    assert body["status"] == "failed"
    assert body["error"]["category"] == "renderer_unavailable"


def test_office_sheet_still_text_fallback_in_s4(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    files_root = tmp_path / "files"
    files_root.mkdir()
    xlsx = files_root / "data.xlsx"
    xlsx.write_bytes(b"fake-xlsx")
    _source_id, doc_id = _create_doc(
        migrated_engine,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        path=str(xlsx),
        external_id="file:data",
    )
    client = _client(migrated_engine, files_root)
    auth = {"Authorization": f"Bearer {_token(client, 'user@example.com')}"}
    body = client.get(f"/preview/{doc_id}/manifest", headers=auth).json()
    # Spreadsheets are not rendered via the worker yet (sheet grids come later).
    assert body["status"] == "ready"
    assert body["kind"] == "office_sheets"
    assert body["renderer"] == "text"
