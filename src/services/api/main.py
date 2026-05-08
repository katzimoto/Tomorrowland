import hashlib
import mimetypes
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import Engine

from services.auth.jwt import JwtService
from services.auth.ldap import LdapAuthenticator
from services.auth.models import LoginRequest, LoginResponse, TokenPayload, UserResponse
from services.auth.repository import AuthRepository
from services.auth.service import AuthService
from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.permissions.enforcer import require_admin
from services.pipeline.worker import PipelineWorker
from services.search.elastic import ElasticsearchSearchClient
from services.search.encoder import MockEncoder
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.config import Settings

AUTH_SCHEME = "Bearer "


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

    return app
