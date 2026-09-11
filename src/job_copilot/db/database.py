"""Database engine, session management, connection health, and initialization."""

from pathlib import Path
import re
from typing import Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from job_copilot.config import settings
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def sanitize_database_url(url: str) -> str:
    """Mask credentials in database URL for safe logging."""
    if not url:
        return ""
    # Matches patterns like postgresql://user:password@host:port/dbname
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def normalize_database_url(url: str) -> str:
    """
    Normalize database URL to ensure SQLAlchemy dialect compatibility.
    Handles Render's default postgres:// scheme and standard postgresql:// schemes by
    routing them to psycopg driver (postgresql+psycopg://).
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def create_db_engine(db_url: Optional[str] = None) -> Engine:
    """Create a SQLAlchemy Engine with connection pool parameters appropriate for the dialect."""
    raw_url = db_url or settings.database_url
    url = normalize_database_url(raw_url)
    is_sqlite = url.startswith("sqlite")

    connect_args = {}
    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }

    if is_sqlite:
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args
    else:
        # PostgreSQL connection pool configuration
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20
        engine_kwargs["pool_recycle"] = 300
        engine_kwargs["pool_timeout"] = 30

    return create_engine(url, **engine_kwargs)


# Global default engine and session factory
engine = create_db_engine()
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


def check_db_connection(custom_engine: Optional[Engine] = None) -> bool:
    """Safely check if the database is reachable without exposing credentials."""
    eng = custom_engine or engine
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning(f"Database health check failed: {sanitize_database_url(str(e))}")
        return False


def init_db(custom_engine: Optional[Engine] = None) -> None:
    """Initialize database tables and create required parent directories."""
    from job_copilot.db.base import Base

    target_engine = custom_engine or engine
    db_url = str(target_engine.url)

    if db_url.startswith("sqlite"):
        sqlite_path_str = db_url.replace("sqlite:///", "")
        if sqlite_path_str and sqlite_path_str != ":memory:":
            db_file = Path(sqlite_path_str)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensuring database directory exists: {db_file.parent}")

    logger.info(f"Creating database tables on: {sanitize_database_url(db_url)}")
    Base.metadata.create_all(bind=target_engine)
    logger.info("Database tables initialized successfully.")
