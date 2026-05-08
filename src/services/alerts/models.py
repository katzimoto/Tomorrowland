"""Alert subscription and notification models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubscriptionCreateRequest(BaseModel):
    """Request body for creating an alert subscription."""

    name: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    enabled: bool = True


class SubscriptionUpdateRequest(BaseModel):
    """Request body for updating an alert subscription."""

    name: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    enabled: bool | None = None
