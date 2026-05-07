from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import Engine

from services.auth.jwt import JwtService
from services.auth.ldap import LdapAuthenticator
from services.auth.models import LoginRequest, LoginResponse, TokenPayload, UserResponse
from services.auth.repository import AuthRepository
from services.auth.service import AuthService
from services.permissions.enforcer import require_admin
from shared.config import Settings

AUTH_SCHEME = "Bearer "


def create_app(
    engine: Engine,
    settings: Settings | None = None,
    ldap_authenticator: LdapAuthenticator | None = None,
) -> FastAPI:
    """Create the API app with Phase 02 auth routes."""
    app = FastAPI(title="Neverland API")
    app.state.engine = engine
    app.state.settings = settings or Settings()
    app.state.ldap_authenticator = ldap_authenticator

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

    return app
