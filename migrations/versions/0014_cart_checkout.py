"""0014 cart checkout

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-02

Wishlist, cart, orders, returns, and delivery addresses (J43, J44, J48–J52).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.tenants.id"), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("line1", sa.String(255), nullable=False),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("pincode", sa.String(16), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="tenant",
    )
    op.create_index("ix_addresses_tenant_id", "addresses", ["tenant_id"], schema="tenant")

    op.create_table(
        "wishlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.tenants.id"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.products.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "product_id", name="uq_wishlists_tenant_product"),
        schema="marketplace",
    )
    op.create_index("ix_wishlists_tenant_id", "wishlists", ["tenant_id"], schema="marketplace")
    op.create_index("ix_wishlists_product_id", "wishlists", ["product_id"], schema="marketplace")

    op.create_table(
        "carts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.tenants.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )
    op.create_index("ix_carts_tenant_id", "carts", ["tenant_id"], schema="marketplace")
    op.create_index(
        "uq_carts_one_open",
        "carts",
        ["tenant_id"],
        unique=True,
        schema="marketplace",
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "cart_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.carts.id"), nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.offerings.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("cart_id", "offering_id", name="uq_cart_lines_cart_offering"),
        schema="marketplace",
    )
    op.create_index("ix_cart_lines_cart_id", "cart_lines", ["cart_id"], schema="marketplace")
    op.create_index("ix_cart_lines_offering_id", "cart_lines", ["offering_id"], schema="marketplace")

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.tenants.id"), nullable=False),
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.carts.id"), nullable=False),
        sa.Column("address_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.addresses.id"), nullable=True),
        sa.Column("payment_method", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="placed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )
    op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"], schema="marketplace")
    op.create_index("ix_orders_cart_id", "orders", ["cart_id"], schema="marketplace")

    op.create_table(
        "order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.orders.id"), nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.offerings.id"), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("plan_name", sa.String(128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("fulfilment_type", sa.String(64), nullable=False),
        sa.Column("billing_period", sa.String(32), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        schema="marketplace",
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"], schema="marketplace")
    op.create_index("ix_order_lines_offering_id", "order_lines", ["offering_id"], schema="marketplace")

    op.create_table(
        "returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.orders.id"), nullable=False),
        sa.Column("line_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.order_lines.id"), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="requested"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )
    op.create_index("ix_returns_order_id", "returns", ["order_id"], schema="marketplace")
    op.create_index("ix_returns_line_id", "returns", ["line_id"], schema="marketplace")


def downgrade() -> None:
    op.drop_table("returns", schema="marketplace")
    op.drop_table("order_lines", schema="marketplace")
    op.drop_table("orders", schema="marketplace")
    op.drop_table("cart_lines", schema="marketplace")
    op.drop_table("carts", schema="marketplace")
    op.drop_table("wishlists", schema="marketplace")
    op.drop_table("addresses", schema="tenant")
