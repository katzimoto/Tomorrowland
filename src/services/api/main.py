import hashlib
import mimetypes
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.auth.jwt import JwtService
from services.auth.ldap import LdapAuthenticator
from services.auth.models import LoginRequest, LoginResponse, TokenPayload, UserResponse
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.auth.service import AuthService
from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.permissions.enforcer import assert_doc_access, require_admin
from services.pipeline.worker import PipelineWorker
from services.search.elastic import ElasticsearchSearchClient
from services.search.encoder import MockEncoder
from services.search.hybrid import merge_results
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.config import Settings
from shared.db import to_uuid

AUTH_SCHEME = "Bearer "


def _fmt_dt(value: Any) -> str | None:
    """Format a datetime value (object or string) to ISO format."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


class SearchRequest(BaseModel):
    """Search request body."""

    query: str
    page: int = 1
    page_size: int = Field(default=10, ge=1, le=100)


class SearchResultItem(BaseModel):
    """Single search result."""

    doc_id: str
    score: float
    title: str | None = None
    chunk_text: str | None = None


class SearchResponse(BaseModel):
    """Search response."""

    results: list[SearchResultItem]
    total: int


class PreviewResponse(BaseModel):
    """Document preview response."""

    doc_id: str
    title: str | None = None
    mime_type: str
    translation_quality: str | None = None
    metadata: dict[str, Any]


def create_app(
    engine: Engine,
    settings: Settings | None = None,
    ldap_authenticator: LdapAuthenticator | None = None,
    translator: LibreTranslateClient | None = None,
    es_client: ElasticsearchSearchClient | None = None,
    qdrant_client: QdrantSearchClient | None = None,
) -> FastAPI:
    """Create the API app with Phase 02 auth routes."""
    app = FastAPI(title="Neverland API")
    app.state.engine = engine
    app.state.settings = settings or Settings()
    app.state.ldap_authenticator = ldap_authenticator
    app.state.translator = translator
    app.state.es_client = es_client
    app.state.qdrant_client = qdrant_client

    @contextmanager
    def repository_context() -> Iterator[AuthRepository]:
        with app.state.engine.begin() as connection:
            yield AuthRepository(connection)

    def jwt_service() -> JwtService:
        return JwtService(secret=app.state.settings.jwt_secret)

    def current_user(request: Request) -> TokenPayload:
        authorization = request.headers.get("authorization")
        if authorization is None or not authorization.startswith(AUTH_SCHEME):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.removeprefix(AUTH_SCHEME)
        return jwt_service().decode(token)

    @app.post("/auth/login", response_model=LoginResponse)
    def login(request: LoginRequest) -> LoginResponse:
        with repository_context() as repository:
            service = AuthService(
                repository=repository,
                jwt_service=jwt_service(),
                auth_provider=app.state.settings.auth_provider,
                ldap_authenticator=app.state.ldap_authenticator,
            )
            return service.authenticate(request.email, request.password)

    @app.post("/auth/logout")
    def logout(_: Annotated[TokenPayload, Depends(current_user)]) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/auth/me", response_model=UserResponse)
    def me(user: Annotated[TokenPayload, Depends(current_user)]) -> UserResponse:
        return UserResponse.from_token(user)

    @app.get("/admin/health")
    def admin_health(user: Annotated[TokenPayload, Depends(current_user)]) -> dict[str, str]:
        require_admin(user)
        return {"status": "ok"}

    @app.post("/admin/ingestion/{source_id}/sync-now")
    def sync_now(
        source_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)

        with app.state.engine.begin() as connection:
            source_row = (
                connection.execute(
                    sa.text("SELECT * FROM ingestion_sources WHERE id = :id"),
                    {"id": source_id.hex},
                )
                .mappings()
                .first()
            )
            if source_row is None:
                raise HTTPException(status_code=404, detail="Source not found")

            source_path = source_row.get("path")
            if source_path is None:
                raise HTTPException(status_code=400, detail="Source has no path configured")

            folder = Path(source_path)
            if not folder.exists():
                raise HTTPException(status_code=400, detail="Source path does not exist")

            doc_repo = DocumentRepository(connection)
            translator = app.state.translator or LibreTranslateClient(
                base_url=app.state.settings.libretranslate_url
            )
            es_client = app.state.es_client or ElasticsearchSearchClient(
                hosts=[app.state.settings.elastic_url]
            )
            qdrant_client = app.state.qdrant_client or QdrantSearchClient(
                url=app.state.settings.qdrant_url
            )

            worker = PipelineWorker(
                document_repository=doc_repo,
                extractor_registry=ExtractorRegistry(),
                translator=translator,
                encoder=MockEncoder(),
                es_client=es_client,
                qdrant_client=qdrant_client,
            )

            results: dict[str, int] = {"indexed": 0, "skipped": 0, "failed": 0}
            for file_path in folder.rglob("*"):
                if not file_path.is_file():
                    continue

                mime_type, _ = mimetypes.guess_type(str(file_path))
                if mime_type is None:
                    mime_type = "application/octet-stream"

                sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
                doc = doc_repo.create(
                    source_id=source_id,
                    external_id=f"file:{file_path}",
                    source="folder",
                    mime_type=mime_type,
                    path=str(file_path),
                    title=file_path.name,
                    sha256=sha256,
                )
                if doc is None:
                    results["skipped"] += 1
                    continue

                try:
                    worker.process_document(doc.id)
                    results["indexed"] += 1
                except Exception:
                    results["failed"] += 1

            return results

    @app.post("/search", response_model=SearchResponse)
    def search(
        request: SearchRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> SearchResponse:
        group_ids = [str(g) for g in user.groups]
        if not group_ids:
            return SearchResponse(results=[], total=0)

        es_client = app.state.es_client or ElasticsearchSearchClient(
            hosts=[app.state.settings.elastic_url]
        )
        qdrant_client = app.state.qdrant_client or QdrantSearchClient(
            url=app.state.settings.qdrant_url
        )
        encoder = MockEncoder()

        bm25_results = es_client.search(request.query, group_ids=group_ids, size=50)
        query_vector = encoder.encode(request.query)
        vector_results = qdrant_client.search(vector=query_vector, group_ids=group_ids, limit=50)

        # TODO: read weights from system_config in Phase 04
        merged = merge_results(
            bm25_results=bm25_results,
            vector_results=vector_results,
            vector_weight=0.7,
            bm25_weight=0.3,
        )

        start = (request.page - 1) * request.page_size
        end = start + request.page_size
        page = merged[start:end]

        return SearchResponse(
            results=[
                SearchResultItem(
                    doc_id=r.doc_id,
                    score=r.score,
                    title=r.title,
                    chunk_text=r.chunk_text,
                )
                for r in page
            ],
            total=len(merged),
        )

    @app.get("/preview/{doc_id}", response_model=PreviewResponse)
    def preview(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> PreviewResponse:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            doc_repo = DocumentRepository(connection)
            doc = doc_repo.get_by_id(doc_id)
            if doc is None:
                raise HTTPException(status_code=404, detail="Document not found")

            return PreviewResponse(
                doc_id=str(doc.id),
                title=doc.title,
                mime_type=doc.mime_type,
                translation_quality=doc.translation_quality,
                metadata=doc.metadata,
            )

    @app.get("/download/{doc_id}")
    def download(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> StreamingResponse:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            doc_repo = DocumentRepository(connection)
            doc = doc_repo.get_by_id(doc_id)
            if doc is None or doc.path is None:
                raise HTTPException(status_code=404, detail="Document not found")

        files_root = app.state.settings.files_root.resolve()
        target = Path(doc.path).resolve()
        if not target.is_relative_to(files_root):
            raise HTTPException(status_code=400, detail="Invalid file path")

        def file_iterator() -> Iterator[bytes]:
            with target.open("rb") as f:
                while chunk := f.read(8192):
                    yield chunk

        return StreamingResponse(
            file_iterator(),
            media_type=doc.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
        )

    # Admin endpoints

    @app.get("/admin/users")
    def admin_list_users(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT id, email, display_name, auth_source, is_admin, created_at
                    FROM users ORDER BY created_at DESC
                    """
                )
            ).mappings()
            return [
                {
                    "id": str(to_uuid(row["id"])),
                    "email": row["email"],
                    "display_name": row["display_name"],
                    "auth_source": row["auth_source"],
                    "is_admin": row["is_admin"],
                    "created_at": _fmt_dt(row["created_at"]),
                }
                for row in rows
            ]

    @app.post("/admin/users", status_code=201)
    def admin_create_user(
        request: dict[str, Any],
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            identity = auth_repo.create_local_user(
                email=request["email"],
                password_hash=hash_password(request["password"]),
                display_name=request.get("display_name"),
                is_admin=request.get("is_admin", False),
                group_names=request.get("group_names", []),
            )
            return {
                "id": str(identity.id),
                "email": identity.email,
                "display_name": identity.display_name,
                "is_admin": identity.is_admin,
            }

    @app.delete("/admin/users/{user_id}", status_code=204)
    def admin_delete_user(
        user_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> None:
        require_admin(user)
        with app.state.engine.begin() as connection:
            result = connection.execute(
                sa.text("DELETE FROM users WHERE id = :id"),
                {"id": user_id.hex},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="User not found")

    @app.get("/admin/groups")
    def admin_list_groups(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text("SELECT id, name FROM groups ORDER BY name")
            ).mappings()
            return [{"id": str(to_uuid(row["id"])), "name": row["name"]} for row in rows]

    @app.post("/admin/groups", status_code=201)
    def admin_create_group(
        request: dict[str, Any],
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            group_id = auth_repo.ensure_group(request["name"])
            return {"id": str(group_id), "name": request["name"]}

    @app.get("/admin/sources")
    def admin_list_sources(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT id, name, type, path, source_language, enabled, created_at
                    FROM ingestion_sources ORDER BY created_at DESC
                    """
                )
            ).mappings()
            return [
                {
                    "id": str(to_uuid(row["id"])),
                    "name": row["name"],
                    "type": row["type"],
                    "path": row["path"],
                    "source_language": row["source_language"],
                    "enabled": row["enabled"],
                    "created_at": _fmt_dt(row["created_at"]),
                }
                for row in rows
            ]

    @app.post("/admin/sources", status_code=201)
    def admin_create_source(
        request: dict[str, Any],
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            source_id = uuid4()
            connection.execute(
                sa.text(
                    """
                    INSERT INTO ingestion_sources (id, name, type, path, source_language, enabled)
                    VALUES (:id, :name, :type, :path, :source_language, :enabled)
                    """
                ),
                {
                    "id": source_id.hex,
                    "name": request["name"],
                    "type": request.get("type", "folder"),
                    "path": request.get("path"),
                    "source_language": request.get("source_language", "en"),
                    "enabled": request.get("enabled", True),
                },
            )
            return {
                "id": str(source_id),
                "name": request["name"],
                "type": request.get("type", "folder"),
                "path": request.get("path"),
                "source_language": request.get("source_language", "en"),
                "enabled": request.get("enabled", True),
            }

    @app.post("/admin/sources/{source_id}/permissions", status_code=201)
    def admin_grant_permission(
        source_id: UUID,
        request: dict[str, Any],
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        group_id = UUID(request["group_id"])
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            auth_repo.grant_source_to_group(source_id, group_id)
            return {"source_id": str(source_id), "group_id": str(group_id)}

    @app.delete("/admin/sources/{source_id}/permissions/{group_id}", status_code=204)
    def admin_revoke_permission(
        source_id: UUID,
        group_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> None:
        require_admin(user)
        with app.state.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    DELETE FROM source_permissions
                    WHERE source_id = :source_id AND group_id = :group_id
                    """
                ),
                {"source_id": source_id.hex, "group_id": group_id.hex},
            )

    @app.get("/admin/config")
    def admin_list_config(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text("SELECT key, value, updated_at FROM system_config ORDER BY key")
            ).mappings()
            return [
                {
                    "key": row["key"],
                    "value": row["value"],
                    "updated_at": _fmt_dt(row["updated_at"]),
                }
                for row in rows
            ]

    @app.put("/admin/config/{key}")
    def admin_update_config(
        key: str,
        request: dict[str, Any],
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    UPDATE system_config
                    SET value = :value, updated_at = CURRENT_TIMESTAMP, updated_by = :user_id
                    WHERE key = :key
                    """
                ),
                {
                    "key": key,
                    "value": request["value"],
                    "user_id": user.sub.hex,
                },
            )
            row = (
                connection.execute(
                    sa.text("SELECT key, value, updated_at FROM system_config WHERE key = :key"),
                    {"key": key},
                )
                .mappings()
                .first()
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Config key not found")
            return {
                "key": row["key"],
                "value": row["value"],
                "updated_at": _fmt_dt(row["updated_at"]),
            }

    return app
