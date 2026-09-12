"""Schema migration for Phase 10C Authenticated Browser Sessions

Revision ID: 004_browser_sessions
Revises: 003_browser_tasks
Create Date: 2026-09-12 01:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004_browser_sessions"
down_revision: Union[str, None] = "003_browser_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NOT_CONFIGURED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("session_id", name="uq_browser_session_id"),
    )

    op.create_index("ix_browser_sessions_session_id", "browser_sessions", ["session_id"])
    op.create_index("ix_browser_sessions_source", "browser_sessions", ["source"])
    op.create_index("ix_browser_sessions_status", "browser_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_browser_sessions_status", table_name="browser_sessions")
    op.drop_index("ix_browser_sessions_source", table_name="browser_sessions")
    op.drop_index("ix_browser_sessions_session_id", table_name="browser_sessions")
    op.drop_table("browser_sessions")
