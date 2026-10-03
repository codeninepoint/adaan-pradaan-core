from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.interface.api.dependencies import get_authorization_service
from identity.interface.api.dependencies import CurrentAuthDep, get_session
from marketplace.application.catalog_service import CatalogService
from marketplace.application.plugin_service import PluginService
from marketplace.interface.api.schemas import (
    CatalogItem,
    CatalogResponse,
    CreateOfferingRequest,
    CreateProductRequest,
    DeclareCapabilitiesRequest,
    DeclareCapabilitiesResponse,
    EntitlementItem,
    EntitlementsResponse,
    HomeResponse,
    InstallRequest,
    InstallResponse,
    ListVersionsResponse,
    OfferingDetailItem,
    OfferingListItemResponse,
    OfferingListResponse,
    OfferingResponse,
    PluginListItem,
    PluginListResponse,
    PortalResponse,
    ProductDetailResponse,
    ProductListResponse,
    ProductResponse,
    InventoryAdjustRequest,
    InventoryListResponse,
    InventoryRequest,
    InventoryResponse,
    WarehouseListResponse,
    WarehouseRequest,
    WarehouseResponse,
    ClaimResponse,
    RegisterPluginRequest,
    RequestChangesRequest,
    ReviewDetailResponse,
    RegisterPluginResponse,
    SubmitVersionRequest,
    SubmitVersionResponse,
    SuspendVendorRequest,
    SuspendVendorResponse,
    UpdateOfferingPriceRequest,
    UpdateProductRequest,
    VendorDirectoryItemResponse,
    VendorDirectoryResponse,
    VendorInstallItem,
    VendorInstallListResponse,
    PendingReviewItem,
    PendingReviewsResponse,
    VersionDecisionRequest,
    VersionDecisionResponse,
    VersionItem,
)

router = APIRouter(prefix="/api/v1", tags=["marketplace"])


def get_plugin_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PluginService:
    return PluginService(session)


def get_catalog_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> CatalogService:
    return CatalogService(session, authorization)


def _card(item) -> CatalogItem:
    return CatalogItem(
        offering_id=str(item.offering_id),
        product_id=str(item.product_id),
        product_name=item.product_name,
        vendor=item.vendor_name,
        vendor_id=str(item.vendor_id),
        plan_name=item.plan_name,
        price_usd=item.price_usd,
        billing_period=item.billing_period,
        fulfilment_type=item.fulfilment_type,
        category=item.category,
    )


