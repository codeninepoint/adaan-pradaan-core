"""0012 marketplace plugins catalog install

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-02

Plugin core (J23–J28) and catalog/install (J29–J34, J38–J42).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS marketplace")

    op.create_table(
        "plugins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor.profiles.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_plugins_slug"),
        schema="marketplace",
    )
    op.create_index("ix_plugins_vendor_id", "plugins", ["vendor_id"], schema="marketplace")

    op.create_table(
        "plugin_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plugin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.plugins.id"), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("artifact_url", sa.String(1024), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=False, server_default=""),
        sa.Column("sbom_url", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_review"),
        sa.Column("scan_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plugin_id", "version", name="uq_plugin_versions_plugin_version"),
        schema="marketplace",
    )
    op.create_index("ix_plugin_versions_plugin_id", "plugin_versions", ["plugin_id"], schema="marketplace")

    op.create_table(
        "plugin_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.plugin_versions.id"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_id", "scope", name="uq_plugin_capabilities_version_scope"),
        schema="marketplace",
    )
    op.create_index("ix_plugin_capabilities_version_id", "plugin_capabilities", ["version_id"], schema="marketplace")

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor.profiles.id"), nullable=False),
        sa.Column("plugin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.plugins.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(128), nullable=False, server_default=""),
        sa.Column("fulfilment_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )
    op.create_index("ix_products_vendor_id", "products", ["vendor_id"], schema="marketplace")
    op.create_index("ix_products_plugin_id", "products", ["plugin_id"], schema="marketplace")

    op.create_table(
        "product_content",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.products.id"), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        schema="marketplace",
    )

    op.create_table(
        "offerings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.products.id"), nullable=False),
        sa.Column("plan_name", sa.String(128), nullable=False),
        sa.Column("billing_period", sa.String(32), nullable=False),
        sa.Column("price_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("included_transactions", sa.Integer(), nullable=True),
        sa.Column("overage_price_per_1k", sa.Numeric(12, 4), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )
    op.create_index("ix_offerings_product_id", "offerings", ["product_id"], schema="marketplace")

    op.create_table(
        "installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.offerings.id"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.projects.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="provisioning"),
        sa.Column("accepted_capabilities", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )
    op.create_index("ix_installations_offering_id", "installations", ["offering_id"], schema="marketplace")
    op.create_index("ix_installations_tenant_id", "installations", ["tenant_id"], schema="marketplace")

    op.create_table(
        "entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.installations.id"),
            nullable=False,
        ),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace.offerings.id"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.tenants.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )
    op.create_index("ix_entitlements_tenant_id", "entitlements", ["tenant_id"], schema="marketplace")

    op.create_table(
        "service_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.installations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("external_ref", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_table("service_instances", schema="marketplace")
    op.drop_table("entitlements", schema="marketplace")
    op.drop_table("installations", schema="marketplace")
    op.drop_table("offerings", schema="marketplace")
    op.drop_table("product_content", schema="marketplace")
    op.drop_table("products", schema="marketplace")
    op.drop_table("plugin_capabilities", schema="marketplace")
    op.drop_table("plugin_versions", schema="marketplace")
    op.drop_table("plugins", schema="marketplace")
    op.execute("DROP SCHEMA IF EXISTS marketplace")
