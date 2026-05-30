"""Model provider adapter interfaces and registry types."""

from services.intelligence.adapters.base import (
    BaseModelProviderAdapter,
    ProviderCapabilities,
    ProviderHealthResult,
)

__all__ = [
    "BaseModelProviderAdapter",
    "ProviderCapabilities",
    "ProviderHealthResult",
]
