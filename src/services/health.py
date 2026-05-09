from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict


class HealthResponse(TypedDict):
    """Shared health response shape for Phase 01 service skeletons."""

    status: Literal["ok"]
    service: str


def health(service: str) -> HealthResponse:
    """Return a minimal health payload for a service."""
    return {"status": "ok", "service": service}
