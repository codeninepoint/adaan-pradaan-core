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
from marketplace.application.growth_plugins import GrowthPluginService
from marketplace.application.plugin_service import PluginService
from marketplace.application.vendor_growth_plugins import VendorGrowthPluginService
from platform_ops.application.vendor_communications_service import VendorCommunicationsService
from platform_ops.application.vendor_settlement_service import VendorSettlementService
from marketplace.interface.api.schemas import (
    CatalogFacets,
    CatalogItem,
    CatalogResponse,
    CatalogVendorFacet,
    CreateOfferingRequest,
    CreateProductRequest,
    CreateStandardPluginRequest,
    CreateStandardPluginResponse,
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
    PublicProductReviewItem,
    PublicProductReviewListResponse,
    InventoryAdjustRequest,
    InventoryListResponse,
    InventoryRequest,
    InventoryResponse,
    CityInventoryResponse,
    ServiceCityListResponse,
    ServiceCityResponse,
    AddServiceCityRequest,
    UpdateServiceCityRequest,
    SetCityPincodesRequest,
    ProductCityAssignmentListResponse,
    ProductCityAssignmentResponse,
    SetProductServiceCitiesRequest,
    SubmitProductListingRequest,
    WarehouseListResponse,
    WarehouseRequest,
    WarehouseResponse,
    ClaimResponse,
    RegisterPluginRequest,
    RequestChangesRequest,
    ReviewDetailResponse,
    ReviewStatsResponse,
    RegisterPluginResponse,
    GrowthPluginItem,
    GrowthPluginListResponse,
    GrowthPluginModule,
    GrowthPluginSummary,
    AiDraftRequest,
    AiDraftResponse,
    CreateMarketingCampaignRequest,
    CreatePressReleaseRequest,
    CreateSalesDealRequest,
    PressReleaseItem,
    PublicityBoardResponse,
    UpdatePressReleaseRequest,
    VendorCommunicationHubResponse,
    VendorCommunicationLogItem,
    VendorCommunicationLogsResponse,
    VendorCommunicationSendRequest,
    VendorCommunicationSendResponse,
    VendorCommunicationTemplateItem,
    VendorCommunicationTemplateListResponse,
    VendorCommunicationTemplateRequestBody,
    VendorCommunicationTemplateRequestResponse,
    VendorSettlementBankUpdateRequest,
    VendorSettlementReturnActionRequest,
    CreateSalesFollowUpRequest,
    MarketingBoardResponse,
    MarketingCampaignItem,
    UpdateMarketingCampaignRequest,
    ImportGrowthPluginRequest,
    SalesBoardResponse,
    SalesDealItem,
    SalesFollowUpItem,
    UpdateSalesDealRequest,
    UpdateVendorGrowthPluginRequest,
    VendorGrowthPluginItem,
    VendorGrowthPluginListResponse,
    VendorGrowthModule,
    StandardPluginItem,
    StandardPluginListResponse,
    SubmitVersionRequest,
    SubmitVersionResponse,
    VendorPluginSubmitRequest,
    VendorPluginSubmitResponse,
    VendorStandardPluginItem,
    VendorStandardPluginListResponse,
    SuspendVendorRequest,
    SuspendVendorResponse,
    UpdateGrowthPluginRequest,
    UpdateOfferingPriceRequest,
    UpdateProductRequest,
    UpdateStandardPluginRequest,
    AdminProductItemResponse,
    AdminProductListResponse,
    AdminProductStatsResponse,
    LocationSummaryItemResponse,
    LocationSummaryResponse,
    RejectProductRequest,
    VendorDirectoryItemResponse,
    VendorDirectoryResponse,
    VendorStatsResponse,
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


def get_growth_plugin_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GrowthPluginService:
    return GrowthPluginService(session)


def get_vendor_growth_plugin_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VendorGrowthPluginService:
    return VendorGrowthPluginService(session)


def get_vendor_communications_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VendorCommunicationsService:
    return VendorCommunicationsService(session)


def get_vendor_settlement_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VendorSettlementService:
    return VendorSettlementService(session)


def _vendor_comm_template(item) -> VendorCommunicationTemplateItem:
    return VendorCommunicationTemplateItem(
        id=item.id,
        code=item.code,
        name=item.name,
        channel=item.channel,
        plugin=item.plugin,
        message_type=item.message_type,
        body=item.body,
        approval_status=item.approval_status,
        dlt_reference=item.dlt_reference,
        vendors_using=item.vendors_using,
        messages_sent_month=item.messages_sent_month,
        variable_map=item.variable_map,
        meta=item.meta,
        submitted_at=item.submitted_at,
    )


def _vendor_comm_log(item) -> VendorCommunicationLogItem:
    return VendorCommunicationLogItem(
        id=item.id,
        occurred_at=item.occurred_at,
        channel=item.channel,
        template_code=item.template_code,
        template_name=item.template_name,
        audience=item.audience,
        contact_name=item.contact_name,
        sent=item.sent,
        delivered=item.delivered,
        read_count=item.read_count,
        replied_count=item.replied_count,
        status=item.status,
    )


def _product(item) -> ProductResponse:
    return ProductResponse(
        product_id=str(item.product_id),
        name=item.name,
        status=item.status,
        fulfilment_type=item.fulfilment_type,
        category=item.category,
        content=item.content,
        pa_status=item.pa_status,
        pa_reject_reason=item.pa_reject_reason,
        mrp_inr=item.mrp_inr,
        image_count=item.image_count,
        cities=item.cities,
        stock_status=item.stock_status,
        visibility=item.visibility,
        brand=item.brand,
        net_weight=item.net_weight,
        sku=item.sku,
        image_urls=item.image_urls,
        currency=getattr(item, "currency", None) or "INR",
    )


def _service_city(item) -> ServiceCityResponse:
    return ServiceCityResponse(
        city_id=str(item.city_id),
        city_name=item.city_name,
        warehouse_id=str(item.warehouse_id),
        pincodes=item.pincodes,
        currency=item.currency,
        resolved_currency=getattr(item, "resolved_currency", None) or item.currency or "INR",
    )


def _product_city_assignment(item) -> ProductCityAssignmentResponse:
    return ProductCityAssignmentResponse(
        product_id=str(item.product_id),
        product_name=item.product_name,
        category=item.category,
        cities=item.cities,
        status=item.status,
    )


def _card(item) -> CatalogItem:
    amount = float(getattr(item, "price", None) or item.price_usd)
    currency = getattr(item, "currency", None) or "INR"
    return CatalogItem(
        offering_id=str(item.offering_id),
        product_id=str(item.product_id),
        product_name=item.product_name,
        vendor=item.vendor_name,
        vendor_id=str(item.vendor_id),
        plan_name=item.plan_name,
        price=amount,
        currency=currency,
        price_usd=amount,
        billing_period=item.billing_period,
        fulfilment_type=item.fulfilment_type,
        category=item.category,
        avg_rating=float(getattr(item, "avg_rating", 0) or 0),
        review_count=int(getattr(item, "review_count", 0) or 0),
        in_stock=bool(getattr(item, "in_stock", True)),
    )


def _offering_list_item(item) -> OfferingListItemResponse:
    amount = float(getattr(item, "price", None) or item.price_usd)
    currency = getattr(item, "currency", None) or "INR"
    return OfferingListItemResponse(
        offering_id=str(item.offering_id),
        product_id=str(item.product_id),
        product_name=item.product_name,
        plan_name=item.plan_name,
        status=item.status,
        price=amount,
        currency=currency,
        price_usd=amount,
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
                category=item.category,
                short_description=item.short_description,
                review_notes=item.review_notes,
                submitted_at=item.submitted_at,
                changelog=item.changelog,
            )
            for item in items
        ]
    )


