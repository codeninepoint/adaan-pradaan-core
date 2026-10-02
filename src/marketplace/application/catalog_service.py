from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
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
    PluginCapabilityRow,
    PluginRow,
    PluginVersionRow,
    ProductContentRow,
    ProductRow,
)
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shared.infrastructure.models import OutboxEventRow
from shared.settings import settings
from tenant.infrastructure.models import ProjectRow, TenantRow
from vendor.infrastructure.models import VendorProfileRow


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


@dataclass(frozen=True, slots=True)
class ProductItem:
    product_id: UUID
    name: str
    fulfilment_type: str
    status: str
    category: str


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


@dataclass(frozen=True, slots=True)
class OfferingDetail:
    offering_id: UUID
    plan_name: str
    price_usd: float
    billing_period: str
    status: str


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
        plugin_id: UUID,
        fulfilment_type: str,
        content: dict | None,
        category: str | None,
    ) -> ProductCreated:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        if vendor.status != "verified":
            raise ForbiddenError("vendor not verified")
        plugin = await self._session.get(PluginRow, plugin_id)
        if plugin is None or plugin.vendor_id != vendor_id:
            raise NotFoundError("plugin not found")
        name = name.strip()
        if not name:
            raise ValidationError("name is required")
        if fulfilment_type not in FULFILMENT_TYPES:
            raise ValidationError("unknown fulfilment_type")

        product = ProductRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            plugin_id=plugin_id,
            name=name,
            description=description.strip(),
            category=(category or plugin.category).strip(),
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
                "plugin_id": str(plugin_id),
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
        return [
            ProductItem(
                product_id=row.id,
                name=row.name,
                fulfilment_type=row.fulfilment_type,
                status=row.status,
                category=row.category,
            )
            for row in rows
        ]

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
    ) -> ProductItem:
        product = await self._owned_product(product_id, caller_user_id)
        if product.status == "archived":
            raise ConflictError("archived product cannot be edited")
        if name is not None and name.strip():
            product.name = name.strip()
        if description is not None:
            product.description = description.strip()
        await audit(
            self._session,
            action="product.updated",
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
        offering = OfferingRow(
            id=uuid.uuid4(),
            product_id=product.id,
            plan_name=plan_name,
            billing_period=billing_period,
            price_usd=price_usd,
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
        self, *, caller_user_id: UUID, status: str | None
    ) -> list[VendorDirectoryItem]:
        await require_platform_operator(self._session, caller_user_id)
        stmt = select(VendorProfileRow).order_by(VendorProfileRow.legal_name.asc())
        if status:
            stmt = stmt.where(VendorProfileRow.status == status)
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
        return [
            VendorDirectoryItem(
                vendor_id=vendor.id,
                legal_name=vendor.legal_name,
                status=vendor.status,
                product_count=int(product_counts.get(vendor.id, 0)),
                active_installs=int(install_counts.get(vendor.id, 0)),
            )
            for vendor in vendors
        ]

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
        offering.status = "published"
        if product.status == "draft":
            product.status = "published"
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
        verified_only: bool,
        price_min: Decimal | None,
        price_max: Decimal | None,
        sort: str,
    ) -> list[CatalogCard]:
        stmt = (
            select(OfferingRow, ProductRow, VendorProfileRow)
            .join(ProductRow, ProductRow.id == OfferingRow.product_id)
            .join(VendorProfileRow, VendorProfileRow.id == ProductRow.vendor_id)
            .where(OfferingRow.status == "published", ProductRow.status == "published")
        )
        if category:
            stmt = stmt.where(ProductRow.category == category)
        if q:
            stmt = stmt.where(ProductRow.name.ilike(f"%{q.strip()}%"))
        if vendor_id is not None:
            stmt = stmt.where(ProductRow.vendor_id == vendor_id)
        if verified_only:
            stmt = stmt.where(VendorProfileRow.status == "verified")
        if price_min is not None:
            stmt = stmt.where(OfferingRow.price_usd >= price_min)
        if price_max is not None:
            stmt = stmt.where(OfferingRow.price_usd <= price_max)
        if sort == "price_asc":
            stmt = stmt.order_by(OfferingRow.price_usd.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(OfferingRow.price_usd.desc())
        else:
            stmt = stmt.order_by(OfferingRow.created_at.desc())
        rows = (await self._session.execute(stmt)).all()
        return [self._card(offering, product, vendor) for offering, product, vendor in rows]

    async def home(self) -> dict[str, list[CatalogCard]]:
        cards = await self.catalog(
            category=None,
            q=None,
            vendor_id=None,
            verified_only=False,
            price_min=None,
            price_max=None,
            sort="newest",
        )
        return {"new": cards[:8], "trending": cards[:12], "sponsored": []}

    async def product_detail(self, *, product_id: UUID) -> ProductDetail:
        product = await self._session.get(ProductRow, product_id)
        if product is None or product.status != "published":
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
        capabilities = await self._approved_capabilities(product.plugin_id)
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

    async def _approved_capabilities(self, plugin_id: UUID) -> list[str]:
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
        return CatalogCard(
            offering_id=offering.id,
            product_id=product.id,
            product_name=product.name,
            vendor_name=vendor.legal_name,
            vendor_id=vendor.id,
            plan_name=offering.plan_name,
            price_usd=float(offering.price_usd),
            billing_period=offering.billing_period,
            fulfilment_type=product.fulfilment_type,
            category=product.category,
        )
