"""0033 communications hub

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-10

Platform Admin Communications Hub: message templates (SMS/WhatsApp/Email/In-App),
usage audit log, and consent/opt-out registry.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communication_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("plugin", sa.String(64), nullable=False, server_default="Sales"),
        sa.Column("message_type", sa.String(64), nullable=False, server_default="Marketing"),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("approval_status", sa.String(64), nullable=False, server_default="draft"),
        sa.Column("dlt_reference", sa.String(64), nullable=True),
        sa.Column("vendors_using", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_sent_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("variable_map", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_communication_templates_code"),
        schema="platform",
    )
    op.create_index(
        "ix_communication_templates_channel",
        "communication_templates",
        ["channel"],
        schema="platform",
    )
    op.create_index(
        "ix_communication_templates_approval_status",
        "communication_templates",
        ["approval_status"],
        schema="platform",
    )

    op.create_table(
        "communication_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vendor_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("template_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("template_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("audience", sa.String(255), nullable=False, server_default=""),
        sa.Column("sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(64), nullable=False, server_default="done"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )
    op.create_index(
        "ix_communication_usage_logs_occurred_at",
        "communication_usage_logs",
        ["occurred_at"],
        schema="platform",
    )

    op.create_table(
        "communication_optouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("contact_ref", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(128), nullable=False, server_default="user_request"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("channel", "contact_ref", name="uq_communication_optouts_channel_contact"),
        schema="platform",
    )
    op.create_index(
        "ix_communication_optouts_channel",
        "communication_optouts",
        ["channel"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index("ix_communication_optouts_channel", table_name="communication_optouts", schema="platform")
    op.drop_table("communication_optouts", schema="platform")
    op.drop_index(
        "ix_communication_usage_logs_occurred_at",
        table_name="communication_usage_logs",
        schema="platform",
    )
    op.drop_table("communication_usage_logs", schema="platform")
    op.drop_index(
        "ix_communication_templates_approval_status",
        table_name="communication_templates",
        schema="platform",
    )
    op.drop_index(
        "ix_communication_templates_channel",
        table_name="communication_templates",
        schema="platform",
    )
    op.drop_table("communication_templates", schema="platform")
