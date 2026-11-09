"""0030 vendor growth plugins

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-22

Vendor-side import of the Sales & Growth standard plugins: per-vendor
installations with module toggles, plus Sales Pipeline deals/follow-ups.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_growth_plugins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plugin_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("modules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("connection", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("consents", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.profiles.id"]),
        sa.ForeignKeyConstraint(["plugin_key"], ["marketplace.growth_plugins.key"]),
        sa.UniqueConstraint("vendor_id", "plugin_key", name="uq_vendor_growth_plugins_vendor_key"),
        schema="marketplace",
    )
    op.create_index("ix_vendor_growth_plugins_vendor_id", "vendor_growth_plugins", ["vendor_id"], schema="marketplace")
    op.create_table(
        "sales_deals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("stage", sa.String(64), nullable=False, server_default="new-lead"),
        sa.Column("value_inr", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.profiles.id"]),
        schema="marketplace",
    )
    op.create_index("ix_sales_deals_vendor_id", "sales_deals", ["vendor_id"], schema="marketplace")
    op.create_table(
        "sales_followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.profiles.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["marketplace.sales_deals.id"]),
        schema="marketplace",
    )
    op.create_index("ix_sales_followups_vendor_id", "sales_followups", ["vendor_id"], schema="marketplace")


def downgrade() -> None:
    op.drop_table("sales_followups", schema="marketplace")
    op.drop_table("sales_deals", schema="marketplace")
    op.drop_table("vendor_growth_plugins", schema="marketplace")
