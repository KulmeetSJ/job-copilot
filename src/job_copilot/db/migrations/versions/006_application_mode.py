"""Schema migration for Application Mode (MANUAL, ASSISTED, AUTO_APPLY).

Revision ID: 006_application_mode
Revises: 005_device_pairing_and_local_agent
Create Date: 2026-09-18 00:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006_application_mode"
down_revision: Union[str, None] = "005_device_pairing_and_local_agent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add mode column to applications table
    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(
            sa.Column("mode", sa.String(length=32), nullable=False, server_default="ASSISTED")
        )

    # 2. Add application_mode column to browser_tasks table
    with op.batch_alter_table("browser_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("application_mode", sa.String(length=32), nullable=False, server_default="ASSISTED")
        )

    # 3. Add mode column to copilot_queue table
    with op.batch_alter_table("copilot_queue") as batch_op:
        batch_op.add_column(
            sa.Column("mode", sa.String(length=32), nullable=False, server_default="ASSISTED")
        )


def downgrade() -> None:
    with op.batch_alter_table("copilot_queue") as batch_op:
        batch_op.drop_column("mode")

    with op.batch_alter_table("browser_tasks") as batch_op:
        batch_op.drop_column("application_mode")

    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("mode")