@router.get("/vendors/{vendor_id}/portal", response_model=PortalResponse)
async def vendor_portal(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> PortalResponse:
    user, _session, _credential = auth
    result = await service.portal(vendor_id=vendor_id, caller_user_id=user.id)
    return PortalResponse(
        vendor_id=str(result.vendor_id),
        status=result.status,
        product_count=result.product_count,
        offering_count=result.offering_count,
        active_installs=result.active_installs,
        pending_plugin_reviews=result.pending_plugin_reviews,
    )


@router.get("/vendors/{vendor_id}/plugins", response_model=PluginListResponse)
async def list_plugins(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> PluginListResponse:
    user, _session, _credential = auth
    items = await service.list_plugins(vendor_id=vendor_id, caller_user_id=user.id)
    return PluginListResponse(
        plugins=[
            PluginListItem(
                plugin_id=str(item.plugin_id),
                name=item.name,
                slug=item.slug,
                status=item.status,
                latest_version=item.latest_version,
                latest_version_status=item.latest_version_status,
            )
            for item in items
        ]
    )


@router.post(
    "/vendors/{vendor_id}/plugins",
    response_model=RegisterPluginResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_plugin(
    vendor_id: UUID,
    body: RegisterPluginRequest,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> RegisterPluginResponse:
    user, _session, _credential = auth
    result = await service.register_plugin(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        name=body.name,
        slug=body.slug,
        category=body.category,
        short_description=body.short_description,
    )
    return RegisterPluginResponse(
        plugin_id=str(result.plugin_id),
        slug=result.slug,
        status=result.status,
        vendor_id=str(result.vendor_id),
    )


@router.post(
    "/plugins/{plugin_id}/versions",
    response_model=SubmitVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_version(
    plugin_id: UUID,
    body: SubmitVersionRequest,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> SubmitVersionResponse:
    user, _session, _credential = auth
    result = await service.submit_version(
        plugin_id=plugin_id,
        caller_user_id=user.id,
        version=body.version,
        artifact_url=body.artifact_url,
        changelog=body.changelog,
        sbom_url=body.sbom_url,
    )
    return SubmitVersionResponse(
        version_id=str(result.version_id),
        plugin_id=str(result.plugin_id),
        version=result.version,
        status=result.status,
    )


@router.put(
    "/plugins/versions/{version_id}/capabilities",
    response_model=DeclareCapabilitiesResponse,
)
async def declare_capabilities(
    version_id: UUID,
    body: DeclareCapabilitiesRequest,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> DeclareCapabilitiesResponse:
    user, _session, _credential = auth
    count = await service.declare_capabilities(
        version_id=version_id,
        caller_user_id=user.id,
        capabilities=[(item.scope, item.justification) for item in body.capabilities],
    )
    return DeclareCapabilitiesResponse(version_id=str(version_id), capability_count=count)


@router.get("/plugins/{plugin_id}/versions", response_model=ListVersionsResponse)
async def list_versions(
    plugin_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> ListVersionsResponse:
    user, _session, _credential = auth
    plugin, versions = await service.list_versions(plugin_id=plugin_id, caller_user_id=user.id)
    return ListVersionsResponse(
        plugin_id=str(plugin),
        versions=[
            VersionItem(
                version_id=str(item.version_id),
                version=item.version,
                status=item.status,
                scan_status=item.scan_status,
                submitted_at=item.submitted_at,
                decided_at=item.decided_at,
                artifact_url=item.artifact_url,
                changelog=item.changelog,
                sbom_url=item.sbom_url,
            )
            for item in versions
        ],
    )


@router.get("/admin/plugin-reviews", response_model=PendingReviewsResponse)
async def list_plugin_reviews(
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
    status: Annotated[str | None, Query()] = None,
) -> PendingReviewsResponse:
    user, _session, _credential = auth
    items = await service.list_pending_reviews(caller_user_id=user.id, status=status)
    return PendingReviewsResponse(
        items=[
            PendingReviewItem(
                version_id=str(item.version_id),
                plugin_id=str(item.plugin_id),
                plugin_slug=item.plugin_slug,
                version=item.version,
                status=item.status,
                vendor_id=str(item.vendor_id),
                vendor_name=item.vendor_name,
                claimed_by=str(item.claimed_by) if item.claimed_by else None,
                submitted_at=item.submitted_at,
            )
            for item in items
        ]
    )


@router.get("/plugins/versions/{version_id}/review", response_model=ReviewDetailResponse)
async def plugin_version_review(
    version_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> ReviewDetailResponse:
    user, _session, _credential = auth
    detail = await service.review_detail(version_id=version_id, caller_user_id=user.id)
    return ReviewDetailResponse(
        version_id=str(detail.version_id),
        plugin=detail.plugin_slug,
        version=detail.version,
        status=detail.status,
        scan_status=detail.scan_status,
        requested_capabilities=detail.requested_capabilities,
        sbom_url=detail.sbom_url,
        changelog=detail.changelog,
        artifact_url=detail.artifact_url,
        claimed_by=str(detail.claimed_by) if detail.claimed_by else None,
        review_notes=detail.review_notes,
    )


@router.post("/plugins/versions/{version_id}/request-changes", response_model=VersionDecisionResponse)
async def request_plugin_changes(
    version_id: UUID,
    body: RequestChangesRequest,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> VersionDecisionResponse:
    user, _session, _credential = auth
    result = await service.request_changes(
        version_id=version_id, caller_user_id=user.id, notes=body.notes
    )
    return VersionDecisionResponse(
        version_id=str(result.version_id),
        status=result.status,
        decided_by=str(result.decided_by),
        decided_at=result.decided_at,
    )


@router.post("/admin/plugin-reviews/{version_id}/claim", response_model=ClaimResponse)
async def claim_plugin_review(
    version_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> ClaimResponse:
    user, _session, _credential = auth
    result = await service.claim_version(version_id=version_id, caller_user_id=user.id)
    return ClaimResponse(
        version_id=str(result.version_id),
        claimed_by=str(result.claimed_by),
        claimed_at=result.claimed_at,
    )


@router.get("/admin/vendors", response_model=VendorDirectoryResponse)
async def list_admin_vendors(
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    status: Annotated[str | None, Query()] = None,
) -> VendorDirectoryResponse:
    user, _session, _credential = auth
    items = await service.list_vendors(caller_user_id=user.id, status=status)
    return VendorDirectoryResponse(
        results=[
            VendorDirectoryItemResponse(
                vendor_id=str(item.vendor_id),
                legal_name=item.legal_name,
                status=item.status,
                product_count=item.product_count,
                active_installs=item.active_installs,
            )
            for item in items
        ]
    )


@router.post("/admin/vendors/{vendor_id}/suspend", response_model=SuspendVendorResponse)
async def suspend_vendor(
    vendor_id: UUID,
    body: SuspendVendorRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> SuspendVendorResponse:
    user, _session, _credential = auth
    result = await service.suspend_vendor(
        vendor_id=vendor_id, caller_user_id=user.id, reason=body.reason
    )
    return SuspendVendorResponse(
        vendor_id=str(result.vendor_id),
        status=result.status,
        offerings_unpublished=result.offerings_unpublished,
    )


@router.post(
    "/admin/plugin-reviews/{version_id}/decision",
    response_model=VersionDecisionResponse,
)
async def decide_plugin_version(
    version_id: UUID,
    body: VersionDecisionRequest,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> VersionDecisionResponse:
    user, _session, _credential = auth
    result = await service.decide_version(
        version_id=version_id,
        caller_user_id=user.id,
        decision=body.decision,
        notes=body.notes,
    )
    return VersionDecisionResponse(
        version_id=str(result.version_id),
        status=result.status,
        decided_by=str(result.decided_by),
        decided_at=result.decided_at,
    )


@router.get("/vendors/{vendor_id}/offerings", response_model=OfferingListResponse)
async def list_offerings(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> OfferingListResponse:
    user, _session, _credential = auth
    items = await service.list_offerings(vendor_id=vendor_id, caller_user_id=user.id)
    return OfferingListResponse(
        offerings=[
            OfferingListItemResponse(
                offering_id=str(item.offering_id),
                product_id=str(item.product_id),
                product_name=item.product_name,
                plan_name=item.plan_name,
                status=item.status,
                price_usd=item.price_usd,
            )
            for item in items
        ]
    )


@router.get("/vendors/{vendor_id}/products", response_model=ProductListResponse)
async def list_products(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductListResponse:
    user, _session, _credential = auth
    items = await service.list_products(vendor_id=vendor_id, caller_user_id=user.id)
    return ProductListResponse(
        products=[
            ProductResponse(
                product_id=str(item.product_id),
                name=item.name,
                status=item.status,
                fulfilment_type=item.fulfilment_type,
                category=item.category,
                content=item.content,
            )
            for item in items
        ]
    )


def _warehouse(item) -> WarehouseResponse:
    return WarehouseResponse(
        warehouse_id=str(item.warehouse_id),
        name=item.name,
        location=item.location,
        capacity=item.capacity,
        units_stored=item.units_stored,
        sku_count=item.sku_count,
    )


def _inventory(item) -> InventoryResponse:
    return InventoryResponse(
        inventory_id=str(item.inventory_id),
        product_id=str(item.product_id),
        product_name=item.product_name,
        warehouse_id=str(item.warehouse_id),
        warehouse_name=item.warehouse_name,
        sku=item.sku,
        available=item.available,
        reserved=item.reserved,
    )


@router.get("/vendors/{vendor_id}/warehouses", response_model=WarehouseListResponse)
async def list_warehouses(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> WarehouseListResponse:
    user, _session, _credential = auth
    rows = await service.list_warehouses(vendor_id=vendor_id, caller_user_id=user.id)
    return WarehouseListResponse(warehouses=[_warehouse(row) for row in rows])


@router.post(
    "/vendors/{vendor_id}/warehouses",
    response_model=WarehouseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse(
    vendor_id: UUID,
    body: WarehouseRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> WarehouseResponse:
    user, _session, _credential = auth
    created = await service.create_warehouse(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        name=body.name,
        location=body.location,
        capacity=body.capacity,
    )
    return _warehouse(created)


@router.patch("/vendors/{vendor_id}/warehouses/{warehouse_id}", response_model=WarehouseResponse)
async def update_warehouse(
    vendor_id: UUID,
    warehouse_id: UUID,
    body: WarehouseRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> WarehouseResponse:
    user, _session, _credential = auth
    updated = await service.update_warehouse(
        vendor_id=vendor_id,
        warehouse_id=warehouse_id,
        caller_user_id=user.id,
        name=body.name,
        location=body.location,
        capacity=body.capacity,
    )
    return _warehouse(updated)


@router.get("/vendors/{vendor_id}/inventory", response_model=InventoryListResponse)
async def list_inventory(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> InventoryListResponse:
    user, _session, _credential = auth
    rows = await service.list_inventory(vendor_id=vendor_id, caller_user_id=user.id)
    return InventoryListResponse(rows=[_inventory(row) for row in rows])


@router.post(
    "/vendors/{vendor_id}/inventory",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_inventory(
    vendor_id: UUID,
    body: InventoryRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> InventoryResponse:
    user, _session, _credential = auth
    created = await service.add_inventory(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        product_id=UUID(body.product_id),
        warehouse_id=UUID(body.warehouse_id),
        sku=body.sku,
        available=body.available,
    )
    return _inventory(created)


@router.patch("/vendors/{vendor_id}/inventory/{inventory_id}", response_model=InventoryResponse)
async def adjust_inventory(
    vendor_id: UUID,
    inventory_id: UUID,
    body: InventoryAdjustRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> InventoryResponse:
    user, _session, _credential = auth
    updated = await service.adjust_inventory(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        inventory_id=inventory_id,
        available=body.available,
    )
    return _inventory(updated)


@router.post(
    "/vendors/{vendor_id}/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    vendor_id: UUID,
    body: CreateProductRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductResponse:
    user, _session, _credential = auth
    result = await service.create_product(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        name=body.name,
        description=body.description,
        plugin_id=UUID(body.plugin_id),
        fulfilment_type=body.fulfilment_type,
        content=body.content,
        category=body.category,
    )
    return ProductResponse(
        product_id=str(result.product_id),
        name=result.name,
        status=result.status,
        fulfilment_type=result.fulfilment_type,
    )


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    body: UpdateProductRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductResponse:
    user, _session, _credential = auth
    item = await service.update_product(
        product_id=product_id,
        caller_user_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        content=body.content,
    )
    return ProductResponse(
        product_id=str(item.product_id),
        name=item.name,
        status=item.status,
        fulfilment_type=item.fulfilment_type,
        category=item.category,
        content=item.content,
    )


@router.post("/products/{product_id}/archive", response_model=ProductResponse)
async def archive_product(
    product_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductResponse:
    user, _session, _credential = auth
    item = await service.archive_product(product_id=product_id, caller_user_id=user.id)
    return ProductResponse(
        product_id=str(item.product_id),
        name=item.name,
        status=item.status,
        fulfilment_type=item.fulfilment_type,
        category=item.category,
    )


@router.post(
    "/products/{product_id}/offerings",
    response_model=OfferingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_offering(
    product_id: UUID,
    body: CreateOfferingRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> OfferingResponse:
    user, _session, _credential = auth
    result = await service.create_offering(
        product_id=product_id,
        caller_user_id=user.id,
        plan_name=body.plan_name,
        billing_period=body.billing_period,
        price_usd=body.price_usd,
        included_transactions=body.included_transactions,
        overage_price_per_1k=body.overage_price_per_1k,
    )
    return OfferingResponse(
        offering_id=str(result.offering_id),
        product_id=str(result.product_id),
        plan_name=result.plan_name,
        status=result.status,
    )


@router.patch("/offerings/{offering_id}", response_model=OfferingListItemResponse)
async def update_offering_price(
    offering_id: UUID,
    body: UpdateOfferingPriceRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> OfferingListItemResponse:
    user, _session, _credential = auth
    item = await service.update_offering_price(
        offering_id=offering_id,
        caller_user_id=user.id,
        price_usd=body.price_usd,
    )
    return OfferingListItemResponse(
        offering_id=str(item.offering_id),
        product_id=str(item.product_id),
        product_name=item.product_name,
        plan_name=item.plan_name,
        status=item.status,
        price_usd=item.price_usd,
    )


@router.post("/offerings/{offering_id}/publish", response_model=OfferingResponse)
async def publish_offering(
    offering_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> OfferingResponse:
    user, _session, _credential = auth
    result = await service.publish_offering(offering_id=offering_id, caller_user_id=user.id)
    return OfferingResponse(
        offering_id=str(result.offering_id),
        product_id=str(result.product_id),
        plan_name=result.plan_name,
        status=result.status,
    )


@router.get("/marketplace/catalog", response_model=CatalogResponse)
async def browse_catalog(
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    category: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    vendor_id: Annotated[UUID | None, Query()] = None,
    verified_only: Annotated[bool, Query()] = False,
    price_min: Annotated[Decimal | None, Query()] = None,
    price_max: Annotated[Decimal | None, Query()] = None,
    sort: Annotated[str, Query()] = "newest",
) -> CatalogResponse:
    cards = await service.catalog(
        category=category,
        q=q,
        vendor_id=vendor_id,
        verified_only=verified_only,
        price_min=price_min,
        price_max=price_max,
        sort=sort,
    )
    results = [_card(item) for item in cards]
    return CatalogResponse(results=results, page=1, total=len(results))


@router.get("/marketplace/home", response_model=HomeResponse)
async def marketplace_home(
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> HomeResponse:
    rails = await service.home()
    categories = sorted({item.category for item in rails["new"] if item.category})
    return HomeResponse(
        categories=categories,
        rails={name: [_card(item) for item in cards] for name, cards in rails.items()},
    )


@router.get("/marketplace/products/{product_id}", response_model=ProductDetailResponse)
async def product_detail(
    product_id: UUID,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductDetailResponse:
    detail = await service.product_detail(product_id=product_id)
    return ProductDetailResponse(
        product_id=str(detail.product_id),
        name=detail.name,
        description=detail.description,
        fulfilment_type=detail.fulfilment_type,
        vendor=detail.vendor_name,
        category=detail.category,
        content=detail.content,
        capabilities=detail.capabilities,
        offerings=[
            OfferingDetailItem(
                offering_id=str(item.offering_id),
                plan_name=item.plan_name,
                price_usd=item.price_usd,
                billing_period=item.billing_period,
                status=item.status,
            )
            for item in detail.offerings
        ],
    )


@router.post(
    "/tenants/{tenant_id}/installations",
    response_model=InstallResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def install_offering(
    tenant_id: UUID,
    body: InstallRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> InstallResponse:
    user, _session, _credential = auth
    result = await service.install(
        tenant_id=tenant_id,
        caller_user_id=user.id,
        caller_principal_id=user.principal_id,
        offering_id=UUID(body.offering_id),
        project_id=UUID(body.project_id) if body.project_id else None,
        accepted_capabilities=body.accepted_capabilities,
        request_id=x_request_id,
    )
    return InstallResponse(
        installation_id=str(result.installation_id),
        offering_id=str(result.offering_id),
        tenant_id=str(result.tenant_id),
        status=result.status,
        entitlement_id=str(result.entitlement_id),
    )


@router.get("/tenants/{tenant_id}/entitlements", response_model=EntitlementsResponse)
async def list_entitlements(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> EntitlementsResponse:
    user, _session, _credential = auth
    items = await service.list_entitlements(
        tenant_id=tenant_id,
        caller_principal_id=user.principal_id,
        request_id=x_request_id,
    )
    return EntitlementsResponse(
        entitlements=[
            EntitlementItem(
                entitlement_id=str(item.entitlement_id),
                offering=item.offering_name,
                status=item.status,
                installation_status=item.installation_status,
                granted_at=item.granted_at,
            )
            for item in items
        ]
    )


@router.get("/vendors/{vendor_id}/installations", response_model=VendorInstallListResponse)
async def vendor_installations(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> VendorInstallListResponse:
    user, _session, _credential = auth
    items = await service.vendor_installs(vendor_id=vendor_id, caller_user_id=user.id)
    return VendorInstallListResponse(
        installations=[
            VendorInstallItem(
                installation_id=str(item.installation_id),
                tenant_name=item.tenant_name,
                product_name=item.product_name,
                fulfilment_type=item.fulfilment_type,
                status=item.status,
                since=item.since,
            )
            for item in items
        ]
    )
