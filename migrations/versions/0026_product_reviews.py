"""0026 product reviews

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-17

marketplace.product_reviews — buyer product ratings for vendor portal
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("line_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.profiles.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["marketplace.products.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["marketplace.orders.id"]),
        sa.ForeignKeyConstraint(["line_id"], ["marketplace.order_lines.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("line_id", name="uq_product_reviews_line_id"),
        schema="marketplace",
    )
    op.create_index(
        "ix_marketplace_product_reviews_vendor_id",
        "product_reviews",
        ["vendor_id"],
        unique=False,
        schema="marketplace",
    )
    op.create_index(
        "ix_marketplace_product_reviews_product_id",
        "product_reviews",
        ["product_id"],
        unique=False,
        schema="marketplace",
    )
    op.create_index(
        "ix_marketplace_product_reviews_order_id",
        "product_reviews",
        ["order_id"],
        unique=False,
        schema="marketplace",
    )
    op.create_index(
        "ix_marketplace_product_reviews_tenant_id",
        "product_reviews",
        ["tenant_id"],
        unique=False,
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketplace_product_reviews_tenant_id",
        table_name="product_reviews",
        schema="marketplace",
    )
    op.drop_index(
        "ix_marketplace_product_reviews_order_id",
        table_name="product_reviews",
        schema="marketplace",
    )
    op.drop_index(
        "ix_marketplace_product_reviews_product_id",
        table_name="product_reviews",
        schema="marketplace",
    )
    op.drop_index(
        "ix_marketplace_product_reviews_vendor_id",
        table_name="product_reviews",
        schema="marketplace",
    )
    op.drop_table("product_reviews", schema="marketplace")
