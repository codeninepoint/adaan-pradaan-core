"""0037 customer order hub

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-10

Customer Order hub: active/past orders with return window, photo returns,
vendor chat evidence lock, and refund status — seeded for marketplace demos.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_hub_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("order_ref", sa.String(32), nullable=False),
        sa.Column("vendor_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("zone", sa.String(128), nullable=False, server_default=""),
        sa.Column("placed_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=False, server_default="return_window"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("window_seconds", sa.Integer(), nullable=True),
        sa.Column("window_closes_label", sa.String(32), nullable=False, server_default=""),
        sa.Column("timeline", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("bill_lines", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("chat", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )

    op.create_table(
        "customer_hub_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("order_ref", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("photo_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("amount_at_stake", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(64), nullable=False, server_default="submitted"),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("refund_method", sa.String(128), nullable=True),
        sa.Column("refund_reference", sa.String(64), nullable=True),
        sa.Column("expected_by", sa.String(64), nullable=True),
        sa.Column("vendor_name", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("customer_hub_returns", schema="platform")
    op.drop_table("customer_hub_orders", schema="platform")
