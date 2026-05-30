"""Pydantic models for the model provider registry."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ModelProvider(BaseModel):
    """A registered model provider (e.g. Ollama, OpenAI, Anthropic)."""

    id: UUID
    name: str
    provider_type: str
    description: str | None = None
    base_url: str | None = None
    api_key_ref: str | None = Field(
        default=None, description="Reference to a credential, not a raw value"
    )
    locality: str = "local"  # local | self_hosted | external
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class ModelProviderCreate(BaseModel):
    """Input model for creating a new model provider."""

    name: str
    provider_type: str
    description: str | None = None
    base_url: str | None = None
    api_key_ref: str | None = None
    credential_value: str | None = Field(
        default=None,
        description=("Plaintext credential to encrypt and store. Never returned in responses."),
    )
    locality: str = "local"
    enabled: bool = True


class ModelProviderUpdate(BaseModel):
    """Input model for updating an existing model provider."""

    name: str | None = None
    provider_type: str | None = None
    description: str | None = None
    base_url: str | None = None
    api_key_ref: str | None = None
    credential_value: str | None = Field(
        default=None,
        description=(
            "Plaintext credential to encrypt and store. "
            'Pass ``None`` to leave unchanged; pass ``""`` to clear.'
        ),
    )
    locality: str | None = None
    enabled: bool | None = None


class ModelProviderResponse(BaseModel):
    """API response for a model provider — never contains plaintext credentials."""

    id: UUID
    name: str
    provider_type: str
    description: str | None = None
    base_url: str | None = None
    api_key_ref: str | None = None
    credential_set: bool = False
    locality: str = "local"
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class ModelDescriptor(BaseModel):
    """A specific model available from a provider."""

    id: UUID
    provider_id: UUID
    model_name: str
    display_name: str | None = None
    description: str | None = None
    capabilities: dict[str, Any] | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class ModelDescriptorCreate(BaseModel):
    """Input model for registering a new model descriptor."""

    provider_id: UUID
    model_name: str
    display_name: str | None = None
    description: str | None = None
    capabilities: dict[str, Any] | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    enabled: bool = True


class ModelDescriptorUpdate(BaseModel):
    """Input model for updating a model descriptor."""

    display_name: str | None = None
    description: str | None = None
    capabilities: dict[str, Any] | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    enabled: bool | None = None


class ModelTaskDefault(BaseModel):
    """Default provider/descriptor assignment for a task type."""

    id: UUID
    task_type: str
    provider_id: UUID
    model_descriptor_id: UUID | None = None
    parameters: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ModelTaskDefaultCreate(BaseModel):
    """Input model for setting a task default."""

    task_type: str
    provider_id: UUID
    model_descriptor_id: UUID | None = None
    parameters: dict[str, Any] | None = None


class ModelTaskDefaultUpdate(BaseModel):
    """Input model for updating a task default."""

    provider_id: UUID | None = None
    model_descriptor_id: UUID | None = None
    parameters: dict[str, Any] | None = None
