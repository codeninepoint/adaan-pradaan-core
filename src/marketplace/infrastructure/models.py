from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models import Base, TimestampMixin


class PluginRow(Base, TimestampMixin):
    __tablename__ = "plugins"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_plugins_slug"),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(128))
    short_description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")


class PluginVersionRow(Base):
    __tablename__ = "plugin_versions"
    __table_args__ = (
        UniqueConstraint("plugin_id", "version", name="uq_plugin_versions_plugin_version"),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.plugins.id"), index=True
    )
    version: Mapped[str] = mapped_column(String(64))
    artifact_url: Mapped[str] = mapped_column(String(1024))
    changelog: Mapped[str] = mapped_column(Text, default="")
    sbom_url: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="pending_review")
    scan_status: Mapped[str] = mapped_column(String(32), default="pending")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PluginCapabilityRow(Base):
    __tablename__ = "plugin_capabilities"
    __table_args__ = (
        UniqueConstraint("version_id", "scope", name="uq_plugin_capabilities_version_scope"),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.plugin_versions.id"), index=True
    )
    scope: Mapped[str] = mapped_column(String(128))
    justification: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProductRow(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), index=True
    )
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.plugins.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    fulfilment_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProductContentRow(Base):
    __tablename__ = "product_content"
    __table_args__ = {"schema": "marketplace"}

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.products.id"), primary_key=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class OfferingRow(Base, TimestampMixin):
    __tablename__ = "offerings"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.products.id"), index=True
    )
    plan_name: Mapped[str] = mapped_column(String(128))
    billing_period: Mapped[str] = mapped_column(String(32))
    price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    included_transactions: Mapped[int | None] = mapped_column(nullable=True)
    overage_price_per_1k: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")


class InstallationRow(Base):
    __tablename__ = "installations"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offering_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.offerings.id"), index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenants.id"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.projects.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="provisioning")
    accepted_capabilities: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EntitlementRow(Base):
    __tablename__ = "entitlements"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.installations.id"), index=True
    )
    offering_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.offerings.id"), index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenants.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active")
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ServiceInstanceRow(Base):
    __tablename__ = "service_instances"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.installations.id"), unique=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active")
    external_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WishlistRow(Base):
    __tablename__ = "wishlists"
    __table_args__ = (
        UniqueConstraint("tenant_id", "product_id", name="uq_wishlists_tenant_product"),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenants.id"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.products.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CartRow(Base, TimestampMixin):
    __tablename__ = "carts"
    __table_args__ = (
        Index(
            "uq_carts_one_open",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenants.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="open")


class CartLineRow(Base):
    __tablename__ = "cart_lines"
    __table_args__ = (
        UniqueConstraint("cart_id", "offering_id", name="uq_cart_lines_cart_offering"),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.carts.id"), index=True
    )
    offering_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.offerings.id"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OrderRow(Base):
    __tablename__ = "orders"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenants.id"), index=True
    )
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.carts.id"), index=True
    )
    address_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.addresses.id"), nullable=True
    )
    payment_method: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="placed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VendorFulfilmentRow(Base):
    __tablename__ = "vendor_fulfilments"
    __table_args__ = (
        UniqueConstraint("order_id", "vendor_id", name="uq_vendor_fulfilment_order_vendor"),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.orders.id"), index=True
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="placed")
    courier: Mapped[str] = mapped_column(String(128), default="")
    tracking_number: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OrderLineRow(Base):
    __tablename__ = "order_lines"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.orders.id"), index=True
    )
    offering_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.offerings.id"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(255))
    plan_name: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer)
    fulfilment_type: Mapped[str] = mapped_column(String(64))
    billing_period: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(32), default="active")


class ReturnRow(Base):
    __tablename__ = "returns"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.orders.id"), index=True
    )
    line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.order_lines.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="requested")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WarehouseRow(Base):
    __tablename__ = "warehouses"
    __table_args__ = {"schema": "marketplace"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(255))
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InventoryRow(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "product_id", "sku", name="uq_inventory_warehouse_product_sku"),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.products.id"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace.warehouses.id"), index=True
    )
    sku: Mapped[str] = mapped_column(String(128))
    available: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)


class PayoutLedgerRow(Base):
    __tablename__ = "payouts"
    __table_args__ = (
        UniqueConstraint("vendor_id", "period", name="uq_payouts_vendor_period"),
        {"schema": "marketplace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), index=True
    )
    period: Mapped[str] = mapped_column(String(16))
    gross: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    net: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