def _vendor_std_plugin(item) -> VendorStandardPluginItem:
    return VendorStandardPluginItem(
        plugin_id=str(item.plugin_id),
        name=item.name,
        slug=item.slug,
        category=item.category,
        short_description=item.short_description,
        version=item.version,
        tags=item.tags,
        vendor_count=item.vendor_count,
        activation_status=item.activation_status,
    )


@router.get(
    "/vendors/{vendor_id}/standard-plugins",
    response_model=VendorStandardPluginListResponse,
)
async def list_vendor_standard_plugins(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
    q: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
) -> VendorStandardPluginListResponse:
    user, _session, _credential = auth
    items = await service.list_vendor_standard_plugins(
        vendor_id=vendor_id, caller_user_id=user.id, q=q, category=category
    )
    return VendorStandardPluginListResponse(items=[_vendor_std_plugin(item) for item in items])


@router.post(
    "/vendors/{vendor_id}/standard-plugins/{plugin_id}/activate",
    response_model=VendorStandardPluginItem,
)
async def activate_vendor_standard_plugin(
    vendor_id: UUID,
    plugin_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> VendorStandardPluginItem:
    user, _session, _credential = auth
    item = await service.activate_standard_plugin(
        vendor_id=vendor_id, caller_user_id=user.id, plugin_id=plugin_id
    )
    return _vendor_std_plugin(item)


@router.post(
    "/vendors/{vendor_id}/standard-plugins/{plugin_id}/deactivate",
    response_model=VendorStandardPluginItem,
)
async def deactivate_vendor_standard_plugin(
    vendor_id: UUID,
    plugin_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> VendorStandardPluginItem:
    user, _session, _credential = auth
    item = await service.deactivate_standard_plugin(
        vendor_id=vendor_id, caller_user_id=user.id, plugin_id=plugin_id
    )
    return _vendor_std_plugin(item)


@router.post(
    "/vendors/{vendor_id}/plugins/submit",
    response_model=VendorPluginSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_vendor_plugin_bundle(
    vendor_id: UUID,
    body: VendorPluginSubmitRequest,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> VendorPluginSubmitResponse:
    user, _session, _credential = auth
    result = await service.submit_plugin_bundle(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        name=body.name,
        version=body.version,
        category=body.category,
        description=body.description,
        artifact_url=body.artifact_url,
        sbom_url=body.sbom_url,
        plugin_id=UUID(body.plugin_id) if body.plugin_id else None,
        slug=body.slug,
    )
    return VendorPluginSubmitResponse(
        plugin_id=str(result.plugin_id),
        version_id=str(result.version_id),
        slug=result.slug,
        version=result.version,
        status=result.status,
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
                review_notes=item.review_notes,
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
    claimed: Annotated[bool | None, Query()] = None,
    risk: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> PendingReviewsResponse:
    user, _session, _credential = auth
    items = await service.list_pending_reviews(
        caller_user_id=user.id, status=status, claimed=claimed, risk=risk, q=q
    )
    return PendingReviewsResponse(
        items=[
            PendingReviewItem(
                version_id=str(item.version_id),
                plugin_id=str(item.plugin_id),
                plugin_slug=item.plugin_slug,
                version=item.version,
                status=item.status,
                vendor_id=str(item.vendor_id) if item.vendor_id else None,
                vendor_name=item.vendor_name,
                claimed_by=str(item.claimed_by) if item.claimed_by else None,
                submitted_at=item.submitted_at,
                risk_level=item.risk_level,
                decided_by=str(item.decided_by) if item.decided_by else None,
                decided_at=item.decided_at,
                review_notes=item.review_notes,
            )
            for item in items
        ]
    )


@router.get("/admin/plugin-reviews/stats", response_model=ReviewStatsResponse)
async def plugin_review_stats(
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> ReviewStatsResponse:
    user, _session, _credential = auth
    stats = await service.review_stats(caller_user_id=user.id)
    return ReviewStatsResponse(
        pending=stats.pending,
        in_review=stats.in_review,
        published=stats.published,
        rejected=stats.rejected,
        standard_plugins=stats.standard_plugins,
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
        risk_level=detail.risk_level,
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
    q: Annotated[str | None, Query()] = None,
) -> VendorDirectoryResponse:
    user, _session, _credential = auth
    items = await service.list_vendors(caller_user_id=user.id, status=status, q=q)
    return VendorDirectoryResponse(
        results=[
            VendorDirectoryItemResponse(
                vendor_id=str(item.vendor_id),
                legal_name=item.legal_name,
                status=item.status,
                product_count=item.product_count,
                active_installs=item.active_installs,
                plugin_count=item.plugin_count,
                warehouse_count=item.warehouse_count,
                kyc_status=item.kyc_status,
                gmv_mtd=item.gmv_mtd,
            )
            for item in items
        ]
    )


@router.get("/admin/vendors/stats", response_model=VendorStatsResponse)
async def admin_vendor_stats(
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> VendorStatsResponse:
    user, _session, _credential = auth
    stats = await service.vendor_stats(caller_user_id=user.id)
    return VendorStatsResponse(
        active=stats.active,
        pending_verification=stats.pending_verification,
        suspended=stats.suspended,
        total_plugins=stats.total_plugins,
    )


@router.post("/admin/vendors/{vendor_id}/reinstate", response_model=SuspendVendorResponse)
async def reinstate_vendor(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> SuspendVendorResponse:
    user, _session, _credential = auth
    result = await service.reinstate_vendor(vendor_id=vendor_id, caller_user_id=user.id)
    return SuspendVendorResponse(
        vendor_id=str(result.vendor_id),
        status=result.status,
        offerings_unpublished=result.offerings_unpublished,
    )


def _admin_product(item) -> AdminProductItemResponse:
    return AdminProductItemResponse(
        product_id=str(item.product_id),
        name=item.name,
        vendor_id=str(item.vendor_id),
        vendor_name=item.vendor_name,
        category=item.category,
        status=item.status,
        pa_status=item.pa_status,
        pa_reject_reason=item.pa_reject_reason,
        fulfilment_type=item.fulfilment_type,
        submitted_at=item.submitted_at,
    )


@router.get("/admin/products", response_model=AdminProductListResponse)
async def list_admin_products(
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    pa_status: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    vendor_id: Annotated[UUID | None, Query()] = None,
) -> AdminProductListResponse:
    user, _session, _credential = auth
    items = await service.list_admin_products(
        caller_user_id=user.id, pa_status=pa_status, q=q, vendor_id=vendor_id
    )
    return AdminProductListResponse(items=[_admin_product(item) for item in items])


@router.get("/admin/products/stats", response_model=AdminProductStatsResponse)
async def admin_product_stats(
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> AdminProductStatsResponse:
    user, _session, _credential = auth
    stats = await service.product_stats(caller_user_id=user.id)
    return AdminProductStatsResponse(
        pending_review=stats.pending_review,
        live=stats.live,
        rejected=stats.rejected,
        not_submitted=stats.not_submitted,
        warehouse_locations=stats.warehouse_locations,
    )


@router.post("/admin/products/{product_id}/approve", response_model=AdminProductItemResponse)
async def approve_admin_product(
    product_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> AdminProductItemResponse:
    user, _session, _credential = auth
    item = await service.approve_product(product_id=product_id, caller_user_id=user.id)
    return _admin_product(item)


@router.post("/admin/products/{product_id}/reject", response_model=AdminProductItemResponse)
async def reject_admin_product(
    product_id: UUID,
    body: RejectProductRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> AdminProductItemResponse:
    user, _session, _credential = auth
    item = await service.reject_product(
        product_id=product_id, caller_user_id=user.id, reason=body.reason
    )
    return _admin_product(item)


@router.get("/admin/locations/summary", response_model=LocationSummaryResponse)
async def admin_locations_summary(
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> LocationSummaryResponse:
    user, _session, _credential = auth
    items = await service.locations_summary(caller_user_id=user.id)
    return LocationSummaryResponse(
        items=[
            LocationSummaryItemResponse(
                location=item.location,
                warehouse_count=item.warehouse_count,
                vendor_count=item.vendor_count,
                units_stored=item.units_stored,
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


def _standard_plugin_item(view) -> StandardPluginItem:
    return StandardPluginItem(
        plugin_id=str(view.plugin_id) if view.plugin_id else None,
        category=view.category,
        name=view.name,
        slug=view.slug,
        status=view.status,
        short_description=view.short_description,
        version=view.version,
        requirements=view.requirements,
        updated_at=view.updated_at,
    )


@router.get("/admin/standard-plugins", response_model=StandardPluginListResponse)
async def list_standard_plugins(
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> StandardPluginListResponse:
    user, _session, _credential = auth
    items = await service.list_standard_plugins(caller_user_id=user.id)
    return StandardPluginListResponse(items=[_standard_plugin_item(item) for item in items])


@router.post(
    "/admin/standard-plugins",
    response_model=CreateStandardPluginResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_standard_plugin(
    body: CreateStandardPluginRequest,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> CreateStandardPluginResponse:
    user, _session, _credential = auth
    result = await service.create_standard_plugin(
        caller_user_id=user.id,
        name=body.name,
        slug=body.slug,
        category=body.category,
        short_description=body.short_description,
        version=body.version,
        artifact_url=body.artifact_url,
        changelog=body.changelog,
        requirements=body.requirements,
        publish=body.publish,
    )
    return CreateStandardPluginResponse(
        plugin_id=str(result.plugin_id),
        slug=result.slug,
        category=result.category,
        status=result.status,
        version=result.version,
    )


@router.patch("/admin/standard-plugins/{plugin_id}", response_model=StandardPluginItem)
async def update_standard_plugin(
    plugin_id: UUID,
    body: UpdateStandardPluginRequest,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> StandardPluginItem:
    user, _session, _credential = auth
    view = await service.update_standard_plugin(
        plugin_id=plugin_id,
        caller_user_id=user.id,
        name=body.name,
        short_description=body.short_description,
        requirements=body.requirements,
    )
    return _standard_plugin_item(view)


@router.post("/admin/standard-plugins/{plugin_id}/publish", response_model=StandardPluginItem)
async def publish_standard_plugin(
    plugin_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> StandardPluginItem:
    user, _session, _credential = auth
    view = await service.set_standard_plugin_status(
        plugin_id=plugin_id, caller_user_id=user.id, status="active"
    )
    return _standard_plugin_item(view)


@router.post("/admin/standard-plugins/{plugin_id}/unpublish", response_model=StandardPluginItem)
async def unpublish_standard_plugin(
    plugin_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> StandardPluginItem:
    user, _session, _credential = auth
    view = await service.set_standard_plugin_status(
        plugin_id=plugin_id, caller_user_id=user.id, status="unpublished"
    )
    return _standard_plugin_item(view)


@router.post("/admin/standard-plugins/{plugin_id}/deprecate", response_model=StandardPluginItem)
async def deprecate_standard_plugin(
    plugin_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> StandardPluginItem:
    user, _session, _credential = auth
    view = await service.set_standard_plugin_status(
        plugin_id=plugin_id, caller_user_id=user.id, status="deprecated"
    )
    return _standard_plugin_item(view)


@router.delete("/admin/standard-plugins/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_standard_plugin(
    plugin_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PluginService, Depends(get_plugin_service)],
) -> None:
    user, _session, _credential = auth
    await service.delete_standard_plugin(plugin_id=plugin_id, caller_user_id=user.id)


def _growth_plugin_item(view) -> GrowthPluginItem:
    return GrowthPluginItem(
        key=view.key,
        name=view.name,
        description=view.description,
        group_label=view.group_label,
        lifecycle=view.lifecycle,
        enabled=view.enabled,
        modules=[GrowthPluginModule(**module) for module in view.modules],
        config=view.config,
        stats=view.stats,
        guarantees=view.guarantees,
        updated_at=view.updated_at,
    )


@router.get("/admin/growth-plugins", response_model=GrowthPluginListResponse)
async def list_growth_plugins(
    auth: CurrentAuthDep,
    service: Annotated[GrowthPluginService, Depends(get_growth_plugin_service)],
) -> GrowthPluginListResponse:
    user, _session, _credential = auth
    items, summary = await service.list_plugins(caller_user_id=user.id)
    return GrowthPluginListResponse(
        items=[_growth_plugin_item(item) for item in items],
        summary=GrowthPluginSummary(
            total_plugins=summary.total_plugins,
            total_modules=summary.total_modules,
            enabled_plugins=summary.enabled_plugins,
            vendors_using=summary.vendors_using,
        ),
    )


@router.patch("/admin/growth-plugins/{plugin_key}", response_model=GrowthPluginItem)
async def update_growth_plugin(
    plugin_key: str,
    body: UpdateGrowthPluginRequest,
    auth: CurrentAuthDep,
    service: Annotated[GrowthPluginService, Depends(get_growth_plugin_service)],
) -> GrowthPluginItem:
    user, _session, _credential = auth
    view = await service.update_plugin(
        plugin_key=plugin_key,
        caller_user_id=user.id,
        enabled=body.enabled,
        modules=[module.model_dump() for module in body.modules] if body.modules is not None else None,
        config=body.config,
    )
    return _growth_plugin_item(view)


def _vendor_growth_item(view) -> VendorGrowthPluginItem:
    return VendorGrowthPluginItem(
        key=view.key,
        name=view.name,
        description=view.description,
        group_label=view.group_label,
        lifecycle=view.lifecycle,
        platform_enabled=view.platform_enabled,
        rating=view.rating,
        price_label=view.price_label,
        vendors_using=view.vendors_using,
        total_vendors=view.total_vendors,
        guarantees=view.guarantees,
        modules=[GrowthPluginModule(**module) for module in view.modules],
        installation_status=view.installation_status,
        vendor_modules=[VendorGrowthModule(**module) for module in view.vendor_modules],
        connection=view.connection,
        imported_at=view.imported_at,
        updated_at=view.updated_at,
    )


@router.get(
    "/vendors/{vendor_id}/growth-plugins", response_model=VendorGrowthPluginListResponse
)
async def list_vendor_growth_plugins(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> VendorGrowthPluginListResponse:
    user, _session, _credential = auth
    items = await service.list_for_vendor(vendor_id=vendor_id, caller_user_id=user.id)
    return VendorGrowthPluginListResponse(items=[_vendor_growth_item(item) for item in items])


@router.post(
    "/vendors/{vendor_id}/growth-plugins/{plugin_key}/import",
    response_model=VendorGrowthPluginItem,
)
async def import_vendor_growth_plugin(
    vendor_id: UUID,
    plugin_key: str,
    body: ImportGrowthPluginRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> VendorGrowthPluginItem:
    user, _session, _credential = auth
    view = await service.import_plugin(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        plugin_key=plugin_key,
        consents=body.consents,
        connection=body.connection,
        modules=[module.model_dump() for module in body.modules] if body.modules else None,
    )
    return _vendor_growth_item(view)


@router.patch(
    "/vendors/{vendor_id}/growth-plugins/{plugin_key}",
    response_model=VendorGrowthPluginItem,
)
async def update_vendor_growth_plugin(
    vendor_id: UUID,
    plugin_key: str,
    body: UpdateVendorGrowthPluginRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> VendorGrowthPluginItem:
    user, _session, _credential = auth
    view = await service.update_installation(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        plugin_key=plugin_key,
        modules=[module.model_dump() for module in body.modules] if body.modules is not None else None,
        status=body.status,
        connection=body.connection,
    )
    return _vendor_growth_item(view)


@router.get(
    "/vendors/{vendor_id}/growth-plugins/sales-pipeline/board",
    response_model=SalesBoardResponse,
)
async def vendor_sales_pipeline_board(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> SalesBoardResponse:
    user, _session, _credential = auth
    board = await service.sales_board(vendor_id=vendor_id, caller_user_id=user.id)
    return SalesBoardResponse(
        stages=board.stages,
        deals=[SalesDealItem(**deal) for deal in board.deals],
        followups=[SalesFollowUpItem(**item) for item in board.followups],
        stats=board.stats,
        active_modules=board.active_modules,
        updated_at=board.updated_at,
    )


@router.post(
    "/vendors/{vendor_id}/growth-plugins/sales-pipeline/deals",
    response_model=SalesDealItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_vendor_sales_deal(
    vendor_id: UUID,
    body: CreateSalesDealRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> SalesDealItem:
    user, _session, _credential = auth
    deal = await service.create_deal(
        vendor_id=vendor_id, caller_user_id=user.id, body=body.model_dump()
    )
    return SalesDealItem(**deal)


@router.patch(
    "/vendors/{vendor_id}/growth-plugins/sales-pipeline/deals/{deal_id}",
    response_model=SalesDealItem,
)
async def update_vendor_sales_deal(
    vendor_id: UUID,
    deal_id: UUID,
    body: UpdateSalesDealRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> SalesDealItem:
    user, _session, _credential = auth
    deal = await service.update_deal(
        vendor_id=vendor_id, caller_user_id=user.id, deal_id=deal_id, body=body.model_dump()
    )
    return SalesDealItem(**deal)


@router.post(
    "/vendors/{vendor_id}/growth-plugins/sales-pipeline/followups",
    response_model=SalesFollowUpItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_vendor_sales_followup(
    vendor_id: UUID,
    body: CreateSalesFollowUpRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> SalesFollowUpItem:
    user, _session, _credential = auth
    item = await service.create_followup(
        vendor_id=vendor_id, caller_user_id=user.id, body=body.model_dump()
    )
    return SalesFollowUpItem(**item)


@router.post(
    "/vendors/{vendor_id}/growth-plugins/sales-pipeline/followups/{followup_id}/complete",
    response_model=SalesFollowUpItem,
)
async def complete_vendor_sales_followup(
    vendor_id: UUID,
    followup_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> SalesFollowUpItem:
    user, _session, _credential = auth
    item = await service.complete_followup(
        vendor_id=vendor_id, caller_user_id=user.id, followup_id=followup_id
    )
    return SalesFollowUpItem(**item)


@router.get(
    "/vendors/{vendor_id}/growth-plugins/digital-marketing/board",
    response_model=MarketingBoardResponse,
)
async def vendor_digital_marketing_board(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> MarketingBoardResponse:
    user, _session, _credential = auth
    board = await service.marketing_board(vendor_id=vendor_id, caller_user_id=user.id)
    return MarketingBoardResponse(
        campaigns=[MarketingCampaignItem(**c) for c in board.campaigns],
        stats=board.stats,
        race_funnel=board.race_funnel,
        active_modules=board.active_modules,
        daily_spend_cap_inr=board.daily_spend_cap_inr,
        updated_at=board.updated_at,
    )


@router.post(
    "/vendors/{vendor_id}/growth-plugins/digital-marketing/campaigns",
    response_model=MarketingCampaignItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_vendor_marketing_campaign(
    vendor_id: UUID,
    body: CreateMarketingCampaignRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> MarketingCampaignItem:
    user, _session, _credential = auth
    campaign = await service.create_campaign(
        vendor_id=vendor_id, caller_user_id=user.id, body=body.model_dump()
    )
    return MarketingCampaignItem(**campaign)


@router.patch(
    "/vendors/{vendor_id}/growth-plugins/digital-marketing/campaigns/{campaign_id}",
    response_model=MarketingCampaignItem,
)
async def update_vendor_marketing_campaign(
    vendor_id: UUID,
    campaign_id: UUID,
    body: UpdateMarketingCampaignRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> MarketingCampaignItem:
    user, _session, _credential = auth
    campaign = await service.update_campaign(
        vendor_id=vendor_id, caller_user_id=user.id, campaign_id=campaign_id, body=body.model_dump()
    )
    return MarketingCampaignItem(**campaign)


@router.get(
    "/vendors/{vendor_id}/growth-plugins/publicity/board",
    response_model=PublicityBoardResponse,
)
async def vendor_publicity_board(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> PublicityBoardResponse:
    user, _session, _credential = auth
    board = await service.publicity_board(vendor_id=vendor_id, caller_user_id=user.id)
    return PublicityBoardResponse(
        releases=[PressReleaseItem(**r) for r in board.releases],
        stats=board.stats,
        templates=board.templates,
        distributions=board.distributions,
        active_modules=board.active_modules,
        ai_tokens_per_month=board.ai_tokens_per_month,
        media_kit_format=board.media_kit_format,
        updated_at=board.updated_at,
    )


@router.post(
    "/vendors/{vendor_id}/growth-plugins/publicity/releases",
    response_model=PressReleaseItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_vendor_press_release(
    vendor_id: UUID,
    body: CreatePressReleaseRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> PressReleaseItem:
    user, _session, _credential = auth
    release = await service.create_release(
        vendor_id=vendor_id, caller_user_id=user.id, body=body.model_dump()
    )
    return PressReleaseItem(**release)


@router.patch(
    "/vendors/{vendor_id}/growth-plugins/publicity/releases/{release_id}",
    response_model=PressReleaseItem,
)
async def update_vendor_press_release(
    vendor_id: UUID,
    release_id: UUID,
    body: UpdatePressReleaseRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> PressReleaseItem:
    user, _session, _credential = auth
    release = await service.update_release(
        vendor_id=vendor_id, caller_user_id=user.id, release_id=release_id, body=body.model_dump()
    )
    return PressReleaseItem(**release)


@router.post(
    "/vendors/{vendor_id}/growth-plugins/publicity/ai-draft",
    response_model=AiDraftResponse,
)
async def vendor_publicity_ai_draft(
    vendor_id: UUID,
    body: AiDraftRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorGrowthPluginService, Depends(get_vendor_growth_plugin_service)],
) -> AiDraftResponse:
    user, _session, _credential = auth
    draft = await service.ai_draft(vendor_id=vendor_id, caller_user_id=user.id, body=body.model_dump())
    return AiDraftResponse(**draft)


@router.get(
    "/vendors/{vendor_id}/communications/hub",
    response_model=VendorCommunicationHubResponse,
)
async def vendor_communications_hub(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorCommunicationsService, Depends(get_vendor_communications_service)],
) -> VendorCommunicationHubResponse:
    user, _session, _credential = auth
    summary, recent = await service.hub(vendor_id=vendor_id, caller_user_id=user.id)
    return VendorCommunicationHubResponse(
        summary={
            "sent_this_month": summary.sent_this_month,
            "delivery_rate": summary.delivery_rate,
            "active_campaigns": summary.active_campaigns,
            "templates_available": summary.templates_available,
            "by_channel": summary.by_channel,
        },
        recent=[_vendor_comm_log(item) for item in recent],
    )


@router.get(
    "/vendors/{vendor_id}/communications/templates",
    response_model=VendorCommunicationTemplateListResponse,
)
async def vendor_communication_templates(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorCommunicationsService, Depends(get_vendor_communications_service)],
    channel: Annotated[str | None, Query()] = None,
) -> VendorCommunicationTemplateListResponse:
    user, _session, _credential = auth
    items = await service.list_templates(
        vendor_id=vendor_id, caller_user_id=user.id, channel=channel
    )
    return VendorCommunicationTemplateListResponse(
        items=[_vendor_comm_template(item) for item in items]
    )


@router.post(
    "/vendors/{vendor_id}/communications/send",
    response_model=VendorCommunicationSendResponse,
)
async def vendor_communication_send(
    vendor_id: UUID,
    body: VendorCommunicationSendRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorCommunicationsService, Depends(get_vendor_communications_service)],
) -> VendorCommunicationSendResponse:
    user, _session, _credential = auth
    result = await service.send(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        template_id=UUID(body.template_id),
        audience=body.audience,
        variables=body.variables,
        contact_name=body.contact_name,
        schedule=body.schedule,
    )
    return VendorCommunicationSendResponse(
        log_id=result.log_id,
        status=result.status,
        sent=result.sent,
        delivered=result.delivered,
        estimated_cost_inr=result.estimated_cost_inr,
    )


@router.get(
    "/vendors/{vendor_id}/communications/logs",
    response_model=VendorCommunicationLogsResponse,
)
async def vendor_communication_logs(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorCommunicationsService, Depends(get_vendor_communications_service)],
) -> VendorCommunicationLogsResponse:
    user, _session, _credential = auth
    data = await service.logs(vendor_id=vendor_id, caller_user_id=user.id)
    return VendorCommunicationLogsResponse(
        items=[_vendor_comm_log(item) for item in data["items"]],
        campaign=data.get("campaign"),
        compliance=data.get("compliance") or {},
    )


@router.post(
    "/vendors/{vendor_id}/communications/template-requests",
    response_model=VendorCommunicationTemplateRequestResponse,
    status_code=201,
)
async def vendor_communication_template_request(
    vendor_id: UUID,
    body: VendorCommunicationTemplateRequestBody,
    auth: CurrentAuthDep,
    service: Annotated[VendorCommunicationsService, Depends(get_vendor_communications_service)],
) -> VendorCommunicationTemplateRequestResponse:
    user, _session, _credential = auth
    result = await service.request_template(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        name=body.name,
        channel=body.channel,
        notes=body.notes,
    )
    return VendorCommunicationTemplateRequestResponse(**result)


@router.get("/vendors/{vendor_id}/settlement/earnings")
async def vendor_settlement_earnings(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorSettlementService, Depends(get_vendor_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.earnings(vendor_id=vendor_id, caller_user_id=user.id)


@router.get("/vendors/{vendor_id}/settlement/returns")
async def vendor_settlement_returns(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorSettlementService, Depends(get_vendor_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.returns(vendor_id=vendor_id, caller_user_id=user.id)


@router.post("/vendors/{vendor_id}/settlement/returns/{return_id}/respond")
async def vendor_settlement_respond_return(
    vendor_id: UUID,
    return_id: UUID,
    body: VendorSettlementReturnActionRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorSettlementService, Depends(get_vendor_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.respond_return(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        return_id=return_id,
        action=body.action,
        reason=body.reason,
    )


@router.get("/vendors/{vendor_id}/settlement/orders")
async def vendor_settlement_orders(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorSettlementService, Depends(get_vendor_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.orders(vendor_id=vendor_id, caller_user_id=user.id)


@router.get("/vendors/{vendor_id}/settlement/history")
async def vendor_settlement_history(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorSettlementService, Depends(get_vendor_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.history(vendor_id=vendor_id, caller_user_id=user.id)


@router.get("/vendors/{vendor_id}/settlement/chat")
async def vendor_settlement_chat(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorSettlementService, Depends(get_vendor_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.chat(vendor_id=vendor_id, caller_user_id=user.id)


@router.get("/vendors/{vendor_id}/settlement/bank")
async def vendor_settlement_bank(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorSettlementService, Depends(get_vendor_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.bank(vendor_id=vendor_id, caller_user_id=user.id)


@router.patch("/vendors/{vendor_id}/settlement/bank")
async def vendor_settlement_update_bank(
    vendor_id: UUID,
    body: VendorSettlementBankUpdateRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorSettlementService, Depends(get_vendor_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.update_bank(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        bank_name=body.bank_name,
        account_number=body.account_number,
        ifsc=body.ifsc,
        branch=body.branch,
    )


@router.get("/vendors/{vendor_id}/offerings", response_model=OfferingListResponse)
async def list_offerings(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> OfferingListResponse:
    user, _session, _credential = auth
    items = await service.list_offerings(vendor_id=vendor_id, caller_user_id=user.id)
    return OfferingListResponse(offerings=[_offering_list_item(item) for item in items])


@router.get("/vendors/{vendor_id}/products", response_model=ProductListResponse)
async def list_products(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductListResponse:
    user, _session, _credential = auth
    items = await service.list_products(vendor_id=vendor_id, caller_user_id=user.id)
    return ProductListResponse(products=[_product(item) for item in items])


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
        reorder_threshold=item.reorder_threshold,
        city_name=item.city_name,
        status=item.status,
    )


def _city_inventory(item) -> CityInventoryResponse:
    return CityInventoryResponse(
        inventory_id=str(item.inventory_id),
        product_id=str(item.product_id),
        product_name=item.product_name,
        city_id=str(item.city_id),
        city_name=item.city_name,
        sku=item.sku,
        available=item.available,
        reserved=item.reserved,
        reorder_threshold=item.reorder_threshold,
        status=item.status,
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
    view: Annotated[str | None, Query()] = None,
) -> InventoryListResponse:
    user, _session, _credential = auth
    rows = await service.list_inventory(
        vendor_id=vendor_id, caller_user_id=user.id, view=view
    )
    if view == "by_city":
        return InventoryListResponse(city_rows=[_city_inventory(row) for row in rows])
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
        reorder_threshold=body.reorder_threshold,
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
        reorder_threshold=body.reorder_threshold,
    )
    return _inventory(updated)


@router.get("/vendors/{vendor_id}/service-cities", response_model=ServiceCityListResponse)
async def list_service_cities(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ServiceCityListResponse:
    user, _session, _credential = auth
    cities = await service.list_service_cities(vendor_id=vendor_id, caller_user_id=user.id)
    return ServiceCityListResponse(cities=[_service_city(city) for city in cities])


@router.post(
    "/vendors/{vendor_id}/service-cities",
    response_model=ServiceCityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_service_city(
    vendor_id: UUID,
    body: AddServiceCityRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ServiceCityResponse:
    user, _session, _credential = auth
    created = await service.add_service_city(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        city_name=body.city_name,
        currency=body.currency,
    )
    return _service_city(created)


@router.patch(
    "/vendors/{vendor_id}/service-cities/{city_id}",
    response_model=ServiceCityResponse,
)
async def update_service_city(
    vendor_id: UUID,
    city_id: UUID,
    body: UpdateServiceCityRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ServiceCityResponse:
    user, _session, _credential = auth
    updated = await service.update_service_city(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        city_id=city_id,
        currency=body.currency,
    )
    return _service_city(updated)


@router.delete(
    "/vendors/{vendor_id}/service-cities/{city_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_service_city(
    vendor_id: UUID,
    city_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> None:
    user, _session, _credential = auth
    await service.delete_service_city(
        vendor_id=vendor_id, caller_user_id=user.id, city_id=city_id
    )


@router.put(
    "/vendors/{vendor_id}/service-cities/{city_id}/pincodes",
    response_model=ServiceCityResponse,
)
async def set_city_pincodes(
    vendor_id: UUID,
    city_id: UUID,
    body: SetCityPincodesRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ServiceCityResponse:
    user, _session, _credential = auth
    updated = await service.set_city_pincodes(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        city_id=city_id,
        pincodes=body.pincodes,
    )
    return _service_city(updated)


@router.get(
    "/vendors/{vendor_id}/product-city-assignments",
    response_model=ProductCityAssignmentListResponse,
)
async def list_product_city_assignments(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductCityAssignmentListResponse:
    user, _session, _credential = auth
    items = await service.list_product_city_assignments(
        vendor_id=vendor_id, caller_user_id=user.id
    )
    return ProductCityAssignmentListResponse(
        items=[_product_city_assignment(item) for item in items]
    )


@router.put(
    "/products/{product_id}/service-cities",
    response_model=ProductCityAssignmentResponse,
)
async def set_product_service_cities(
    product_id: UUID,
    body: SetProductServiceCitiesRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductCityAssignmentResponse:
    user, _session, _credential = auth
    item = await service.set_product_service_cities(
        product_id=product_id,
        caller_user_id=user.id,
        city_ids=[UUID(city_id) for city_id in body.city_ids],
    )
    return _product_city_assignment(item)


@router.post(
    "/vendors/{vendor_id}/products/submit",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_product_listing(
    vendor_id: UUID,
    body: SubmitProductListingRequest,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductResponse:
    user, _session, _credential = auth
    item = await service.submit_product_listing(
        vendor_id=vendor_id,
        caller_user_id=user.id,
        product_id=UUID(body.product_id) if body.product_id else None,
        name=body.name,
        description=body.description,
        category=body.category,
        sku=body.sku,
        mrp_inr=body.mrp_inr,
        currency=body.currency,
        net_weight=body.net_weight,
        brand=body.brand,
        image_urls=body.image_urls,
        authenticity_attested=body.authenticity_attested,
        city_ids=[UUID(city_id) for city_id in body.city_ids],
        fulfilment_type=body.fulfilment_type,
    )
    return _product(item)


@router.post("/products/{product_id}/resubmit", response_model=ProductResponse)
async def resubmit_product(
    product_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductResponse:
    user, _session, _credential = auth
    item = await service.resubmit_product(product_id=product_id, caller_user_id=user.id)
    return _product(item)


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
        plugin_id=UUID(body.plugin_id) if body.plugin_id else None,
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
    return _product(item)


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
        currency=body.currency,
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
        currency=body.currency,
    )
    return _offering_list_item(item)


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
    vendor_ids: Annotated[str | None, Query()] = None,
    verified_only: Annotated[bool, Query()] = False,
    price_min: Annotated[Decimal | None, Query()] = None,
    price_max: Annotated[Decimal | None, Query()] = None,
    sort: Annotated[str, Query()] = "newest",
    pincode: Annotated[str | None, Query()] = None,
    in_stock: Annotated[bool, Query()] = False,
    fulfilment: Annotated[str | None, Query()] = None,
) -> CatalogResponse:
    parsed_vendor_ids: list[UUID] = []
    if vendor_ids:
        for part in vendor_ids.split(","):
            part = part.strip()
            if part:
                parsed_vendor_ids.append(UUID(part))
    result = await service.catalog(
        category=category,
        q=q,
        vendor_id=vendor_id,
        vendor_ids=parsed_vendor_ids or None,
        verified_only=verified_only,
        price_min=price_min,
        price_max=price_max,
        sort=sort,
        pincode=pincode,
        in_stock=in_stock,
        fulfilment=fulfilment,
    )
    results = [_card(item) for item in result.cards]
    return CatalogResponse(
        results=results,
        page=1,
        total=len(results),
        facets=CatalogFacets(
            vendors=[
                CatalogVendorFacet(vendor_id=str(v.vendor_id), name=v.name)
                for v in result.vendors
            ]
        ),
    )


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


@router.get(
    "/marketplace/products/{product_id}/reviews",
    response_model=PublicProductReviewListResponse,
)
async def product_public_reviews(
    product_id: UUID,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> PublicProductReviewListResponse:
    result = await service.list_public_reviews(product_id=product_id)
    return PublicProductReviewListResponse(
        reviews=[
            PublicProductReviewItem(
                rating=item.rating,
                comment=item.comment,
                customer_name=item.customer_name,
                created_at=item.created_at,
            )
            for item in result.reviews
        ],
        avg_rating=result.avg_rating,
        review_count=result.review_count,
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
                price=float(getattr(item, "price", None) or item.price_usd),
                currency=getattr(item, "currency", None) or "INR",
                price_usd=float(getattr(item, "price", None) or item.price_usd),
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
