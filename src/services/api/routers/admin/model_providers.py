"""Admin API for model provider registry management.

This router exposes CRUD for model providers, model descriptors, and model
task defaults.  Credentials are never returned in plaintext — only a boolean
``credential_set`` flag is exposed.  URL / SSRF validation is applied based on
the provider's declared locality.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from typing import Annotated, Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from services.api._helpers import _audit_log
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.intelligence.credential_store import CredentialStore
from services.intelligence.model_provider_models import (
    ModelDescriptor,
    ModelDescriptorCreate,
    ModelDescriptorUpdate,
    ModelProvider,
    ModelProviderCreate,
    ModelProviderResponse,
    ModelProviderUpdate,
    ModelTaskDefault,
    ModelTaskDefaultCreate,
    ModelTaskDefaultUpdate,
)
from services.intelligence.model_provider_repository import ModelProviderRepository
from services.intelligence.ssrf_validation import validate_locality, validate_provider_url
from services.permissions.enforcer import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cs(
    connection: sa.engine.Connection,
    request: Request,
) -> CredentialStore:
    """Shortcut: credential store from a *connection* + *request*."""
    key = request.app.state.settings.credential_store_key or "dev-only"
    return CredentialStore(connection, key)


def _provider_to_response(
    provider: ModelProvider,
    cs: CredentialStore,
) -> ModelProviderResponse:
    """Convert a ``ModelProvider`` to the API response shape."""
    credential_set = False
    if provider.api_key_ref:
        credential_set = cs.has_credential(provider.api_key_ref)
    return ModelProviderResponse(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        description=provider.description,
        base_url=provider.base_url,
        api_key_ref=None,
        credential_set=credential_set,
        locality=provider.locality,
        enabled=provider.enabled,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def _handle_credential(
    cs: CredentialStore,
    credential_value: str | None,
    existing_ref: str | None,
) -> str | None:
    """Handle credential_value from create/update input.

    * ``None`` — leave existing_ref unchanged (no-op).
    * ``""`` (empty string) — clear the stored credential, return *None*.
    * Non-empty — encrypt and store, return the *key_name*.
    """
    if credential_value is None:
        return existing_ref
    if credential_value == "":
        if existing_ref:
            cs.delete_credential(existing_ref)
        return None
    key_name = f"prov/{uuid4().hex}"
    cs.set_credential(key_name, credential_value)
    return key_name


# ---------------------------------------------------------------------------
# Model Providers CRUD
# ---------------------------------------------------------------------------


@router.get("/admin/model-providers")
def admin_list_providers(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    enabled_only: bool = Query(False, description="Only return enabled providers"),
) -> list[ModelProviderResponse]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        cs = _cs(connection, request)
        providers = repo.list_providers(enabled_only=enabled_only)
        return [_provider_to_response(p, cs) for p in providers]


@router.get("/admin/model-providers/{provider_id}")
def admin_get_provider(
    provider_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelProviderResponse:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        cs = _cs(connection, request)
        provider = repo.get_provider(provider_id)
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        return _provider_to_response(provider, cs)


@router.post("/admin/model-providers", status_code=201)
def admin_create_provider(
    body: ModelProviderCreate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelProviderResponse:
    require_admin(user)
    locality = validate_locality(body.locality)
    base_url = validate_provider_url(body.base_url, locality)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        cs = _cs(connection, request)

        # Check unique name
        if repo.get_provider_by_name(body.name):
            raise HTTPException(
                status_code=409,
                detail=f"Provider name '{body.name}' already exists",
            )

        api_key_ref = _handle_credential(cs, body.credential_value, None)
        create_kwargs = body.model_dump()
        create_kwargs.pop("credential_value", None)
        create_kwargs.update(
            {
                "base_url": base_url,
                "locality": locality,
                "api_key_ref": api_key_ref,
            }
        )
        provider = repo.create_provider(ModelProviderCreate(**create_kwargs))
        _audit_log(connection, user.sub, "create", "model_provider", str(provider.id))
        return _provider_to_response(provider, cs)


@router.put("/admin/model-providers/{provider_id}")
def admin_update_provider(
    provider_id: UUID,
    body: ModelProviderUpdate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelProviderResponse:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        cs = _cs(connection, request)

        existing = repo.get_provider(provider_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Provider not found")

        # Validate locality if provided.
        locality = existing.locality
        if body.locality is not None:
            locality = validate_locality(body.locality)

        # Validate URL if provided (or keep existing).
        resolved_url = existing.base_url if body.base_url is None else body.base_url
        base_url = validate_provider_url(resolved_url, locality)

        # Handle credential.
        api_key_ref = _handle_credential(cs, body.credential_value, existing.api_key_ref)

        update_data = body.model_copy(
            update={
                "base_url": base_url,
                "locality": locality,
                "api_key_ref": api_key_ref,
            }
        )
        # Remove API-only fields before passing to the repository.
        # These are not persisted to the model_providers table.
        update_kwargs = update_data.model_dump(exclude_unset=True)
        update_kwargs.pop("credential_value", None)
        repo_update = ModelProviderUpdate(**update_kwargs)
        updated = repo.update_provider(provider_id, repo_update)
        if updated is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        _audit_log(connection, user.sub, "update", "model_provider", str(provider_id))
        return _provider_to_response(updated, cs)


@router.delete("/admin/model-providers/{provider_id}")
def admin_delete_provider(
    provider_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        existing = repo.get_provider(provider_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Provider not found")

        # Clean up stored credential.
        if existing.api_key_ref:
            cs = _cs(connection, request)
            cs.delete_credential(existing.api_key_ref)

        repo.delete_provider(provider_id)
        _audit_log(connection, user.sub, "delete", "model_provider", str(provider_id))
        return {"deleted": True, "id": str(provider_id)}


# ---------------------------------------------------------------------------
# Provider health / test
# ---------------------------------------------------------------------------


class _SetTaskDefaultBody(BaseModel):
    """Body for setting a task default — ``task_type`` is taken from the URL path."""

    provider_id: UUID
    model_descriptor_id: UUID | None = None
    parameters: dict[str, Any] | None = None


class _ProviderTestResult(BaseModel):
    healthy: bool
    latency_ms: float | None = None
    error: str | None = None
    provider_type: str


@router.post("/admin/model-providers/{provider_id}/test")
def admin_test_provider(
    provider_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> _ProviderTestResult:
    """Test connectivity to a provider by hitting its health endpoint.

    For Ollama: ``GET /api/tags``
    For OpenAI-compatible: ``GET /v1/models``
    """
    require_admin(user)

    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        provider = repo.get_provider(provider_id)
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")

        base_url = provider.base_url
        if not base_url:
            return _ProviderTestResult(
                healthy=False,
                error="No base URL configured",
                provider_type=provider.provider_type,
            )

        # Resolve credential if needed.
        api_key: str | None = None
        if provider.api_key_ref:
            cs = _cs(connection, request)
            api_key = cs.get_credential(provider.api_key_ref)

    try:
        if provider.provider_type == "ollama":
            url = base_url.rstrip("/") + "/api/tags"
        else:
            url = base_url.rstrip("/") + "/v1/models"

        req = urllib.request.Request(url)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")

        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=10) as resp:
            latency = (time.perf_counter() - start) * 1000
            status = resp.status
            if status < 500:
                return _ProviderTestResult(
                    healthy=True,
                    latency_ms=round(latency, 1),
                    provider_type=provider.provider_type,
                )
            return _ProviderTestResult(
                healthy=False,
                latency_ms=round(latency, 1),
                error=f"HTTP {status}",
                provider_type=provider.provider_type,
            )
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return _ProviderTestResult(
            healthy=False,
            latency_ms=round(elapsed, 1),
            error=f"HTTP {exc.code}: {exc.reason}",
            provider_type=provider.provider_type,
        )
    except urllib.error.URLError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return _ProviderTestResult(
            healthy=False,
            latency_ms=round(elapsed, 1),
            error=f"Connection failed: {exc.reason}",
            provider_type=provider.provider_type,
        )
    except TimeoutError:
        elapsed = (time.perf_counter() - start) * 1000
        return _ProviderTestResult(
            healthy=False,
            latency_ms=round(elapsed, 1),
            error="Connection timed out",
            provider_type=provider.provider_type,
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return _ProviderTestResult(
            healthy=False,
            latency_ms=round(elapsed, 1),
            error=str(exc),
            provider_type=provider.provider_type,
        )


# ---------------------------------------------------------------------------
# Model Descriptors CRUD
# ---------------------------------------------------------------------------


@router.get("/admin/model-providers/{provider_id}/descriptors")
def admin_list_descriptors(
    provider_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    enabled_only: bool = Query(False),
) -> list[ModelDescriptor]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        if repo.get_provider(provider_id) is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        return repo.list_descriptors(provider_id=provider_id, enabled_only=enabled_only)


@router.get("/admin/model-descriptors/{descriptor_id}")
def admin_get_descriptor(
    descriptor_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelDescriptor:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        desc = repo.get_descriptor(descriptor_id)
        if desc is None:
            raise HTTPException(status_code=404, detail="Descriptor not found")
        return desc


class _CreateDescriptorBody(BaseModel):
    """Body for creating a descriptor — ``provider_id`` is taken from the URL path."""

    model_name: str
    display_name: str | None = None
    description: str | None = None
    capabilities: dict[str, Any] | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    enabled: bool = True


@router.post("/admin/model-providers/{provider_id}/descriptors", status_code=201)
def admin_create_descriptor(
    provider_id: UUID,
    body: _CreateDescriptorBody,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelDescriptor:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        if repo.get_provider(provider_id) is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        create_data = ModelDescriptorCreate(
            provider_id=provider_id,
            model_name=body.model_name,
            display_name=body.display_name,
            description=body.description,
            capabilities=body.capabilities,
            context_window=body.context_window,
            max_output_tokens=body.max_output_tokens,
            enabled=body.enabled,
        )
        try:
            desc = repo.create_descriptor(create_data)
        except sa.exc.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Descriptor for model '{body.model_name}' already exists under this provider"
                ),
            ) from None
        _audit_log(connection, user.sub, "create", "model_descriptor", str(desc.id))
        return desc


@router.put("/admin/model-descriptors/{descriptor_id}")
def admin_update_descriptor(
    descriptor_id: UUID,
    body: ModelDescriptorUpdate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelDescriptor:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        updated = repo.update_descriptor(descriptor_id, body)
        if updated is None:
            raise HTTPException(status_code=404, detail="Descriptor not found")
        _audit_log(connection, user.sub, "update", "model_descriptor", str(descriptor_id))
        return updated


@router.delete("/admin/model-descriptors/{descriptor_id}")
def admin_delete_descriptor(
    descriptor_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        if repo.get_descriptor(descriptor_id) is None:
            raise HTTPException(status_code=404, detail="Descriptor not found")
        repo.delete_descriptor(descriptor_id)
        _audit_log(connection, user.sub, "delete", "model_descriptor", str(descriptor_id))
        return {"deleted": True, "id": str(descriptor_id)}


# ---------------------------------------------------------------------------
# Task Defaults
# ---------------------------------------------------------------------------


@router.get("/admin/model-task-defaults")
def admin_list_task_defaults(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[ModelTaskDefault]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        return repo.list_task_defaults()


@router.get("/admin/model-task-defaults/{task_type}")
def admin_get_task_default(
    task_type: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelTaskDefault:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        td = repo.get_task_default(task_type)
        if td is None:
            raise HTTPException(status_code=404, detail="Task default not found")
        return td


@router.put("/admin/model-task-defaults/{task_type}")
def admin_set_task_default(
    task_type: str,
    body: _SetTaskDefaultBody,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelTaskDefault:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        # Verify provider exists.
        if repo.get_provider(body.provider_id) is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        # Verify descriptor exists if specified.
        if (
            body.model_descriptor_id is not None
            and repo.get_descriptor(body.model_descriptor_id) is None
        ):
            raise HTTPException(status_code=404, detail="Model descriptor not found")
        create_data = ModelTaskDefaultCreate(
            task_type=task_type,
            provider_id=body.provider_id,
            model_descriptor_id=body.model_descriptor_id,
            parameters=body.parameters,
        )
        td = repo.set_task_default(create_data)
        _audit_log(connection, user.sub, "set", "model_task_default", task_type)
        return td


@router.patch("/admin/model-task-defaults/{task_type}")
def admin_update_task_default(
    task_type: str,
    body: ModelTaskDefaultUpdate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ModelTaskDefault:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        # Verify descriptor exists if specified.
        if (
            body.model_descriptor_id is not None
            and repo.get_descriptor(body.model_descriptor_id) is None
        ):
            raise HTTPException(status_code=404, detail="Model descriptor not found")
        updated = repo.update_task_default(task_type, body)
        if updated is None:
            raise HTTPException(status_code=404, detail="Task default not found")
        _audit_log(connection, user.sub, "update", "model_task_default", task_type)
        return updated


@router.delete("/admin/model-task-defaults/{task_type}")
def admin_delete_task_default(
    task_type: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        if not repo.delete_task_default(task_type):
            raise HTTPException(status_code=404, detail="Task default not found")
        _audit_log(connection, user.sub, "delete", "model_task_default", task_type)
        return {"deleted": True, "task_type": task_type}


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------


@router.post("/admin/model-providers/reload")
def admin_reload_providers(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, bool]:
    """Reload provider registry and task-default resolver from the database.

    Call this after creating, updating, or deleting providers via the API so
    in-process resolver state reflects the latest DB configuration without
    requiring a service restart.
    """
    require_admin(user)
    request.app.state.provider_registry.reload()
    resolver = getattr(request.app.state, "task_default_resolver", None)
    if resolver is not None:
        resolver.reload()
    return {"reloaded": True}


# ---------------------------------------------------------------------------
# Discover models
# ---------------------------------------------------------------------------


@router.post("/admin/model-providers/{provider_id}/discover")
def admin_discover_models(
    provider_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    """Discover available models from a provider by querying its API.

    For Ollama: ``GET /api/tags`` returns list of models.
    For OpenAI-compatible: ``GET /v1/models`` returns list of models.
    """
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = ModelProviderRepository(connection)
        provider = repo.get_provider(provider_id)
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")

        base_url = provider.base_url
        if not base_url:
            raise HTTPException(status_code=422, detail="Provider has no base URL configured")

        api_key: str | None = None
        if provider.api_key_ref:
            cs = _cs(connection, request)
            api_key = cs.get_credential(provider.api_key_ref)

    try:
        if provider.provider_type == "ollama":
            url = base_url.rstrip("/") + "/api/tags"
        else:
            url = base_url.rstrip("/") + "/v1/models"

        req = urllib.request.Request(url)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")

        with urllib.request.urlopen(req, timeout=15) as resp:
            import json

            raw = resp.read(1_048_576)  # limit response to 1 MB
            data = json.loads(raw.decode())

        if provider.provider_type == "ollama":
            models = data.get("models", [])
            return [
                {
                    "model_name": m["name"],
                    "modified_at": m.get("modified_at"),
                    "size": m.get("size"),
                }
                for m in models
            ]
        else:
            models = data.get("data", [])
            return [
                {
                    "model_name": m["id"],
                    "owned_by": m.get("owned_by"),
                }
                for m in models
            ]
    except urllib.error.HTTPError as exc:
        body = exc.read()[:500].decode(errors="replace")
        raise HTTPException(
            status_code=502,
            detail=f"Provider returned HTTP {exc.code}: {body}",
        ) from exc
    except urllib.error.URLError:
        raise HTTPException(status_code=502, detail="Could not connect to provider") from None
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Provider did not respond within 15s") from None
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Discovery failed: {exc}") from exc
