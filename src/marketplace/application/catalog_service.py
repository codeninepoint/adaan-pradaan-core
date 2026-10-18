from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.domain.deny_messages import public_forbid_detail
from authz.domain.models import ApiSurface, AuthorizeCommand
from identity.domain.security import utcnow
from marketplace.application.access import audit, require_platform_operator, require_vendor_owner
from marketplace.application.provision import handle_provision
from marketplace.domain.fulfilment import FULFILMENT_TYPES, PROVISION_TYPES
from marketplace.infrastructure.models import (
    EntitlementRow,
    InstallationRow,
    OfferingRow,
    OrderLineRow,
    OrderRow,
    PluginCapabilityRow,
    PluginRow,
    PluginVersionRow,
    ProductContentRow,
    ProductReviewRow,
    ProductRow,
    InventoryRow,
    ProductServiceCityRow,
    VendorCityPincodeRow,
    VendorServiceCityRow,
    WarehouseRow,
)
from platform_ops.infrastructure.models import PlatformConfigRow
from sqlalchemy import or_
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shared.infrastructure.models import OutboxEventRow
from shared.settings import settings
from tenant.infrastructure.models import AddressRow, ProjectRow, TenantRow
from vendor.application.vendor_service import ALLOWED_CURRENCIES
from vendor.infrastructure.models import VendorProfileRow, VendorSettingsRow


@dataclass(frozen=True, slots=True)
class ProductCreated:
    product_id: UUID
    name: str
    status: str
    fulfilment_type: str


@dataclass(frozen=True, slots=True)
class VendorDirectoryItem:
    vendor_id: UUID
    legal_name: str
    status: str
    product_count: int
    active_installs: int
    plugin_count: int = 0
    warehouse_count: int = 0
    kyc_status: str = ""
    gmv_mtd: float = 0.0


@dataclass(frozen=True, slots=True)
class VendorStats:
    active: int
    pending_verification: int
    suspended: int
    total_plugins: int


@dataclass(frozen=True, slots=True)
class SuspendResult:
    vendor_id: UUID
    status: str
    offerings_unpublished: int


@dataclass(frozen=True, slots=True)
class OfferingListItem:
    offering_id: UUID
    product_id: UUID
    product_name: str
    plan_name: str
    status: str
    price_usd: float
    currency: str = "INR"
    price: float = 0.0


@dataclass(frozen=True, slots=True)
class ProductItem:
    product_id: UUID
    name: str
    fulfilment_type: str
    status: str
    category: str
    content: dict = field(default_factory=dict)
    pa_status: str = "not_submitted"
    pa_reject_reason: str = ""
    mrp_inr: float = 0.0
    image_count: int = 0
    cities: list[str] = field(default_factory=list)
    stock_status: str = "none"
    visibility: str = "hidden"
    brand: str = ""
    net_weight: str = ""
    sku: str = ""
    image_urls: list[str] = field(default_factory=list)
    currency: str = "INR"


@dataclass(frozen=True, slots=True)
class ServiceCityView:
    city_id: UUID
    city_name: str
    warehouse_id: UUID
    pincodes: list[str]
    currency: str | None = None
    resolved_currency: str = "INR"


@dataclass(frozen=True, slots=True)
class ProductCityAssignmentView:
    product_id: UUID
    product_name: str
    category: str
    cities: list[str]
    status: str


@dataclass(frozen=True, slots=True)
class CityInventoryView:
    inventory_id: UUID
    product_id: UUID
    product_name: str
    city_id: UUID
    city_name: str
    sku: str
    available: int
    reserved: int
    reorder_threshold: int
    status: str


@dataclass(frozen=True, slots=True)
class WarehouseView:
    warehouse_id: UUID
    name: str
    location: str
    capacity: int
    units_stored: int
    sku_count: int


@dataclass(frozen=True, slots=True)
class InventoryView:
    inventory_id: UUID
    product_id: UUID
    product_name: str
    warehouse_id: UUID
    warehouse_name: str
    sku: str
    available: int
    reserved: int
    reorder_threshold: int = 20
    city_name: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class OfferingCreated:
    offering_id: UUID
    product_id: UUID
    plan_name: str
    status: str


@dataclass(frozen=True, slots=True)
class CatalogCard:
    offering_id: UUID
    product_id: UUID
    product_name: str
    vendor_name: str
    vendor_id: UUID
    plan_name: str
    price_usd: float
    billing_period: str
    fulfilment_type: str
    category: str
    currency: str = "INR"
    price: float = 0.0
    avg_rating: float = 0.0
    review_count: int = 0
    in_stock: bool = True


@dataclass(frozen=True, slots=True)
class CatalogVendorFacet:
    vendor_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class CatalogResult:
    cards: list[CatalogCard]
    vendors: list[CatalogVendorFacet]


@dataclass(frozen=True, slots=True)
class PublicReview:
    rating: int
    comment: str
    customer_name: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PublicReviewList:
    reviews: list[PublicReview]
    avg_rating: float
    review_count: int


PHYSICAL_FULFILMENT = frozenset({"SHIP_PHYSICAL"})


@dataclass(frozen=True, slots=True)
class OfferingDetail:
    offering_id: UUID
    plan_name: str
    price_usd: float
    billing_period: str
    status: str
    currency: str = "INR"
    price: float = 0.0


@dataclass(frozen=True, slots=True)
class ProductDetail:
    product_id: UUID
    name: str
    description: str
    fulfilment_type: str
    vendor_name: str
    category: str
    content: dict
    capabilities: list[str]
    offerings: list[OfferingDetail]


@dataclass(frozen=True, slots=True)
class InstallResult:
    installation_id: UUID
    offering_id: UUID
    tenant_id: UUID
    status: str
    entitlement_id: UUID


@dataclass(frozen=True, slots=True)
class EntitlementItem:
    entitlement_id: UUID
    offering_name: str
    status: str
    installation_status: str
    granted_at: str


@dataclass(frozen=True, slots=True)
class VendorInstallItem:
    installation_id: UUID
    tenant_name: str
    product_name: str
    fulfilment_type: str
    status: str
    since: str


@dataclass(frozen=True, slots=True)
class AdminProductItem:
    product_id: UUID
    name: str
    vendor_id: UUID
    vendor_name: str
    category: str
    status: str
    pa_status: str
    pa_reject_reason: str
    fulfilment_type: str
    submitted_at: str


@dataclass(frozen=True, slots=True)
class AdminProductStats:
    pending_review: int
    live: int
    rejected: int
    not_submitted: int
    warehouse_locations: int = 0


@dataclass(frozen=True, slots=True)
class LocationSummaryItem:
    location: str
    warehouse_count: int
    vendor_count: int
    units_stored: int


