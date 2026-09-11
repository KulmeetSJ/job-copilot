"""Initial schema migration for Phase 9.5 Persistent Storage

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-09-11 11:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. jobs table
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=255), nullable=True, unique=True),
        sa.Column("canonical_url", sa.String(length=1024), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("remote_status", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
        sa.Column("employment_type", sa.String(length=50), nullable=False, server_default="FULL_TIME"),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True, server_default="manual"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("normalized_content_hash", sa.String(length=64), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=50), nullable=False, server_default="DISCOVERED"),
        sa.Column("duplicate_of", sa.String(length=255), nullable=True),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("preferred_qualifications", sa.JSON(), nullable=False),
        sa.Column("technologies", sa.JSON(), nullable=False),
        sa.Column("years_experience", sa.Float(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. job_provenance table
    op.create_table(
        "job_provenance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id_ref", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id_ref", "source_id", "source_url", name="uq_job_source_provenance"),
    )

    # 3. recommendations table
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id_ref", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("job_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("recommendation", sa.String(length=50), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("priority_band", sa.String(length=50), nullable=False),
        sa.Column("recommended_strategy", sa.String(length=100), nullable=False),
        sa.Column("category_scores", sa.JSON(), nullable=False),
        sa.Column("explanation_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 4. applications table
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("application_id", sa.String(length=255), nullable=True, unique=True),
        sa.Column("job_id_str", sa.String(length=255), nullable=True, unique=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column("canonical_job_url", sa.String(length=1024), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="DISCOVERED"),
        sa.Column("current_status_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_used", sa.String(length=50), nullable=False, server_default="general_swe"),
        sa.Column("resume_strategy", sa.String(length=100), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("recommendation", sa.String(length=50), nullable=True),
        sa.Column("package_path", sa.String(length=1024), nullable=True),
        sa.Column("browser_session_id", sa.String(length=255), nullable=True),
        sa.Column("user_notes", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recommended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 5. application_events table
    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("application_id_ref", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", sa.String(length=255), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="MANUAL"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_application_event_id"),
        sa.UniqueConstraint("application_id", "event_type", "timestamp", name="uq_app_event_tuple"),
    )

    # 6. application_snapshots table
    op.create_table(
        "application_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("application_id_ref", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("application_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resume_strategy", sa.String(length=100), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("recommendation", sa.String(length=50), nullable=False),
        sa.Column("technical_match", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("responsibility_match", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("seniority_match", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("professional_evidence_match", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("domain_match", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("preference_match", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("credential_match", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("job_source", sa.String(length=100), nullable=False, server_default="unknown"),
        sa.Column("resume_pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("cover_letter_path", sa.String(length=1024), nullable=True),
        sa.Column("applied_via", sa.String(length=100), nullable=True),
    )

    # 7. copilot_queue table
    op.create_table(
        "copilot_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("priority_band", sa.String(length=50), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("queue_status", sa.String(length=50), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("category_scores", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("user_notes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 8. source_health table
    op.create_table(
        "source_health",
        sa.Column("source_id", sa.String(length=100), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False, server_default="ACTIVE"),
        sa.Column("discovery_mode", sa.String(length=50), nullable=False, server_default="PUBLIC"),
        sa.Column("requires_login", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("source_health")
    op.drop_table("copilot_queue")
    op.drop_table("application_snapshots")
    op.drop_table("application_events")
    op.drop_table("applications")
    op.drop_table("recommendations")
    op.drop_table("job_provenance")
    op.drop_table("jobs")
