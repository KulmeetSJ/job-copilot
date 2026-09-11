"""Schema migration for Phase 10A Object Storage and Artifact Management

Revision ID: 002_artifacts_storage
Revises: 001_initial_schema
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_artifacts_storage"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("artifact_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("application_id", sa.String(length=255), nullable=True),
        sa.Column("job_id", sa.String(length=255), nullable=True),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("storage_provider", sa.String(length=50), nullable=False, server_default="local"),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("artifact_id", name="uq_artifact_id"),
    )

    op.create_index("ix_artifacts_artifact_id", "artifacts", ["artifact_id"])
    op.create_index("ix_artifacts_application_id", "artifacts", ["application_id"])
    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])
    op.create_index("ix_artifacts_artifact_type", "artifacts", ["artifact_type"])
    op.create_index("ix_artifacts_storage_key", "artifacts", ["storage_key"])
    op.create_index("ix_artifacts_sha256", "artifacts", ["sha256"])
    op.create_index("ix_artifacts_status", "artifacts", ["status"])
    op.create_index("ix_artifacts_app_type", "artifacts", ["application_id", "artifact_type"])
    op.create_index("ix_artifacts_job_type", "artifacts", ["job_id", "artifact_type"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_job_type", table_name="artifacts")
    op.drop_index("ix_artifacts_app_type", table_name="artifacts")
    op.drop_index("ix_artifacts_status", table_name="artifacts")
    op.drop_index("ix_artifacts_sha256", table_name="artifacts")
    op.drop_index("ix_artifacts_storage_key", table_name="artifacts")
    op.drop_index("ix_artifacts_artifact_type", table_name="artifacts")
    op.drop_index("ix_artifacts_job_id", table_name="artifacts")
    op.drop_index("ix_artifacts_application_id", table_name="artifacts")
    op.drop_index("ix_artifacts_artifact_id", table_name="artifacts")
    op.drop_table("artifacts")
