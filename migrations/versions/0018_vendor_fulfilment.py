"""0018 vendor fulfilment

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-03

Per-vendor fulfilment status, courier, and tracking for an order.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_fulfilments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.orders.id"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor.profiles.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="placed"),
        sa.Column("courier", sa.String(128), nullable=False, server_default=""),
        sa.Column("tracking_number", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("order_id", "vendor_id", name="uq_vendor_fulfilment_order_vendor"),
        schema="marketplace",
    )
    op.create_index(
        "ix_marketplace_vendor_fulfilments_order_id",
        "vendor_fulfilments",
        ["order_id"],
        schema="marketplace",
    )
    op.create_index(
        "ix_marketplace_vendor_fulfilments_vendor_id",
        "vendor_fulfilments",
        ["vendor_id"],
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_index("ix_marketplace_vendor_fulfilments_vendor_id", table_name="vendor_fulfilments", schema="marketplace")
    op.drop_index("ix_marketplace_vendor_fulfilments_order_id", table_name="vendor_fulfilments", schema="marketplace")
    op.drop_table("vendor_fulfilments", schema="marketplace")
