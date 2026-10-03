"""0015 vendor stock

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-03

Warehouses and inventory rows owned by a vendor.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor.profiles.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )
    op.create_index("ix_warehouses_vendor_id", "warehouses", ["vendor_id"], schema="marketplace")
    op.create_table(
        "inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor.profiles.id"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.products.id"), nullable=False),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.warehouses.id"), nullable=False),
        sa.Column("sku", sa.String(128), nullable=False),
        sa.Column("available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("warehouse_id", "product_id", "sku", name="uq_inventory_warehouse_product_sku"),
        schema="marketplace",
    )
    op.create_index("ix_inventory_vendor_id", "inventory", ["vendor_id"], schema="marketplace")
    op.create_index("ix_inventory_product_id", "inventory", ["product_id"], schema="marketplace")
    op.create_index("ix_inventory_warehouse_id", "inventory", ["warehouse_id"], schema="marketplace")


def downgrade() -> None:
    op.drop_index("ix_inventory_warehouse_id", table_name="inventory", schema="marketplace")
    op.drop_index("ix_inventory_product_id", table_name="inventory", schema="marketplace")
    op.drop_index("ix_inventory_vendor_id", table_name="inventory", schema="marketplace")
    op.drop_table("inventory", schema="marketplace")
    op.drop_index("ix_warehouses_vendor_id", table_name="warehouses", schema="marketplace")
    op.drop_table("warehouses", schema="marketplace")
