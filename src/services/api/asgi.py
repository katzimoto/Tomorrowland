"""ASGI entrypoint for container and production-style runtime."""

from __future__ import annotations

import sqlalchemy as sa

from services.api.main import create_app
from services.api.observability import (
    configure_api_logging,
    install_enhanced_request_observability,
)
from shared.config import get_settings

settings = get_settings()
configure_api_logging(settings.log_level)
engine = sa.create_engine(
    settings.postgres_url,
    pool_size=20,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
)
app = create_app(engine, settings)
install_enhanced_request_observability(app)
