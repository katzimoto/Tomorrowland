from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared.db import metadata

config = context.config

# Only override sqlalchemy.url from the environment when invoked via the Alembic
# CLI (e.g. `alembic upgrade head` in the Compose migrate service).  Python
# callers such as the test-fixture conftest.py set sqlalchemy.url directly on
# the Config object before calling command.upgrade(), and cmd_opts is None in
# that path, so we leave their URL untouched.
if config.cmd_opts is not None and (postgres_url := os.getenv("POSTGRES_URL")):
    config.set_main_option("sqlalchemy.url", postgres_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = metadata


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with an Engine connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
