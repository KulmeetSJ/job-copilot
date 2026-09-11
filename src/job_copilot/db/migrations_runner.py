"""Alembic migration runner helpers for programmatic database schema management."""

from pathlib import Path
from typing import Optional
from alembic import command
from alembic.config import Config

from job_copilot.config import settings
from job_copilot.db.database import normalize_database_url, sanitize_database_url
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def get_alembic_config(db_url: Optional[str] = None) -> Config:
    """Construct an Alembic Config object pointing to the project alembic.ini."""
    ini_path = Path.cwd() / "alembic.ini"
    if not ini_path.exists():
        # Fallback to repo root if invoked from a subdirectory
        ini_path = Path(__file__).resolve().parent.parent.parent.parent / "alembic.ini"

    cfg = Config(str(ini_path))
    target_url = normalize_database_url(db_url or settings.database_url)
    cfg.set_main_option("sqlalchemy.url", target_url)
    return cfg


def run_migrations(db_url: Optional[str] = None) -> None:
    """Run all pending Alembic migrations up to head."""
    cfg = get_alembic_config(db_url=db_url)
    target_url = db_url or settings.database_url
    logger.info(f"Applying database migrations to: {sanitize_database_url(target_url)}")
    command.upgrade(cfg, "head")
    logger.info("Database migrations applied successfully.")


def downgrade_migrations(target_rev: str = "base", db_url: Optional[str] = None) -> None:
    """Downgrade migrations to a specified revision or base."""
    cfg = get_alembic_config(db_url=db_url)
    command.downgrade(cfg, target_rev)


def stamp_head(db_url: Optional[str] = None) -> None:
    """Stamp the current database version as head without executing migration scripts."""
    cfg = get_alembic_config(db_url=db_url)
    command.stamp(cfg, "head")
