"""Schema migration for Phase 10B Browser Execution Tasks

Revision ID: 003_browser_tasks
Revises: 002_artifacts_storage
Create Date: 2026-09-12 00:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003_browser_tasks"
down_revision: Union[str, None] = "002_artifacts_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "browser_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("application_id", sa.String(length=255), nullable=True),
        sa.Column("job_id", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="manual"),
        sa.Column("target_url", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="QUEUED"),
        sa.Column("pause_reason", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("confirmation_token", sa.String(length=255), nullable=True),
        sa.Column("confirmation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_package_json", sa.JSON(), nullable=False),
        sa.Column("audit_events", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", name="uq_browser_task_id"),
    )

    op.create_index("ix_browser_tasks_task_id", "browser_tasks", ["task_id"])
    op.create_index("ix_browser_tasks_application_id", "browser_tasks", ["application_id"])
    op.create_index("ix_browser_tasks_job_id", "browser_tasks", ["job_id"])
    op.create_index("ix_browser_tasks_source", "browser_tasks", ["source"])
    op.create_index("ix_browser_tasks_status", "browser_tasks", ["status"])
    op.create_index("ix_browser_tasks_status_created", "browser_tasks", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_browser_tasks_status_created", table_name="browser_tasks")
    op.drop_index("ix_browser_tasks_status", table_name="browser_tasks")
    op.drop_index("ix_browser_tasks_source", table_name="browser_tasks")
    op.drop_index("ix_browser_tasks_job_id", table_name="browser_tasks")
    op.drop_index("ix_browser_tasks_application_id", table_name="browser_tasks")
    op.drop_index("ix_browser_tasks_task_id", table_name="browser_tasks")
    op.drop_table("browser_tasks")
