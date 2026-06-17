"""Runtime model-configuration overrides for local translation bundles.

The high-quality translation provider and the QE scorer load **local model
bundles** (file paths to CTranslate2 / QE artifacts) rather than calling a
provider endpoint, so they do not fit the model-provider registry. Their paths
default to environment values on ``Settings`` but can be overridden at runtime by
admins via ``Admin → Configuration`` (``system_config`` keys under the ``model.``
prefix).

Endpoint-backed models (embedding, reranker, chat/utility generation) are
configured through the model-provider registry / ``TaskDefaultResolver`` instead
— not here.

An override only applies when an admin sets a **non-empty** value; the registered
defaults are empty-string sentinels, so environment-based deployments keep using
their ``.env`` values until an explicit override is stored. These are consumed by
the enrich/slow workers at startup (no request hot path).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Final

from shared.config import Settings
from shared.config_cache import get_cached_config

# system_config key -> Settings field it overrides. All values are strings.
MODEL_CONFIG_OVERRIDES: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "model.translation_qe_model_path": "translation_qe_model_path",
        "model.translation_high_bundle_path": "translation_high_provider_bundle_path",
    }
)


def apply_model_config_overrides(settings: Settings, connection: Any) -> Settings:
    """Return *settings* with model fields overridden by admin ``system_config``.

    Empty/unset config values are ignored, so the environment default is kept.
    When no override is present the original *settings* instance is returned
    unchanged (no copy), keeping the common path allocation-free.
    """
    updates: dict[str, Any] = {}
    for key, field in MODEL_CONFIG_OVERRIDES.items():
        value = get_cached_config(connection, key)
        if value:  # non-empty string => explicit admin override
            updates[field] = value
    if not updates:
        return settings
    return settings.model_copy(update=updates)
