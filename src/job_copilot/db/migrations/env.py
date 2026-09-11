"""Alembic environment configuration."""

from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from alembic import context

from job_copilot.config import settings
from job_copilot.db.base import Base
from job_copilot.db.database import normalize_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    """Retrieve database URL from config, environment, or settings."""
    cfg_url = config.get_main_option("sqlalchemy.url")
    if cfg_url and cfg_url != "%(sqlalchemy.url)s":
        return normalize_database_url(cfg_url)
    raw = os.environ.get("DATABASE_URL", settings.database_url)
    return normalize_database_url(raw)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