class CatalogService:
    """J29–J34 and J38–J42: products, offerings, catalog, install, provision kickoff."""

    def __init__(self, session: AsyncSession, authorization: AuthorizationService) -> None:
        self._session = session
        self._authorization = authorization

    async def create_product(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        name: str,
        description: str,
        plugin_id: UUID | None,
        fulfilment_type: str,
        content: dict | None,
        category: str | None,
    ) -> ProductCreated:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        if vendor.status != "verified":
            raise ForbiddenError("vendor not verified")
        name = name.strip()
        if not name:
            raise ValidationError("name is required")
        if fulfilment_type not in FULFILMENT_TYPES:
            raise ValidationError("unknown fulfilment_type")
        if fulfilment_type in PROVISION_TYPES and plugin_id is None:
            raise ValidationError("plugin_id is required for provision fulfilment types")
        resolved_category = (category or "").strip()
        plugin: PluginRow | None = None
        if plugin_id is not None:
            plugin = await self._session.get(PluginRow, plugin_id)
            if plugin is None or plugin.vendor_id != vendor_id:
                raise NotFoundError("plugin not found")
            if not resolved_category:
                resolved_category = plugin.category.strip()
        elif not resolved_category:
            raise ValidationError("category is required when plugin_id is omitted")

        product = ProductRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            plugin_id=plugin_id,
            name=name,
            description=description.strip(),
            category=resolved_category,
            fulfilment_type=fulfilment_type,
            status="draft",
        )
        self._session.add(product)
        await self._session.flush()
        self._session.add(ProductContentRow(product_id=product.id, payload=content or {}))
        await audit(
            self._session,
            action="product.created",
            actor_user_id=caller_user_id,
            payload={
                "product_id": str(product.id),
                "plugin_id": str(plugin_id) if plugin_id else None,
                "fulfilment_type": fulfilment_type,
            },
        )
        await self._session.commit()
        return ProductCreated(
            product_id=product.id,
            name=name,
            status="draft",
            fulfilment_type=fulfilment_type,
        )

    async def list_products(self, *, vendor_id: UUID, caller_user_id: UUID) -> list[ProductItem]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(ProductRow)
                .where(ProductRow.vendor_id == vendor_id)
                .order_by(ProductRow.created_at.desc())
            )
        ).scalars().all()
        return await self._enrich_product_items(rows)

    async def list_service_cities(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[ServiceCityView]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        cities = (
            await self._session.execute(
                select(VendorServiceCityRow)
                .where(VendorServiceCityRow.vendor_id == vendor_id)
                .order_by(VendorServiceCityRow.city_name.asc())
            )
        ).scalars().all()
        if not cities:
            return []
        city_ids = [city.id for city in cities]
        pin_rows = (
            await self._session.execute(
                select(VendorCityPincodeRow)
                .where(VendorCityPincodeRow.city_id.in_(city_ids))
                .order_by(VendorCityPincodeRow.pincode.asc())
            )
        ).scalars().all()
        pins_by_city: dict[UUID, list[str]] = {}
        for pin in pin_rows:
            pins_by_city.setdefault(pin.city_id, []).append(pin.pincode)
        vendor_default = await self._vendor_default_currency(vendor_id)
        return [
            ServiceCityView(
                city_id=city.id,
                city_name=city.city_name,
                warehouse_id=city.warehouse_id,
                pincodes=pins_by_city.get(city.id, []),
                currency=city.currency,
                resolved_currency=city.currency or vendor_default,
            )
            for city in cities
        ]

    async def add_service_city(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        city_name: str,
        currency: str | None = None,
    ) -> ServiceCityView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        cleaned = city_name.strip()
        if not cleaned:
            raise ValidationError("city_name is required")
        city_currency = self._normalize_optional_currency(currency)
        existing = (
            await self._session.execute(
                select(VendorServiceCityRow.id).where(
                    VendorServiceCityRow.vendor_id == vendor_id,
                    VendorServiceCityRow.city_name == cleaned,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("service city already exists")
        warehouse = WarehouseRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            name=f"{cleaned} Hub",
            location=cleaned,
            capacity=10000,
        )
        self._session.add(warehouse)
        await self._session.flush()
        city = VendorServiceCityRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            city_name=cleaned,
            warehouse_id=warehouse.id,
            currency=city_currency,
        )
        self._session.add(city)
        await audit(
            self._session,
            action="vendor.service_city.added",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "city_name": cleaned, "currency": city_currency},
        )
        await self._session.commit()
        vendor_default = await self._vendor_default_currency(vendor_id)
        return ServiceCityView(
            city_id=city.id,
            city_name=city.city_name,
            warehouse_id=warehouse.id,
            pincodes=[],
            currency=city.currency,
            resolved_currency=city.currency or vendor_default,
        )

    async def update_service_city(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        city_id: UUID,
        currency: str | None = None,
    ) -> ServiceCityView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        city = await self._session.get(VendorServiceCityRow, city_id)
        if city is None or city.vendor_id != vendor_id:
            raise NotFoundError("service city not found")
        # PATCH endpoint is currency-only: null / "" / "DEFAULT" clears the city override.
        if currency is None or not currency.strip() or currency.strip().upper() == "DEFAULT":
            city.currency = None
        else:
            city.currency = self._normalize_currency(currency)
        await self._session.commit()
        pins = (
            await self._session.execute(
                select(VendorCityPincodeRow.pincode)
                .where(VendorCityPincodeRow.city_id == city_id)
                .order_by(VendorCityPincodeRow.pincode.asc())
            )
        ).scalars().all()
        vendor_default = await self._vendor_default_currency(vendor_id)
        return ServiceCityView(
            city_id=city.id,
            city_name=city.city_name,
            warehouse_id=city.warehouse_id,
            pincodes=list(pins),
            currency=city.currency,
            resolved_currency=city.currency or vendor_default,
        )

    async def delete_service_city(
        self, *, vendor_id: UUID, caller_user_id: UUID, city_id: UUID
    ) -> None:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        city = await self._session.get(VendorServiceCityRow, city_id)
        if city is None or city.vendor_id != vendor_id:
            raise NotFoundError("service city not found")
        stock_count = int(
            (
                await self._session.execute(
                    select(func.count(InventoryRow.id)).where(
                        InventoryRow.warehouse_id == city.warehouse_id
                    )
                )
            ).scalar_one()
        )
        if stock_count > 0:
            raise ConflictError("warehouse still has inventory")
        await self._session.execute(
            delete(ProductServiceCityRow).where(ProductServiceCityRow.city_id == city_id)
        )
        await self._session.execute(
            delete(VendorCityPincodeRow).where(VendorCityPincodeRow.city_id == city_id)
        )
        warehouse_id = city.warehouse_id
        await self._session.delete(city)
        warehouse = await self._session.get(WarehouseRow, warehouse_id)
        if warehouse is not None:
            await self._session.delete(warehouse)
        await audit(
            self._session,
            action="vendor.service_city.deleted",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "city_id": str(city_id)},
        )
        await self._session.commit()

    async def set_city_pincodes(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        city_id: UUID,
        pincodes: list[str],
    ) -> ServiceCityView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        city = await self._session.get(VendorServiceCityRow, city_id)
        if city is None or city.vendor_id != vendor_id:
            raise NotFoundError("service city not found")
        cleaned = self._validate_pincodes(pincodes)
        await self._session.execute(
            delete(VendorCityPincodeRow).where(VendorCityPincodeRow.city_id == city_id)
        )
        for pin in cleaned:
            self._session.add(VendorCityPincodeRow(id=uuid.uuid4(), city_id=city_id, pincode=pin))
        await self._session.commit()
        return ServiceCityView(
            city_id=city.id,
            city_name=city.city_name,
            warehouse_id=city.warehouse_id,
            pincodes=cleaned,
        )

    async def list_product_city_assignments(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[ProductCityAssignmentView]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        products = (
            await self._session.execute(
                select(ProductRow)
                .where(
                    ProductRow.vendor_id == vendor_id,
                    ProductRow.fulfilment_type == "SHIP_PHYSICAL",
                )
                .order_by(ProductRow.name.asc())
            )
        ).scalars().all()
        if not products:
            return []
        product_ids = [product.id for product in products]
        city_links = (
            await self._session.execute(
                select(ProductServiceCityRow, VendorServiceCityRow)
                .join(
                    VendorServiceCityRow,
                    VendorServiceCityRow.id == ProductServiceCityRow.city_id,
                )
                .where(ProductServiceCityRow.product_id.in_(product_ids))
            )
        ).all()
        cities_by_product: dict[UUID, list[str]] = {pid: [] for pid in product_ids}
        for link, city in city_links:
            cities_by_product.setdefault(link.product_id, []).append(city.city_name)
        return [
            ProductCityAssignmentView(
                product_id=product.id,
                product_name=product.name,
                category=product.category,
                cities=sorted(cities_by_product.get(product.id, [])),
                status="visible" if cities_by_product.get(product.id) else "hidden",
            )
            for product in products
        ]

    async def set_product_service_cities(
        self,
        *,
        product_id: UUID,
        caller_user_id: UUID,
        city_ids: list[UUID],
    ) -> ProductCityAssignmentView:
        product = await self._owned_product(product_id, caller_user_id)
        if product.fulfilment_type != "SHIP_PHYSICAL":
            raise ValidationError("service cities apply only to SHIP_PHYSICAL products")
        if not city_ids:
            raise ValidationError("at least one city is required")
        vendor_cities = (
            await self._session.execute(
                select(VendorServiceCityRow).where(
                    VendorServiceCityRow.vendor_id == product.vendor_id,
                    VendorServiceCityRow.id.in_(city_ids),
                )
            )
        ).scalars().all()
        if len(vendor_cities) != len(set(city_ids)):
            raise ValidationError("one or more cities do not belong to this vendor")
        await self._session.execute(
            delete(ProductServiceCityRow).where(ProductServiceCityRow.product_id == product_id)
        )
        for city_id in set(city_ids):
            self._session.add(
                ProductServiceCityRow(product_id=product_id, city_id=city_id)
            )
        await self._session.commit()
        city_names = sorted(city.city_name for city in vendor_cities)
        return ProductCityAssignmentView(
            product_id=product.id,
            product_name=product.name,
            category=product.category,
            cities=city_names,
            status="visible",
        )

    async def submit_product_listing(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        product_id: UUID | None,
        name: str,
        description: str,
        category: str,
        sku: str,
        mrp_inr: float,
        net_weight: str,
        brand: str,
        image_urls: list[str],
        authenticity_attested: bool,
        city_ids: list[UUID],
        fulfilment_type: str = "SHIP_PHYSICAL",
        currency: str | None = None,
    ) -> ProductItem:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        if vendor.status != "verified":
            raise ForbiddenError("vendor not verified")
        if fulfilment_type not in FULFILMENT_TYPES:
            raise ValidationError("unknown fulfilment_type")
        if not authenticity_attested:
            raise ValidationError("authenticity_attested must be true")
        cleaned_name = name.strip()
        cleaned_category = category.strip()
        cleaned_description = description.strip()
        cleaned_sku = sku.strip()
        cleaned_brand = brand.strip()
        cleaned_weight = net_weight.strip()
        if not cleaned_name or not cleaned_category or not cleaned_description or not cleaned_sku:
            raise ValidationError("name, category, description, and sku are required")
        if mrp_inr <= 0:
            raise ValidationError("mrp_inr must be greater than zero")
        listing_currency = (
            self._normalize_currency(currency)
            if currency
            else await self._vendor_default_currency(vendor_id)
        )
        validated_images = self._validate_image_urls(image_urls)
        if fulfilment_type == "SHIP_PHYSICAL":
            if not city_ids:
                raise ValidationError("at least one service city is required")
            vendor_cities = (
                await self._session.execute(
                    select(VendorServiceCityRow).where(
                        VendorServiceCityRow.vendor_id == vendor_id,
                        VendorServiceCityRow.id.in_(city_ids),
                    )
                )
            ).scalars().all()
            if len(vendor_cities) != len(set(city_ids)):
                raise ValidationError("one or more cities do not belong to this vendor")
        else:
            vendor_cities = []

        if product_id is not None:
            product = await self._owned_product(product_id, caller_user_id)
            if product.vendor_id != vendor_id:
                raise NotFoundError("product not found")
            if product.status == "archived":
                raise ConflictError("archived product cannot be edited")
        else:
            product = ProductRow(
                id=uuid.uuid4(),
                vendor_id=vendor_id,
                plugin_id=None,
                name=cleaned_name,
                description=cleaned_description,
                category=cleaned_category,
                fulfilment_type=fulfilment_type,
                status="draft",
            )
            self._session.add(product)
            await self._session.flush()
            self._session.add(ProductContentRow(product_id=product.id, payload={}))

        product.name = cleaned_name
        product.description = cleaned_description
        product.category = cleaned_category
        product.fulfilment_type = fulfilment_type
        product.status = "published"
        product.pa_status = "pending_review"
        product.pa_reject_reason = ""

        payload = {
            "sku": cleaned_sku,
            "brand": cleaned_brand,
            "net_weight": cleaned_weight,
            "mrp_inr": mrp_inr,
            "mrp_amount": mrp_inr,
            "currency": listing_currency,
            "image_urls": validated_images,
            "authenticity_attested": True,
        }
        stored = await self._session.get(ProductContentRow, product.id)
        if stored is None:
            stored = ProductContentRow(product_id=product.id, payload=payload)
            self._session.add(stored)
        else:
            stored.payload = payload

        if fulfilment_type == "SHIP_PHYSICAL":
            await self._session.execute(
                delete(ProductServiceCityRow).where(
                    ProductServiceCityRow.product_id == product.id
                )
            )
            for city_id in set(city_ids):
                self._session.add(
                    ProductServiceCityRow(product_id=product.id, city_id=city_id)
                )

        offering = (
            await self._session.execute(
                select(OfferingRow).where(
                    OfferingRow.product_id == product.id,
                    OfferingRow.plan_name == "Standard",
                )
            )
        ).scalar_one_or_none()
        if offering is None:
            offering = OfferingRow(
                id=uuid.uuid4(),
                product_id=product.id,
                plan_name="Standard",
                billing_period="one_time",
                price_usd=Decimal(str(mrp_inr)),
                currency=listing_currency,
                status="draft",
            )
            self._session.add(offering)
        else:
            offering.billing_period = "one_time"
            offering.price_usd = Decimal(str(mrp_inr))
            offering.currency = listing_currency
            offering.status = "draft"

        await audit(
            self._session,
            action="product.listing_submitted",
            actor_user_id=caller_user_id,
            payload={"product_id": str(product.id), "vendor_id": str(vendor_id)},
        )
        await self._session.commit()
        items = await self._enrich_product_items([product])
        return items[0]

    async def resubmit_product(
        self, *, product_id: UUID, caller_user_id: UUID
    ) -> ProductItem:
        product = await self._owned_product(product_id, caller_user_id)
        if product.pa_status != "rejected":
            raise ConflictError("only rejected products can be resubmitted")
        product.pa_status = "pending_review"
        product.pa_reject_reason = ""
        await audit(
            self._session,
            action="product.listing_resubmitted",
            actor_user_id=caller_user_id,
            payload={"product_id": str(product.id)},
        )
        await self._session.commit()
        items = await self._enrich_product_items([product])
        return items[0]

    async def list_warehouses(self, *, vendor_id: UUID, caller_user_id: UUID) -> list[WarehouseView]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(WarehouseRow)
                .where(WarehouseRow.vendor_id == vendor_id)
                .order_by(WarehouseRow.created_at.desc())
            )
        ).scalars().all()
        counts = dict(
            (
                await self._session.execute(
                    select(InventoryRow.warehouse_id, func.count())
                    .where(InventoryRow.vendor_id == vendor_id)
                    .group_by(InventoryRow.warehouse_id)
                )
            ).all()
        )
        units = dict(
            (
                await self._session.execute(
                    select(
                        InventoryRow.warehouse_id,
                        func.coalesce(func.sum(InventoryRow.available + InventoryRow.reserved), 0),
                    )
                    .where(InventoryRow.vendor_id == vendor_id)
                    .group_by(InventoryRow.warehouse_id)
                )
            ).all()
        )
        return [
            WarehouseView(
                warehouse_id=row.id,
                name=row.name,
                location=row.location,
                capacity=row.capacity,
                units_stored=int(units.get(row.id, 0)),
                sku_count=int(counts.get(row.id, 0)),
            )
            for row in rows
        ]

    async def create_warehouse(
        self, *, vendor_id: UUID, caller_user_id: UUID, name: str, location: str, capacity: int
    ) -> WarehouseView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        cleaned_name = name.strip()
        cleaned_location = location.strip()
        if not cleaned_name or not cleaned_location:
            raise ValidationError("name and location are required")
        if capacity < 0:
            raise ValidationError("capacity must be zero or more")
        row = WarehouseRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            name=cleaned_name,
            location=cleaned_location,
            capacity=capacity,
        )
        self._session.add(row)
        await self._session.commit()
        return WarehouseView(
            warehouse_id=row.id,
            name=row.name,
            location=row.location,
            capacity=capacity,
            units_stored=0,
            sku_count=0,
        )

    async def update_warehouse(
        self,
        *,
        vendor_id: UUID,
        warehouse_id: UUID,
        caller_user_id: UUID,
        name: str,
        location: str,
        capacity: int,
    ) -> WarehouseView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        cleaned_name = name.strip()
        cleaned_location = location.strip()
        if not cleaned_name or not cleaned_location:
            raise ValidationError("name and location are required")
        if capacity < 0:
            raise ValidationError("capacity must be zero or more")
        row = await self._session.get(WarehouseRow, warehouse_id)
        if row is None or row.vendor_id != vendor_id:
            raise NotFoundError("warehouse not found")
        row.name = cleaned_name
        row.location = cleaned_location
        row.capacity = capacity
        await self._session.commit()
        listed = await self.list_warehouses(vendor_id=vendor_id, caller_user_id=caller_user_id)
        updated = next((item for item in listed if item.warehouse_id == warehouse_id), None)
        if updated is None:
            raise NotFoundError("warehouse not found")
        return updated

    async def list_inventory(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        view: str | None = None,
    ) -> list[InventoryView] | list[CityInventoryView]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        if view == "by_city":
            rows = (
                await self._session.execute(
                    select(InventoryRow, ProductRow, VendorServiceCityRow)
                    .join(ProductRow, ProductRow.id == InventoryRow.product_id)
                    .join(
                        VendorServiceCityRow,
                        VendorServiceCityRow.warehouse_id == InventoryRow.warehouse_id,
                    )
                    .where(
                        InventoryRow.vendor_id == vendor_id,
                        VendorServiceCityRow.vendor_id == vendor_id,
                    )
                    .order_by(VendorServiceCityRow.city_name, ProductRow.name, InventoryRow.sku)
                )
            ).all()
            return [
                CityInventoryView(
                    inventory_id=stock.id,
                    product_id=product.id,
                    product_name=product.name,
                    city_id=city.id,
                    city_name=city.city_name,
                    sku=stock.sku,
                    available=stock.available,
                    reserved=stock.reserved,
                    reorder_threshold=stock.reorder_threshold,
                    status=self._inventory_status(stock.available, stock.reorder_threshold),
                )
                for stock, product, city in rows
            ]
        rows = (
            await self._session.execute(
                select(InventoryRow, ProductRow, WarehouseRow)
                .join(ProductRow, ProductRow.id == InventoryRow.product_id)
                .join(WarehouseRow, WarehouseRow.id == InventoryRow.warehouse_id)
                .where(InventoryRow.vendor_id == vendor_id)
                .order_by(ProductRow.name, InventoryRow.sku)
            )
        ).all()
        return [
            InventoryView(
                inventory_id=stock.id,
                product_id=product.id,
                product_name=product.name,
                warehouse_id=warehouse.id,
                warehouse_name=warehouse.name,
                sku=stock.sku,
                available=stock.available,
                reserved=stock.reserved,
                reorder_threshold=stock.reorder_threshold,
            )
            for stock, product, warehouse in rows
        ]

    async def add_inventory(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        product_id: UUID,
        warehouse_id: UUID,
        sku: str,
        available: int,
        reorder_threshold: int | None = None,
    ) -> InventoryView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        product = await self._session.get(ProductRow, product_id)
        if product is None or product.vendor_id != vendor_id:
            raise NotFoundError("product not found")
        warehouse = await self._session.get(WarehouseRow, warehouse_id)
        if warehouse is None or warehouse.vendor_id != vendor_id:
            raise NotFoundError("warehouse not found")
        cleaned_sku = sku.strip()
        if not cleaned_sku:
            raise ValidationError("sku is required")
        if available < 0:
            raise ValidationError("available cannot be negative")
        existing = (
            await self._session.execute(
                select(InventoryRow.id).where(
                    InventoryRow.warehouse_id == warehouse_id,
                    InventoryRow.product_id == product_id,
                    InventoryRow.sku == cleaned_sku,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("sku already recorded in this warehouse")
        threshold = 20 if reorder_threshold is None else reorder_threshold
        if threshold < 0:
            raise ValidationError("reorder_threshold must be zero or more")
        row = InventoryRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            sku=cleaned_sku,
            available=available,
            reserved=0,
            reorder_threshold=threshold,
        )
        self._session.add(row)
        await self._session.commit()
        return InventoryView(
            inventory_id=row.id,
            product_id=product.id,
            product_name=product.name,
            warehouse_id=warehouse.id,
            warehouse_name=warehouse.name,
            sku=row.sku,
            available=row.available,
            reserved=0,
            reorder_threshold=row.reorder_threshold,
        )

    async def adjust_inventory(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        inventory_id: UUID,
        available: int,
        reorder_threshold: int | None = None,
    ) -> InventoryView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        if available < 0:
            raise ValidationError("available cannot be negative")
        row = await self._session.get(InventoryRow, inventory_id)
        if row is None or row.vendor_id != vendor_id:
            raise NotFoundError("inventory not found")
        row.available = available
        if reorder_threshold is not None:
            if reorder_threshold < 0:
                raise ValidationError("reorder_threshold must be zero or more")
            row.reorder_threshold = reorder_threshold
        await self._session.commit()
        product = await self._session.get(ProductRow, row.product_id)
        warehouse = await self._session.get(WarehouseRow, row.warehouse_id)
        if product is None or warehouse is None:
            raise NotFoundError("inventory not found")
        return InventoryView(
            inventory_id=row.id,
            product_id=product.id,
            product_name=product.name,
            warehouse_id=warehouse.id,
            warehouse_name=warehouse.name,
            sku=row.sku,
            available=row.available,
            reserved=row.reserved,
            reorder_threshold=row.reorder_threshold,
        )

    async def list_offerings(self, *, vendor_id: UUID, caller_user_id: UUID) -> list[OfferingListItem]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(OfferingRow, ProductRow)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(ProductRow.vendor_id == vendor_id)
                .order_by(OfferingRow.created_at.desc())
            )
        ).all()
        return [
            OfferingListItem(
                offering_id=offering.id,
                product_id=product.id,
                product_name=product.name,
                plan_name=offering.plan_name,
                status=offering.status,
                price_usd=float(offering.price_usd),
                currency=getattr(offering, "currency", None) or "INR",
                price=float(offering.price_usd),
            )
            for offering, product in rows
        ]

    async def update_product(
        self,
        *,
        product_id: UUID,
        caller_user_id: UUID,
        name: str | None,
        description: str | None,
        category: str | None = None,
        content: dict | None = None,
    ) -> ProductItem:
        product = await self._owned_product(product_id, caller_user_id)
        if product.status == "archived":
            raise ConflictError("archived product cannot be edited")
        stored = await self._session.get(ProductContentRow, product.id)
        prior_listing = self._listing_snapshot(product, stored.payload if stored else {})
        if name is not None and name.strip():
            product.name = name.strip()
        if description is not None:
            product.description = description.strip()
        if category is not None:
            product.category = category.strip()
        if content is not None:
            if stored is None:
                stored = ProductContentRow(product_id=product.id, payload=content)
                self._session.add(stored)
            else:
                stored.payload = content
        if await self._product_content_review_required() and product.pa_status in (
            "live",
            "rejected",
        ):
            current_listing = self._listing_snapshot(product, stored.payload if stored else {})
            if current_listing != prior_listing:
                product.pa_status = "pending_review"
                product.pa_reject_reason = ""
                offerings = (
                    await self._session.execute(
                        select(OfferingRow).where(
                            OfferingRow.product_id == product.id,
                            OfferingRow.status == "published",
                        )
                    )
                ).scalars().all()
                for offering in offerings:
                    offering.status = "draft"
        await audit(
            self._session,
            action="product.updated",
            actor_user_id=caller_user_id,
            payload={"product_id": str(product.id)},
        )
        await self._session.commit()
        items = await self._enrich_product_items([product])
        return items[0]

    async def update_offering_price(
        self,
        *,
        offering_id: UUID,
        caller_user_id: UUID,
        price_usd: Decimal,
        currency: str | None = None,
    ) -> OfferingListItem:
        offering = await self._session.get(OfferingRow, offering_id)
        if offering is None:
            raise NotFoundError("offering not found")
        product = await self._owned_product(offering.product_id, caller_user_id)
        if product.status == "archived":
            raise ConflictError("archived product cannot be edited")
        if price_usd < 0:
            raise ValidationError("price_usd must be zero or greater")
        offering.price_usd = price_usd
        if currency is not None:
            offering.currency = self._normalize_currency(currency)
        amount = float(price_usd)
        code = getattr(offering, "currency", None) or "INR"
        await audit(
            self._session,
            action="offering.price_updated",
            actor_user_id=caller_user_id,
            payload={"offering_id": str(offering.id), "product_id": str(product.id)},
        )
        saved = OfferingListItem(
            offering_id=offering.id,
            product_id=product.id,
            product_name=product.name,
            plan_name=offering.plan_name,
            status=offering.status,
            price_usd=amount,
            currency=code,
            price=amount,
        )
        await self._session.commit()
        return saved

    async def archive_product(self, *, product_id: UUID, caller_user_id: UUID) -> ProductItem:
        product = await self._owned_product(product_id, caller_user_id)
        if product.status == "archived":
            raise ConflictError("already archived")
        product.status = "archived"
        product.archived_at = utcnow()
        offerings = (
            await self._session.execute(
                select(OfferingRow).where(
                    OfferingRow.product_id == product.id, OfferingRow.status == "published"
                )
            )
        ).scalars().all()
        for offering in offerings:
            offering.status = "unpublished"
        await audit(
            self._session,
            action="product.archived",
            actor_user_id=caller_user_id,
            payload={"product_id": str(product.id)},
        )
        await self._session.commit()
        return ProductItem(
            product_id=product.id,
            name=product.name,
            fulfilment_type=product.fulfilment_type,
            status=product.status,
            category=product.category,
        )

    async def create_offering(
        self,
        *,
        product_id: UUID,
        caller_user_id: UUID,
        plan_name: str,
        billing_period: str,
        price_usd: Decimal,
        included_transactions: int | None,
        overage_price_per_1k: Decimal | None,
        currency: str | None = None,
    ) -> OfferingCreated:
        product = await self._owned_product(product_id, caller_user_id)
        if product.status == "archived":
            raise ConflictError("archived product cannot take a new offering")
        plan_name = plan_name.strip()
        billing_period = billing_period.strip()
        if not plan_name or not billing_period:
            raise ValidationError("plan_name and billing_period are required")
        if price_usd < 0:
            raise ValidationError("price_usd must be zero or greater")
        offering_currency = (
            self._normalize_currency(currency)
            if currency
            else await self._vendor_default_currency(product.vendor_id)
        )
        offering = OfferingRow(
            id=uuid.uuid4(),
            product_id=product.id,
            plan_name=plan_name,
            billing_period=billing_period,
            price_usd=price_usd,
            currency=offering_currency,
            included_transactions=included_transactions,
            overage_price_per_1k=overage_price_per_1k,
            status="draft",
        )
        self._session.add(offering)
        await audit(
            self._session,
            action="offering.created",
            actor_user_id=caller_user_id,
            payload={"offering_id": str(offering.id), "product_id": str(product.id)},
        )
        await self._session.commit()
        return OfferingCreated(
            offering_id=offering.id,
            product_id=product.id,
            plan_name=plan_name,
            status="draft",
        )

    async def list_vendors(
        self, *, caller_user_id: UUID, status: str | None, q: str | None = None
    ) -> list[VendorDirectoryItem]:
        await require_platform_operator(self._session, caller_user_id)
        stmt = select(VendorProfileRow).order_by(VendorProfileRow.legal_name.asc())
        if status:
            stmt = stmt.where(VendorProfileRow.status == status)
        if q and q.strip():
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(func.lower(VendorProfileRow.legal_name).like(pattern))
        vendors = (await self._session.execute(stmt)).scalars().all()
        if not vendors:
            return []
        vendor_ids = [vendor.id for vendor in vendors]
        product_counts = dict(
            (
                await self._session.execute(
                    select(ProductRow.vendor_id, func.count(ProductRow.id))
                    .where(ProductRow.vendor_id.in_(vendor_ids))
                    .group_by(ProductRow.vendor_id)
                )
            ).all()
        )
        install_counts = dict(
            (
                await self._session.execute(
                    select(ProductRow.vendor_id, func.count(InstallationRow.id))
                    .select_from(ProductRow)
                    .join(OfferingRow, OfferingRow.product_id == ProductRow.id)
                    .join(InstallationRow, InstallationRow.offering_id == OfferingRow.id)
                    .where(
                        ProductRow.vendor_id.in_(vendor_ids),
                        InstallationRow.status == "active",
                    )
                    .group_by(ProductRow.vendor_id)
                )
            ).all()
        )
        plugin_counts = dict(
            (
                await self._session.execute(
                    select(PluginRow.vendor_id, func.count(PluginRow.id))
                    .where(PluginRow.vendor_id.in_(vendor_ids), PluginRow.owner_kind == "vendor")
                    .group_by(PluginRow.vendor_id)
                )
            ).all()
        )
        warehouse_counts = dict(
            (
                await self._session.execute(
                    select(WarehouseRow.vendor_id, func.count(WarehouseRow.id))
                    .where(WarehouseRow.vendor_id.in_(vendor_ids))
                    .group_by(WarehouseRow.vendor_id)
                )
            ).all()
        )
        month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        gmv_rows = (
            await self._session.execute(
                select(
                    ProductRow.vendor_id,
                    func.coalesce(func.sum(OrderLineRow.unit_price * OrderLineRow.quantity), 0),
                )
                .select_from(OrderLineRow)
                .join(OrderRow, OrderRow.id == OrderLineRow.order_id)
                .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(ProductRow.vendor_id.in_(vendor_ids), OrderRow.created_at >= month_start)
                .group_by(ProductRow.vendor_id)
            )
        ).all()
        gmv_mtd = {vid: float(total) for vid, total in gmv_rows}
        return [
            VendorDirectoryItem(
                vendor_id=vendor.id,
                legal_name=vendor.legal_name,
                status=vendor.status,
                product_count=int(product_counts.get(vendor.id, 0)),
                active_installs=int(install_counts.get(vendor.id, 0)),
                plugin_count=int(plugin_counts.get(vendor.id, 0)),
                warehouse_count=int(warehouse_counts.get(vendor.id, 0)),
                kyc_status=vendor.status,
                gmv_mtd=gmv_mtd.get(vendor.id, 0.0),
            )
            for vendor in vendors
        ]

    async def vendor_stats(self, *, caller_user_id: UUID) -> VendorStats:
        await require_platform_operator(self._session, caller_user_id)

        async def _count(status: str) -> int:
            return int(
                (
                    await self._session.execute(
                        select(func.count(VendorProfileRow.id)).where(VendorProfileRow.status == status)
                    )
                ).scalar_one()
            )

        plugins = int(
            (
                await self._session.execute(select(func.count(PluginRow.id)))
            ).scalar_one()
        )
        return VendorStats(
            active=await _count("verified"),
            pending_verification=await _count("pending_verification"),
            suspended=await _count("suspended"),
            total_plugins=plugins,
        )

    async def reinstate_vendor(self, *, vendor_id: UUID, caller_user_id: UUID) -> SuspendResult:
        await require_platform_operator(self._session, caller_user_id)
        vendor = await self._session.get(VendorProfileRow, vendor_id)
        if vendor is None:
            raise NotFoundError("vendor not found")
        if vendor.status != "suspended":
            raise ConflictError("vendor is not suspended")
        vendor.status = "verified"
        await audit(
            self._session,
            action="vendor.reinstated",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id)},
        )
        await self._session.commit()
        return SuspendResult(vendor_id=vendor.id, status=vendor.status, offerings_unpublished=0)

    async def suspend_vendor(
        self, *, vendor_id: UUID, caller_user_id: UUID, reason: str
    ) -> SuspendResult:
        await require_platform_operator(self._session, caller_user_id)
        reason = reason.strip()
        if not reason:
            raise ValidationError("reason is required")
        vendor = await self._session.get(VendorProfileRow, vendor_id)
        if vendor is None:
            raise NotFoundError("vendor not found")
        if vendor.status == "suspended":
            raise ConflictError("already suspended")
        vendor.status = "suspended"
        offerings = (
            await self._session.execute(
                select(OfferingRow)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(ProductRow.vendor_id == vendor_id, OfferingRow.status == "published")
            )
        ).scalars().all()
        for offering in offerings:
            offering.status = "unpublished"
            await audit(
                self._session,
                action="offering.unpublished",
                actor_user_id=caller_user_id,
                payload={"offering_id": str(offering.id), "vendor_id": str(vendor_id)},
            )
        await audit(
            self._session,
            action="vendor.suspended",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "reason": reason, "offerings_unpublished": len(offerings)},
        )
        await self._session.commit()
        return SuspendResult(
            vendor_id=vendor.id,
            status=vendor.status,
            offerings_unpublished=len(offerings),
        )

    async def publish_offering(self, *, offering_id: UUID, caller_user_id: UUID) -> OfferingCreated:
        offering = await self._session.get(OfferingRow, offering_id)
        if offering is None:
            raise NotFoundError("offering not found")
        product = await self._owned_product(offering.product_id, caller_user_id)
        if offering.status == "published":
            raise ConflictError("already published")
        if offering.status != "draft":
            raise ConflictError("offering cannot be published")
        approved = (
            await self._session.execute(
                select(PluginVersionRow.id).where(
                    PluginVersionRow.plugin_id == product.plugin_id,
                    PluginVersionRow.status == "approved",
                )
            )
        ).scalar_one_or_none()
        if approved is None:
            raise ConflictError("plugin version is not approved")
        review_required = await self._product_content_review_required()
        if review_required and product.pa_status not in ("live",):
            product.pa_status = "pending_review"
            product.status = "published"
            offering.status = "draft"
            await audit(
                self._session,
                action="product.content_review_queued",
                actor_user_id=caller_user_id,
                payload={"offering_id": str(offering.id), "product_id": str(product.id)},
            )
            await self._session.commit()
            return OfferingCreated(
                offering_id=offering.id,
                product_id=product.id,
                plan_name=offering.plan_name,
                status="pending_review",
            )
        offering.status = "published"
        if product.status == "draft":
            product.status = "published"
        product.pa_status = "live"
        await audit(
            self._session,
            action="offering.published",
            actor_user_id=caller_user_id,
            payload={"offering_id": str(offering.id), "product_id": str(product.id)},
        )
        await self._session.commit()
        return OfferingCreated(
            offering_id=offering.id,
            product_id=product.id,
            plan_name=offering.plan_name,
            status="published",
        )

    async def catalog(
        self,
        *,
        category: str | None,
        q: str | None,
        vendor_id: UUID | None,
        vendor_ids: list[UUID] | None = None,
        verified_only: bool = False,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        sort: str = "newest",
        pincode: str | None = None,
        in_stock: bool = False,
        fulfilment: str | None = None,
    ) -> CatalogResult:
        selected_vendors = list(vendor_ids or [])
        if vendor_id is not None and vendor_id not in selected_vendors:
            selected_vendors.append(vendor_id)

        base = (
            select(OfferingRow, ProductRow, VendorProfileRow)
            .join(ProductRow, ProductRow.id == OfferingRow.product_id)
            .join(VendorProfileRow, VendorProfileRow.id == ProductRow.vendor_id)
            .where(OfferingRow.status == "published", ProductRow.status == "published")
        )
        if await self._product_content_review_required():
            base = base.where(ProductRow.pa_status.in_(("live", "not_submitted")))
        base = base.where(
            (ProductRow.fulfilment_type != "SHIP_PHYSICAL")
            | exists(
                select(ProductServiceCityRow.product_id).where(
                    ProductServiceCityRow.product_id == ProductRow.id
                )
            )
        )

        # Facets: vendors from catalog before vendor_ids filter
        facet_stmt = base
        if category:
            facet_stmt = facet_stmt.where(ProductRow.category == category)
        if q:
            facet_stmt = facet_stmt.where(ProductRow.name.ilike(f"%{q.strip()}%"))
        if verified_only:
            facet_stmt = facet_stmt.where(VendorProfileRow.status == "verified")
        facet_rows = (await self._session.execute(facet_stmt)).all()
        vendors_map: dict[UUID, str] = {}
        for _off, product, vendor in facet_rows:
            vendors_map[vendor.id] = vendor.legal_name
        vendor_facets = [
            CatalogVendorFacet(vendor_id=vid, name=name)
            for vid, name in sorted(vendors_map.items(), key=lambda item: item[1].lower())
        ]

        stmt = base
        if category:
            stmt = stmt.where(ProductRow.category == category)
        if q:
            stmt = stmt.where(ProductRow.name.ilike(f"%{q.strip()}%"))
        if selected_vendors:
            stmt = stmt.where(ProductRow.vendor_id.in_(selected_vendors))
        if verified_only:
            stmt = stmt.where(VendorProfileRow.status == "verified")
        if price_min is not None:
            stmt = stmt.where(OfferingRow.price_usd >= price_min)
        if price_max is not None:
            stmt = stmt.where(OfferingRow.price_usd <= price_max)

        fulfilment_modes = {
            part.strip().lower()
            for part in (fulfilment or "").split(",")
            if part.strip()
        }
        if fulfilment_modes and fulfilment_modes != {"physical", "digital"}:
            if fulfilment_modes == {"physical"}:
                stmt = stmt.where(ProductRow.fulfilment_type.in_(PHYSICAL_FULFILMENT))
            elif fulfilment_modes == {"digital"}:
                stmt = stmt.where(ProductRow.fulfilment_type.notin_(PHYSICAL_FULFILMENT))

        pin = (pincode or "").strip()
        if pin:
            stmt = stmt.where(
                (ProductRow.fulfilment_type.notin_(PHYSICAL_FULFILMENT))
                | exists(
                    select(ProductServiceCityRow.product_id)
                    .join(
                        VendorServiceCityRow,
                        VendorServiceCityRow.id == ProductServiceCityRow.city_id,
                    )
                    .join(
                        VendorCityPincodeRow,
                        VendorCityPincodeRow.city_id == VendorServiceCityRow.id,
                    )
                    .where(
                        ProductServiceCityRow.product_id == ProductRow.id,
                        VendorCityPincodeRow.pincode == pin,
                    )
                )
            )

        if sort == "price_asc":
            stmt = stmt.order_by(OfferingRow.price_usd.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(OfferingRow.price_usd.desc())
        else:
            stmt = stmt.order_by(OfferingRow.created_at.desc())

        rows = (await self._session.execute(stmt)).all()
        product_ids = list({product.id for _o, product, _v in rows})
        ratings = await self._rating_map(product_ids)
        stock = await self._stock_map(product_ids)

        cards: list[CatalogCard] = []
        for offering, product, vendor in rows:
            available, reserved = stock.get(product.id, (0, 0))
            is_physical = product.fulfilment_type in PHYSICAL_FULFILMENT
            product_in_stock = (not is_physical) or (available > reserved)
            if in_stock and not product_in_stock:
                continue
            avg, count = ratings.get(product.id, (0.0, 0))
            card = self._card(offering, product, vendor)
            cards.append(
                CatalogCard(
                    offering_id=card.offering_id,
                    product_id=card.product_id,
                    product_name=card.product_name,
                    vendor_name=card.vendor_name,
                    vendor_id=card.vendor_id,
                    plan_name=card.plan_name,
                    price_usd=card.price_usd,
                    billing_period=card.billing_period,
                    fulfilment_type=card.fulfilment_type,
                    category=card.category,
                    currency=card.currency,
                    price=card.price,
                    avg_rating=avg,
                    review_count=count,
                    in_stock=product_in_stock,
                )
            )
        return CatalogResult(cards=cards, vendors=vendor_facets)

    async def _rating_map(self, product_ids: list[UUID]) -> dict[UUID, tuple[float, int]]:
        if not product_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    ProductReviewRow.product_id,
                    func.avg(ProductReviewRow.rating),
                    func.count(ProductReviewRow.id),
                )
                .where(ProductReviewRow.product_id.in_(product_ids))
                .group_by(ProductReviewRow.product_id)
            )
        ).all()
        out: dict[UUID, tuple[float, int]] = {}
        for product_id, avg, count in rows:
            out[product_id] = (round(float(avg or 0), 1), int(count or 0))
        return out

    async def _stock_map(self, product_ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
        if not product_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    InventoryRow.product_id,
                    func.coalesce(func.sum(InventoryRow.available), 0),
                    func.coalesce(func.sum(InventoryRow.reserved), 0),
                )
                .where(InventoryRow.product_id.in_(product_ids))
                .group_by(InventoryRow.product_id)
            )
        ).all()
        return {
            product_id: (int(available or 0), int(reserved or 0))
            for product_id, available, reserved in rows
        }

    async def list_public_reviews(self, *, product_id: UUID) -> PublicReviewList:
        product = await self._session.get(ProductRow, product_id)
        if product is None or product.status != "published":
            raise NotFoundError("product not found")
        rows = (
            await self._session.execute(
                select(ProductReviewRow, OrderRow, TenantRow, AddressRow)
                .join(OrderRow, OrderRow.id == ProductReviewRow.order_id)
                .join(TenantRow, TenantRow.id == ProductReviewRow.tenant_id)
                .outerjoin(AddressRow, AddressRow.id == OrderRow.address_id)
                .where(ProductReviewRow.product_id == product_id)
                .order_by(ProductReviewRow.created_at.desc())
            )
        ).all()
        reviews: list[PublicReview] = []
        total = 0
        count = 0
        for review, _order, tenant, address in rows:
            name = address.contact_name if address is not None else tenant.name
            reviews.append(
                PublicReview(
                    rating=review.rating,
                    comment=review.comment,
                    customer_name=name,
                    created_at=review.created_at.isoformat() if review.created_at else "",
                )
            )
            total += review.rating
            count += 1
        avg = round(total / count, 1) if count else 0.0
        return PublicReviewList(reviews=reviews, avg_rating=avg, review_count=count)

    async def home(self) -> dict[str, list[CatalogCard]]:
        result = await self.catalog(
            category=None,
            q=None,
            vendor_id=None,
            verified_only=False,
            price_min=None,
            price_max=None,
            sort="newest",
        )
        cards = result.cards
        return {"new": cards[:8], "trending": cards[:12], "sponsored": []}

    async def product_detail(self, *, product_id: UUID) -> ProductDetail:
        product = await self._session.get(ProductRow, product_id)
        if product is None or product.status != "published":
            raise NotFoundError("product not found")
        if await self._product_content_review_required() and product.pa_status not in (
            "live",
            "not_submitted",
        ):
            raise NotFoundError("product not found")
        if product.fulfilment_type == "SHIP_PHYSICAL":
            has_cities = (
                await self._session.execute(
                    select(ProductServiceCityRow.product_id).where(
                        ProductServiceCityRow.product_id == product.id
                    )
                )
            ).scalar_one_or_none()
            if has_cities is None:
                raise NotFoundError("product not found")
        vendor = await self._session.get(VendorProfileRow, product.vendor_id)
        content = await self._session.get(ProductContentRow, product.id)
        offerings = (
            await self._session.execute(
                select(OfferingRow).where(
                    OfferingRow.product_id == product.id, OfferingRow.status == "published"
                )
            )
        ).scalars().all()
        capabilities = (
            await self._approved_capabilities(product.plugin_id)
            if product.plugin_id is not None
            else []
        )
        return ProductDetail(
            product_id=product.id,
            name=product.name,
            description=product.description,
            fulfilment_type=product.fulfilment_type,
            vendor_name=vendor.legal_name if vendor else "",
            category=product.category,
            content=content.payload if content else {},
            capabilities=capabilities,
            offerings=[
                OfferingDetail(
                    offering_id=row.id,
                    plan_name=row.plan_name,
                    price_usd=float(row.price_usd),
                    billing_period=row.billing_period,
                    status=row.status,
                    currency=getattr(row, "currency", None) or "INR",
                    price=float(row.price_usd),
                )
                for row in offerings
            ],
        )

    async def install(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        caller_principal_id: UUID,
        offering_id: UUID,
        project_id: UUID | None,
        accepted_capabilities: list[str],
        request_id: str | None,
    ) -> InstallResult:
        decision = await self._authorization.authorize(
            AuthorizeCommand(
                principal_id=caller_principal_id,
                permission_code="resource.create",
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
                request_id=request_id,
            )
        )
        if not decision.allowed:
            raise ForbiddenError(public_forbid_detail(decision.reason))

        tenant = await self._session.get(TenantRow, tenant_id)
        if tenant is None or tenant.status != "active":
            raise NotFoundError("tenant not found")
        offering = await self._session.get(OfferingRow, offering_id)
        if offering is None or offering.status != "published":
            raise NotFoundError("offering not found")
        product = await self._session.get(ProductRow, offering.product_id)
        if product is None or product.status != "published":
            raise NotFoundError("offering not found")
        if await self._product_content_review_required() and product.pa_status not in (
            "live",
            "not_submitted",
        ):
            raise NotFoundError("offering not found")
        if product.fulfilment_type not in PROVISION_TYPES:
            raise ConflictError("this fulfilment type is ordered from the cart")
        vendor = await self._session.get(VendorProfileRow, product.vendor_id)
        if vendor is None or vendor.status != "verified":
            raise ConflictError("vendor is not accepting installs")

        resolved_project = await self._resolve_project(tenant_id, project_id)
        declared = await self._approved_capabilities(product.plugin_id)
        accepted = [item.strip() for item in accepted_capabilities if item.strip()]
        if set(accepted) != set(declared):
            raise ConflictError("accepted capabilities do not match the plugin version")

        existing = (
            await self._session.execute(
                select(InstallationRow.id).where(
                    InstallationRow.tenant_id == tenant_id,
                    InstallationRow.offering_id == offering_id,
                    InstallationRow.status.in_(("provisioning", "active")),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("offering already installed")

        installation = InstallationRow(
            id=uuid.uuid4(),
            offering_id=offering.id,
            tenant_id=tenant_id,
            project_id=resolved_project,
            status="provisioning",
            accepted_capabilities=accepted,
        )
        entitlement = EntitlementRow(
            id=uuid.uuid4(),
            installation_id=installation.id,
            offering_id=offering.id,
            tenant_id=tenant_id,
            status="active",
        )
        self._session.add(installation)
        await self._session.flush()
        self._session.add(entitlement)
        outbox = OutboxEventRow(
            id=uuid.uuid4(),
            type="provision_service",
            payload_json={"installation_id": str(installation.id)},
            status="pending",
        )
        self._session.add(outbox)
        if settings.workflow_mode != "temporal":
            await handle_provision(self._session, {"installation_id": str(installation.id)})
            outbox.status = "processed"
        await audit(
            self._session,
            action="installation.created",
            actor_user_id=caller_user_id,
            tenant_id=tenant_id,
            payload={
                "installation_id": str(installation.id),
                "entitlement_id": str(entitlement.id),
                "offering_id": str(offering.id),
            },
        )
        await self._session.commit()
        return InstallResult(
            installation_id=installation.id,
            offering_id=offering.id,
            tenant_id=tenant_id,
            status=installation.status,
            entitlement_id=entitlement.id,
        )

    async def list_entitlements(
        self, *, tenant_id: UUID, caller_principal_id: UUID, request_id: str | None
    ) -> list[EntitlementItem]:
        decision = await self._authorization.authorize(
            AuthorizeCommand(
                principal_id=caller_principal_id,
                permission_code="resource.read",
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
                request_id=request_id,
            )
        )
        if not decision.allowed:
            raise ForbiddenError(public_forbid_detail(decision.reason))
        rows = (
            await self._session.execute(
                select(EntitlementRow, OfferingRow, ProductRow, InstallationRow)
                .join(OfferingRow, OfferingRow.id == EntitlementRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .join(InstallationRow, InstallationRow.id == EntitlementRow.installation_id)
                .where(EntitlementRow.tenant_id == tenant_id)
                .order_by(EntitlementRow.granted_at.desc())
            )
        ).all()
        return [
            EntitlementItem(
                entitlement_id=entitlement.id,
                offering_name=f"{product.name} — {offering.plan_name}",
                status=entitlement.status,
                installation_status=installation.status,
                granted_at=entitlement.granted_at.isoformat() if entitlement.granted_at else "",
            )
            for entitlement, offering, product, installation in rows
        ]

    async def vendor_installs(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[VendorInstallItem]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(InstallationRow, ProductRow, TenantRow)
                .join(OfferingRow, OfferingRow.id == InstallationRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .join(TenantRow, TenantRow.id == InstallationRow.tenant_id)
                .where(ProductRow.vendor_id == vendor_id)
                .order_by(InstallationRow.created_at.desc())
            )
        ).all()
        return [
            VendorInstallItem(
                installation_id=installation.id,
                tenant_name=tenant.name,
                product_name=product.name,
                fulfilment_type=product.fulfilment_type,
                status=installation.status,
                since=installation.created_at.isoformat() if installation.created_at else "",
            )
            for installation, product, tenant in rows
        ]

    async def list_admin_products(
        self,
        *,
        caller_user_id: UUID,
        pa_status: str | None = None,
        q: str | None = None,
        vendor_id: UUID | None = None,
    ) -> list[AdminProductItem]:
        await require_platform_operator(self._session, caller_user_id)
        stmt = (
            select(ProductRow, VendorProfileRow)
            .join(VendorProfileRow, VendorProfileRow.id == ProductRow.vendor_id)
            .order_by(ProductRow.updated_at.desc())
        )
        if pa_status:
            stmt = stmt.where(ProductRow.pa_status == pa_status)
        if vendor_id is not None:
            stmt = stmt.where(ProductRow.vendor_id == vendor_id)
        if q and q.strip():
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(ProductRow.name).like(pattern),
                    func.lower(VendorProfileRow.legal_name).like(pattern),
                )
            )
        rows = (await self._session.execute(stmt)).all()
        return [
            AdminProductItem(
                product_id=product.id,
                name=product.name,
                vendor_id=vendor.id,
                vendor_name=vendor.legal_name,
                category=product.category,
                status=product.status,
                pa_status=product.pa_status,
                pa_reject_reason=product.pa_reject_reason or "",
                fulfilment_type=product.fulfilment_type,
                submitted_at=product.updated_at.isoformat() if product.updated_at else "",
            )
            for product, vendor in rows
        ]

    async def product_stats(self, *, caller_user_id: UUID) -> AdminProductStats:
        await require_platform_operator(self._session, caller_user_id)

        async def _count(status: str) -> int:
            return int(
                (
                    await self._session.execute(
                        select(func.count(ProductRow.id)).where(ProductRow.pa_status == status)
                    )
                ).scalar_one()
            )

        locations = int(
            (
                await self._session.execute(
                    select(func.count(func.distinct(WarehouseRow.location)))
                )
            ).scalar_one()
        )
        return AdminProductStats(
            pending_review=await _count("pending_review"),
            live=await _count("live"),
            rejected=await _count("rejected"),
            not_submitted=await _count("not_submitted"),
            warehouse_locations=locations,
        )

    async def approve_product(self, *, product_id: UUID, caller_user_id: UUID) -> AdminProductItem:
        await require_platform_operator(self._session, caller_user_id)
        product = await self._session.get(ProductRow, product_id)
        if product is None:
            raise NotFoundError("product not found")
        if product.pa_status not in ("pending_review",):
            raise ConflictError("product is not pending review")
        vendor = await self._session.get(VendorProfileRow, product.vendor_id)
        item = AdminProductItem(
            product_id=product.id,
            name=product.name,
            vendor_id=product.vendor_id,
            vendor_name=vendor.legal_name if vendor else "",
            category=product.category,
            status="published",
            pa_status="live",
            pa_reject_reason="",
            fulfilment_type=product.fulfilment_type,
            submitted_at=product.updated_at.isoformat() if product.updated_at else "",
        )
        product.pa_status = "live"
        product.pa_reject_reason = ""
        if product.status == "draft":
            product.status = "published"
        offerings = (
            await self._session.execute(
                select(OfferingRow).where(
                    OfferingRow.product_id == product.id, OfferingRow.status == "draft"
                )
            )
        ).scalars().all()
        for offering in offerings:
            offering.status = "published"
        await audit(
            self._session,
            action="product.content_approved",
            actor_user_id=caller_user_id,
            payload={"product_id": str(product.id), "offerings_published": len(offerings)},
        )
        await self._session.commit()
        return item

    async def reject_product(
        self, *, product_id: UUID, caller_user_id: UUID, reason: str
    ) -> AdminProductItem:
        await require_platform_operator(self._session, caller_user_id)
        reason = reason.strip()
        if not reason:
            raise ValidationError("reason is required")
        product = await self._session.get(ProductRow, product_id)
        if product is None:
            raise NotFoundError("product not found")
        if product.pa_status not in ("pending_review",):
            raise ConflictError("product is not pending review")
        vendor = await self._session.get(VendorProfileRow, product.vendor_id)
        item = AdminProductItem(
            product_id=product.id,
            name=product.name,
            vendor_id=product.vendor_id,
            vendor_name=vendor.legal_name if vendor else "",
            category=product.category,
            status=product.status,
            pa_status="rejected",
            pa_reject_reason=reason,
            fulfilment_type=product.fulfilment_type,
            submitted_at=product.updated_at.isoformat() if product.updated_at else "",
        )
        product.pa_status = "rejected"
        product.pa_reject_reason = reason
        offerings = (
            await self._session.execute(
                select(OfferingRow).where(
                    OfferingRow.product_id == product.id,
                    OfferingRow.status.in_(("published", "draft")),
                )
            )
        ).scalars().all()
        for offering in offerings:
            offering.status = "unpublished"
        await audit(
            self._session,
            action="product.content_rejected",
            actor_user_id=caller_user_id,
            payload={"product_id": str(product.id), "reason": reason},
        )
        await self._session.commit()
        return item

    async def locations_summary(self, *, caller_user_id: UUID) -> list[LocationSummaryItem]:
        await require_platform_operator(self._session, caller_user_id)
        rows = (
            await self._session.execute(
                select(
                    WarehouseRow.location,
                    func.count(WarehouseRow.id),
                    func.count(func.distinct(WarehouseRow.vendor_id)),
                    func.coalesce(func.sum(InventoryRow.available + InventoryRow.reserved), 0),
                )
                .outerjoin(InventoryRow, InventoryRow.warehouse_id == WarehouseRow.id)
                .group_by(WarehouseRow.location)
                .order_by(WarehouseRow.location.asc())
            )
        ).all()
        return [
            LocationSummaryItem(
                location=location,
                warehouse_count=int(warehouse_count),
                vendor_count=int(vendor_count),
                units_stored=int(units),
            )
            for location, warehouse_count, vendor_count, units in rows
        ]

    async def _product_content_review_required(self) -> bool:
        row = await self._session.get(PlatformConfigRow, "product_content_review_required")
        if row is None:
            return True
        value = row.value
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    async def _owned_product(self, product_id: UUID, user_id: UUID) -> ProductRow:
        product = await self._session.get(ProductRow, product_id)
        if product is None:
            raise NotFoundError("product not found")
        await require_vendor_owner(self._session, product.vendor_id, user_id)
        return product

    async def _resolve_project(self, tenant_id: UUID, project_id: UUID | None) -> UUID:
        if project_id is not None:
            project = await self._session.get(ProjectRow, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise ValidationError("project not found in tenant")
            return project.id
        project = (
            await self._session.execute(
                select(ProjectRow)
                .where(ProjectRow.tenant_id == tenant_id, ProjectRow.status == "active")
                .order_by(ProjectRow.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if project is None:
            raise ValidationError("project not found in tenant")
        return project.id

    async def _enrich_product_items(self, rows: list[ProductRow]) -> list[ProductItem]:
        if not rows:
            return []
        ids = [row.id for row in rows]
        payloads: dict[UUID, dict] = {}
        stored = (
            await self._session.execute(
                select(ProductContentRow).where(ProductContentRow.product_id.in_(ids))
            )
        ).scalars().all()
        payloads = {item.product_id: item.payload or {} for item in stored}

        city_links = (
            await self._session.execute(
                select(ProductServiceCityRow, VendorServiceCityRow)
                .join(
                    VendorServiceCityRow,
                    VendorServiceCityRow.id == ProductServiceCityRow.city_id,
                )
                .where(ProductServiceCityRow.product_id.in_(ids))
            )
        ).all()
        cities_by_product: dict[UUID, list[str]] = {pid: [] for pid in ids}
        for link, city in city_links:
            cities_by_product.setdefault(link.product_id, []).append(city.city_name)

        inventory_rows = (
            await self._session.execute(
                select(InventoryRow).where(InventoryRow.product_id.in_(ids))
            )
        ).scalars().all()
        stock_by_product: dict[UUID, list[InventoryRow]] = {}
        for stock in inventory_rows:
            stock_by_product.setdefault(stock.product_id, []).append(stock)

        published_products = set(
            (
                await self._session.execute(
                    select(OfferingRow.product_id).where(
                        OfferingRow.product_id.in_(ids),
                        OfferingRow.status == "published",
                    )
                )
            ).scalars().all()
        )

        items: list[ProductItem] = []
        for row in rows:
            payload = payloads.get(row.id, {})
            city_names = sorted(cities_by_product.get(row.id, []))
            stock_status = self._product_stock_status(stock_by_product.get(row.id, []))
            visibility = self._product_visibility(
                row,
                city_names,
                row.id in published_products,
            )
            image_urls = list(payload.get("image_urls") or [])
            items.append(
                ProductItem(
                    product_id=row.id,
                    name=row.name,
                    fulfilment_type=row.fulfilment_type,
                    status=row.status,
                    category=row.category,
                    content=payload,
                    pa_status=row.pa_status,
                    pa_reject_reason=row.pa_reject_reason or "",
                    mrp_inr=float(payload.get("mrp_inr") or 0),
                    image_count=len(image_urls),
                    cities=city_names,
                    stock_status=stock_status,
                    visibility=visibility,
                    brand=str(payload.get("brand") or ""),
                    net_weight=str(payload.get("net_weight") or ""),
                    sku=str(payload.get("sku") or ""),
                    image_urls=image_urls,
                    currency=str(payload.get("currency") or "INR"),
                )
            )
        return items

    async def _vendor_default_currency(self, vendor_id: UUID) -> str:
        row = await self._session.get(VendorSettingsRow, vendor_id)
        if row is None or not row.default_currency:
            return "INR"
        code = row.default_currency.strip().upper()
        return code if code in ALLOWED_CURRENCIES else "INR"

    @staticmethod
    def _normalize_currency(currency: str) -> str:
        code = currency.strip().upper()
        if code not in ALLOWED_CURRENCIES:
            raise ValidationError(
                f"currency must be one of {', '.join(sorted(ALLOWED_CURRENCIES))}"
            )
        return code

    @staticmethod
    def _normalize_optional_currency(currency: str | None) -> str | None:
        if currency is None:
            return None
        cleaned = currency.strip()
        if not cleaned:
            return None
        return CatalogService._normalize_currency(cleaned)

    @staticmethod
    def _inventory_status(available: int, reorder_threshold: int) -> str:
        if available < reorder_threshold:
            return "low_stock"
        return "ok"

    @staticmethod
    def _product_stock_status(rows: list[InventoryRow]) -> str:
        if not rows:
            return "none"
        total = sum(row.available for row in rows)
        if total <= 0:
            return "none"
        if any(row.available < row.reorder_threshold for row in rows):
            return "low"
        return "ok"

    @staticmethod
    def _product_visibility(
        product: ProductRow, city_names: list[str], has_published_offering: bool
    ) -> str:
        if product.status == "archived":
            return "hidden"
        if product.pa_status == "rejected":
            return "hidden"
        if product.pa_status == "pending_review":
            return "awaiting_pa"
        if product.fulfilment_type == "SHIP_PHYSICAL":
            if product.pa_status == "live" and city_names:
                return "visible"
            return "hidden"
        if product.pa_status in ("live", "not_submitted") and has_published_offering:
            return "visible"
        return "hidden"

    @staticmethod
    def _listing_snapshot(product: ProductRow, payload: dict) -> tuple:
        return (
            product.name,
            product.description,
            product.category,
            str(payload.get("sku") or ""),
            str(payload.get("brand") or ""),
            str(payload.get("net_weight") or ""),
            float(payload.get("mrp_inr") or 0),
            tuple(payload.get("image_urls") or []),
        )

    @staticmethod
    def _validate_pincodes(pincodes: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in pincodes:
            pin = raw.strip()
            if not re.fullmatch(r"\d{6}", pin):
                raise ValidationError("pincodes must be 6-digit numbers")
            if pin not in seen:
                seen.add(pin)
                cleaned.append(pin)
        return cleaned

    @staticmethod
    def _validate_image_urls(image_urls: list[str]) -> list[str]:
        if len(image_urls) < 2 or len(image_urls) > 5:
            raise ValidationError("image_urls must contain 2 to 5 items")
        cleaned: list[str] = []
        for raw in image_urls:
            url = raw.strip()
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValidationError("image_urls must be https URLs")
            cleaned.append(url)
        return cleaned

    async def _approved_capabilities(self, plugin_id: UUID | None) -> list[str]:
        if plugin_id is None:
            return []
        version = (
            await self._session.execute(
                select(PluginVersionRow)
                .where(
                    PluginVersionRow.plugin_id == plugin_id,
                    PluginVersionRow.status == "approved",
                )
                .order_by(PluginVersionRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if version is None:
            return []
        rows = (
            await self._session.execute(
                select(PluginCapabilityRow.scope)
                .where(PluginCapabilityRow.version_id == version.id)
                .order_by(PluginCapabilityRow.scope.asc())
            )
        ).scalars().all()
        return list(rows)

    @staticmethod
    def _card(offering: OfferingRow, product: ProductRow, vendor: VendorProfileRow) -> CatalogCard:
        amount = float(offering.price_usd)
        currency = getattr(offering, "currency", None) or "INR"
        return CatalogCard(
            offering_id=offering.id,
            product_id=product.id,
            product_name=product.name,
            vendor_name=vendor.legal_name,
            vendor_id=vendor.id,
            plan_name=offering.plan_name,
            price_usd=amount,
            billing_period=offering.billing_period,
            fulfilment_type=product.fulfilment_type,
            category=product.category,
            currency=currency,
            price=amount,
        )
