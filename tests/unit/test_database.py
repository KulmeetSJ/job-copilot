"""Unit tests for database initialization and schema creation."""

from sqlalchemy import inspect
from sqlalchemy.orm import Session
from job_copilot.db.database import init_db
from job_copilot.models.base import Base


def test_database_tables_exist(db_session: Session):
    """Test that all expected tables are registered and created in the database schema."""
    engine = db_session.get_bind()
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    assert "jobs" in table_names
    assert "applications" in table_names


def test_init_db_runs_without_error():
    """Test that init_db function executes cleanly."""
    init_db()
