"""0022 vendor catalogue locations

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-17

nullable plugin_id, reorder_threshold, vendor cities/pincodes, product_service_cities
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "products",
        "plugin_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
        schema="marketplace",
    )

    op.add_column(
        "inventory",
        sa.Column("reorder_threshold", sa.Integer(), nullable=False, server_default="20"),
        schema="marketplace",
    )

    op.create_table(
        "vendor_service_cities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor.profiles.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("city_name", sa.String(128), nullable=False),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.warehouses.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("vendor_id", "city_name", name="uq_vendor_service_cities_vendor_city"),
        schema="marketplace",
    )

    op.create_table(
        "vendor_city_pincodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "city_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.vendor_service_cities.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("pincode", sa.String(16), nullable=False),
        sa.UniqueConstraint("city_id", "pincode", name="uq_vendor_city_pincodes_city_pin"),
        schema="marketplace",
    )

    op.create_table(
        "product_service_cities",
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "city_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.vendor_service_cities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_table("product_service_cities", schema="marketplace")
    op.drop_table("vendor_city_pincodes", schema="marketplace")
    op.drop_table("vendor_service_cities", schema="marketplace")
    op.drop_column("inventory", "reorder_threshold", schema="marketplace")
    op.alter_column(
        "products",
        "plugin_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        schema="marketplace",
    )
