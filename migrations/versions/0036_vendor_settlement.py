"""0036 vendor settlement

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-10

Vendor Settlement portal: live earnings tracker, return alerts, today's
orders, settlement history, chat evidence, and IMPS bank account.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_settlement_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("order_ref", sa.String(32), nullable=False),
        sa.Column("order_time", sa.String(16), nullable=False, server_default=""),
        sa.Column("items", sa.String(512), nullable=False, server_default=""),
        sa.Column("gross", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(64), nullable=False, server_default="window_open"),
        sa.Column("window_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("settlement_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("return_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("in_tracker", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("in_today", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )

    op.create_table(
        "vendor_settlement_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("order_ref", sa.String(32), nullable=False),
        sa.Column("customer_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("complaint", sa.Text(), nullable=False, server_default=""),
        sa.Column("reason_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("refund_requested", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("amount_on_hold", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("order_items", sa.Text(), nullable=False, server_default=""),
        sa.Column("timeline", sa.Text(), nullable=False, server_default=""),
        sa.Column("deadline_seconds", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(64), nullable=False, server_default="open"),
        sa.Column("contest_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("chat", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        schema="platform",
    )

    op.create_table(
        "vendor_settlement_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("settle_date", sa.String(32), nullable=False),
        sa.Column("orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gross", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("deductions", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("refund_adj", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("utr", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )

    op.create_table(
        "vendor_settlement_bank",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("bank_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("account_mask", sa.String(64), nullable=False, server_default=""),
        sa.Column("ifsc", sa.String(32), nullable=False, server_default=""),
        sa.Column("branch", sa.String(128), nullable=False, server_default=""),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("vendor_settlement_bank", schema="platform")
    op.drop_table("vendor_settlement_history", schema="platform")
    op.drop_table("vendor_settlement_returns", schema="platform")
    op.drop_table("vendor_settlement_orders", schema="platform")
