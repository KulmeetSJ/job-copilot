"""Database engine, session management, and initialization."""

from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from job_copilot.config import settings
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Configure connect args for SQLite if used
connect_args = {}
if settings.is_sqlite:
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    echo=settings.debug and False,  # set to False to avoid verbose log spam, can be toggled
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """Provide a transactional database session scope."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables and create required parent directories."""
    from job_copilot.db.base import Base

    if settings.is_sqlite:
        # Extract file path from sqlite:///...
        sqlite_path_str = settings.database_url.replace("sqlite:///", "")
        if sqlite_path_str and sqlite_path_str != ":memory:":
            db_file = Path(sqlite_path_str)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensuring database directory exists: {db_file.parent}")

    logger.info(f"Creating database tables on: {settings.database_url}")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully.")
