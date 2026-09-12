"""Schema migration for Local Browser Agent and Device Pairing

Revision ID: 005_device_pairing_and_local_agent
Revises: 004_browser_sessions
Create Date: 2026-09-12 11:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005_device_pairing_and_local_agent"
down_revision: Union[str, None] = "004_browser_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add execution_mode and assigned_device_id columns to browser_tasks
    with op.batch_alter_table("browser_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("execution_mode", sa.String(length=32), nullable=False, server_default="LOCAL_INTERACTIVE")
        )
        batch_op.add_column(
            sa.Column("assigned_device_id", sa.String(length=64), nullable=True)
        )

    # 2. Create paired_devices table
    op.create_table(
        "paired_devices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("device_name", sa.String(length=128), nullable=False, server_default="Local Interactive Machine"),
        sa.Column("pairing_code", sa.String(length=16), nullable=True),
        sa.Column("pairing_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_token_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING_PAIRING"),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("agent_version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("device_id", name="uq_paired_device_id"),
    )

    op.create_index("ix_paired_devices_device_id", "paired_devices", ["device_id"])
    op.create_index("ix_paired_devices_pairing_code", "paired_devices", ["pairing_code"])
    op.create_index("ix_paired_devices_token_hash", "paired_devices", ["device_token_hash"])
    op.create_index("ix_paired_devices_status_seen", "paired_devices", ["status", "last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_paired_devices_status_seen", table_name="paired_devices")
    op.drop_index("ix_paired_devices_token_hash", table_name="paired_devices")
    op.drop_index("ix_paired_devices_pairing_code", table_name="paired_devices")
    op.drop_index("ix_paired_devices_device_id", table_name="paired_devices")
    op.drop_table("paired_devices")

    with op.batch_alter_table("browser_tasks") as batch_op:
        batch_op.drop_column("assigned_device_id")
        batch_op.drop_column("execution_mode")
