"""Unit tests for the canonical model-runtime boundary (#813)."""

from __future__ import annotations

from typing import Any

from services.intelligence.runtime import ModelRuntime
from services.intelligence.task_defaults import TaskResolution
from shared.config import Settings


class _StubResolver:
    """Minimal stand-in for TaskDefaultResolver."""

    def __init__(self, mapping: dict[str, TaskResolution], loaded: bool = True) -> None:
        self._mapping = mapping
        self.loaded = loaded
        self.reloaded = False

    def resolve(self, task: str) -> TaskResolution | None:
        return self._mapping.get(task)

    def reload(self) -> None:
        self.reloaded = True


class _EnvProvider:
    """Sentinel env/bundled fallback provider."""

    name = "env"


def _settings(**kw: Any) -> Settings:
    return Settings(**kw)


def _ollama_resolution(model: str = "qwen3:4b") -> TaskResolution:
    return TaskResolution(
        provider_name="local-ollama",
        provider_type="ollama",
        model_name=model,
        base_url="http://ollama:11434",
        locality="local",
    )


def _external_resolution() -> TaskResolution:
    return TaskResolution(
        provider_name="openai",
        provider_type="openai",
        model_name="gpt-4o",
        base_url="https://api.openai.com",
        api_key="sk-test",
        locality="external",
    )


def test_env_fallback_when_no_resolver() -> None:
    env = _EnvProvider()
    rt = ModelRuntime(_settings(), env, resolver=None)  # type: ignore[arg-type]
    assert rt.get_chat_provider("chat") is env
    assert rt.effective_source("chat") == "env_fallback"
    assert rt.effective_model_name("utility", "fallback-model") == "fallback-model"


def test_env_fallback_when_resolver_not_loaded() -> None:
    env = _EnvProvider()
    rt = ModelRuntime(_settings(), env, resolver=_StubResolver({}, loaded=False))  # type: ignore[arg-type]
    assert rt.get_chat_provider("chat") is env


def test_db_default_overrides_env() -> None:
    env = _EnvProvider()
    rt = ModelRuntime(
        _settings(),
        env,  # type: ignore[arg-type]
        resolver=_StubResolver({"chat": _ollama_resolution()}),  # type: ignore[arg-type]
    )
    provider = rt.get_chat_provider("chat")
    assert provider is not env
    assert getattr(provider, "model", None) == "qwen3:4b"
    assert rt.effective_source("chat") == "db_task_default"
    assert rt.effective_model_name("chat", "fallback") == "qwen3:4b"


def test_airgap_refuses_external_provider() -> None:
    env = _EnvProvider()
    rt = ModelRuntime(
        _settings(air_gapped=True),
        env,  # type: ignore[arg-type]
        resolver=_StubResolver({"chat": _external_resolution()}),  # type: ignore[arg-type]
    )
    # Air-gapped: external provider refused, falls back to local env provider.
    assert rt.get_chat_provider("chat") is env
    assert rt.effective_source("chat") == "env_fallback"
    assert rt.effective_model_name("chat", "local-model") == "local-model"


def test_external_provider_allowed_when_not_airgapped() -> None:
    env = _EnvProvider()
    rt = ModelRuntime(
        _settings(air_gapped=False),
        env,  # type: ignore[arg-type]
        resolver=_StubResolver({"chat": _external_resolution()}),  # type: ignore[arg-type]
    )
    assert rt.get_chat_provider("chat") is not env
    assert rt.effective_source("chat") == "db_task_default"


def test_unsupported_provider_type_falls_back() -> None:
    env = _EnvProvider()
    bad = TaskResolution(
        provider_name="x",
        provider_type="not-a-real-type",
        model_name="m",
        base_url="http://x",
        locality="local",
    )
    rt = ModelRuntime(
        _settings(),
        env,  # type: ignore[arg-type]
        resolver=_StubResolver({"chat": bad}),  # type: ignore[arg-type]
    )
    assert rt.get_chat_provider("chat") is env


def test_reload_delegates_to_resolver() -> None:
    env = _EnvProvider()
    stub = _StubResolver({})
    rt = ModelRuntime(_settings(), env, resolver=stub)  # type: ignore[arg-type]
    rt.reload()
    assert stub.reloaded is True
