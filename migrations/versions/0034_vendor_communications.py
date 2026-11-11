"""0034 vendor communications

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-10

Vendor-scoped send metadata on communication usage logs, plus
template-request notes vendors can submit to platform admin.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "communication_usage_logs",
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="platform",
    )
    op.add_column(
        "communication_usage_logs",
        sa.Column("contact_name", sa.String(255), nullable=True),
        schema="platform",
    )
    op.add_column(
        "communication_usage_logs",
        sa.Column("read_count", sa.Integer(), nullable=False, server_default="0"),
        schema="platform",
    )
    op.add_column(
        "communication_usage_logs",
        sa.Column("replied_count", sa.Integer(), nullable=False, server_default="0"),
        schema="platform",
    )
    op.add_column(
        "communication_usage_logs",
        sa.Column("variables", postgresql.JSONB(), nullable=False, server_default="{}"),
        schema="platform",
    )
    op.create_index(
        "ix_communication_usage_logs_vendor_id",
        "communication_usage_logs",
        ["vendor_id"],
        schema="platform",
    )

    op.create_table(
        "communication_template_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("channel", sa.String(16), nullable=False, server_default="sms"),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="submitted"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )
    op.create_index(
        "ix_communication_template_requests_vendor_id",
        "communication_template_requests",
        ["vendor_id"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_communication_template_requests_vendor_id",
        table_name="communication_template_requests",
        schema="platform",
    )
    op.drop_table("communication_template_requests", schema="platform")
    op.drop_index(
        "ix_communication_usage_logs_vendor_id",
        table_name="communication_usage_logs",
        schema="platform",
    )
    op.drop_column("communication_usage_logs", "variables", schema="platform")
    op.drop_column("communication_usage_logs", "replied_count", schema="platform")
    op.drop_column("communication_usage_logs", "read_count", schema="platform")
    op.drop_column("communication_usage_logs", "contact_name", schema="platform")
    op.drop_column("communication_usage_logs", "vendor_id", schema="platform")
