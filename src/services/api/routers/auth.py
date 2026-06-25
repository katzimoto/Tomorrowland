from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from services.api.main import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, current_user
from services.auth.jwt import JwtService
from services.auth.models import (
    LoginRequest,
    LoginResponse,
    SignUpRequest,
    TokenPayload,
    UserResponse,
)
from services.auth.repository import AuthRepository
from services.auth.service import AuthService

router = APIRouter(tags=["auth"])

# Cookie lifetime mirrors the JwtService access-token TTL (8 hours).
_COOKIE_MAX_AGE = 8 * 60 * 60


@contextmanager
def _repository_context(request: Request) -> Iterator[AuthRepository]:
    with request.app.state.engine.begin() as connection:
        yield AuthRepository(connection)


def _jwt_service(request: Request) -> JwtService:
    return JwtService(secret=request.app.state.settings.jwt_secret)


def _set_auth_cookies(response: Response, token: str, *, secure: bool) -> None:
    """Issue the HttpOnly auth cookie and its readable double-submit CSRF cookie."""
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        secrets.token_urlsafe(32),
        max_age=_COOKIE_MAX_AGE,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
    )


def _clear_auth_cookies(response: Response, *, secure: bool) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/", samesite="lax", secure=secure)
    response.delete_cookie(CSRF_COOKIE_NAME, path="/", samesite="lax", secure=secure)


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    with _repository_context(request) as repository:
        service = AuthService(
            repository=repository,
            jwt_service=_jwt_service(request),
            auth_provider=request.app.state.settings.auth_provider,
            ldap_authenticator=request.app.state.ldap_authenticator,
            metrics=request.app.state.metrics,
        )
        result = service.authenticate(body.email, body.password)
    _set_auth_cookies(
        response, result.access_token, secure=request.app.state.settings.auth_cookie_secure
    )
    return result


@router.post("/auth/signup", response_model=LoginResponse)
def signup(body: SignUpRequest, request: Request, response: Response) -> LoginResponse:
    with _repository_context(request) as repository:
        service = AuthService(
            repository=repository,
            jwt_service=_jwt_service(request),
            auth_provider=request.app.state.settings.auth_provider,
            ldap_authenticator=request.app.state.ldap_authenticator,
            metrics=request.app.state.metrics,
        )
        result = service.register(body.email, body.password, body.display_name)
    _set_auth_cookies(
        response, result.access_token, secure=request.app.state.settings.auth_cookie_secure
    )
    return result


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    _: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, bool]:
    _clear_auth_cookies(response, secure=request.app.state.settings.auth_cookie_secure)
    return {"ok": True}


@router.get("/auth/me", response_model=UserResponse)
def me(user: Annotated[TokenPayload, Depends(current_user)]) -> UserResponse:
    return UserResponse.from_token(user)
