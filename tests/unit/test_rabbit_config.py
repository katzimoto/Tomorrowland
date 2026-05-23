from __future__ import annotations

from shared.config import Settings


def test_rabbitmq_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RABBITMQ_ENABLED", raising=False)
    s = Settings()
    assert s.rabbitmq_enabled is False


def test_rabbitmq_url_default(monkeypatch):
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    s = Settings()
    assert s.rabbitmq_url == "amqp://guest:guest@localhost:5672/"


def test_rabbitmq_enabled_via_env(monkeypatch):
    monkeypatch.setenv("RABBITMQ_ENABLED", "true")
    monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@rabbitmq:5672/")
    s = Settings()
    assert s.rabbitmq_enabled is True
    assert s.rabbitmq_url == "amqp://user:pass@rabbitmq:5672/"
