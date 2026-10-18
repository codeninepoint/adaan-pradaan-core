from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class PortalResponse(BaseModel):
    vendor_id: str
    status: str
    product_count: int
    offering_count: int
    active_installs: int
    pending_plugin_reviews: int


class RegisterPluginRequest(BaseModel):
    name: str
    slug: str
    category: str
    short_description: str = ""


class PluginListItem(BaseModel):
    plugin_id: str
    name: str
    slug: str
    status: str
    latest_version: str | None = None
    latest_version_status: str | None = None
    category: str = ""
    short_description: str = ""
    review_notes: str = ""
    submitted_at: str = ""
    changelog: str = ""


class PluginListResponse(BaseModel):
    plugins: list[PluginListItem]


class VendorStandardPluginItem(BaseModel):
    plugin_id: str
    name: str
    slug: str
    category: str
    short_description: str
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    vendor_count: int = 0
    activation_status: str


class VendorStandardPluginListResponse(BaseModel):
    items: list[VendorStandardPluginItem]


class VendorPluginSubmitRequest(BaseModel):
    name: str
    version: str
    category: str
    description: str = ""
    artifact_url: str
    sbom_url: str = ""
    plugin_id: str | None = None
    slug: str | None = None


class VendorPluginSubmitResponse(BaseModel):
    plugin_id: str
    version_id: str
    slug: str
    version: str
    status: str


class RegisterPluginResponse(BaseModel):
    plugin_id: str
    slug: str
    status: str
    vendor_id: str


class SubmitVersionRequest(BaseModel):
    version: str
    artifact_url: str
    changelog: str = ""
    sbom_url: str = ""


class SubmitVersionResponse(BaseModel):
    version_id: str
    plugin_id: str
    version: str
    status: str


class CapabilityInput(BaseModel):
    scope: str
    justification: str = ""


class DeclareCapabilitiesRequest(BaseModel):
    capabilities: list[CapabilityInput]


class DeclareCapabilitiesResponse(BaseModel):
    version_id: str
    capability_count: int


class VersionItem(BaseModel):
    version_id: str
    version: str
    status: str
    scan_status: str
    submitted_at: str
    decided_at: str | None
    artifact_url: str
    changelog: str
    sbom_url: str
    review_notes: str = ""


class ListVersionsResponse(BaseModel):
    plugin_id: str
    versions: list[VersionItem]


class PendingReviewItem(BaseModel):
    version_id: str
    plugin_id: str
    plugin_slug: str
    version: str
    status: str
    vendor_id: str | None = None
    vendor_name: str
    claimed_by: str | None = None
    submitted_at: str = ""
    risk_level: str = "low"
    decided_by: str | None = None
    decided_at: str | None = None
    review_notes: str = ""


class PendingReviewsResponse(BaseModel):
    items: list[PendingReviewItem]


class ReviewStatsResponse(BaseModel):
    pending: int
    in_review: int
    published: int
    rejected: int
    standard_plugins: int


class ReviewDetailResponse(BaseModel):
    version_id: str
    plugin: str
    version: str
    status: str
    scan_status: str
    requested_capabilities: list[str]
    sbom_url: str
    changelog: str
    artifact_url: str
    claimed_by: str | None = None
    review_notes: str = ""
    risk_level: str = "low"


class StandardPluginRequirement(BaseModel):
    name: str
    detail: str = ""


class StandardPluginItem(BaseModel):
    plugin_id: str | None = None
    category: str
    name: str | None = None
    slug: str | None = None
    status: str | None = None
    short_description: str | None = None
    version: str | None = None
    requirements: list = Field(default_factory=list)
    updated_at: str | None = None


class StandardPluginListResponse(BaseModel):
    items: list[StandardPluginItem]


class CreateStandardPluginRequest(BaseModel):
    name: str
    slug: str
    category: str
    short_description: str = ""
    version: str
    artifact_url: str
    changelog: str = ""
    requirements: list = Field(default_factory=list)
    publish: bool = True


class CreateStandardPluginResponse(BaseModel):
    plugin_id: str
    slug: str
    category: str
    status: str
    version: str


class UpdateStandardPluginRequest(BaseModel):
    name: str | None = None
    short_description: str | None = None
    requirements: list | None = None


class ClaimResponse(BaseModel):
    version_id: str
    claimed_by: str
    claimed_at: str


class RequestChangesRequest(BaseModel):
    notes: str


class VendorDirectoryItemResponse(BaseModel):
    vendor_id: str
    legal_name: str
    status: str
    product_count: int
    active_installs: int
    plugin_count: int = 0
    warehouse_count: int = 0
    kyc_status: str = ""
    gmv_mtd: float = 0.0


class VendorDirectoryResponse(BaseModel):
    results: list[VendorDirectoryItemResponse]


class VendorStatsResponse(BaseModel):
    active: int
    pending_verification: int
    suspended: int
    total_plugins: int


class AdminProductItemResponse(BaseModel):
    product_id: str
    name: str
    vendor_id: str
    vendor_name: str
    category: str
    status: str
    pa_status: str
    pa_reject_reason: str = ""
    fulfilment_type: str
    submitted_at: str = ""


class AdminProductListResponse(BaseModel):
    items: list[AdminProductItemResponse]


class AdminProductStatsResponse(BaseModel):
    pending_review: int
    live: int
    rejected: int
    not_submitted: int
    warehouse_locations: int = 0


class RejectProductRequest(BaseModel):
    reason: str


class LocationSummaryItemResponse(BaseModel):
    location: str
    warehouse_count: int
    vendor_count: int
    units_stored: int


class LocationSummaryResponse(BaseModel):
    items: list[LocationSummaryItemResponse]


class SuspendVendorRequest(BaseModel):
    reason: str


class SuspendVendorResponse(BaseModel):
    vendor_id: str
    status: str
    offerings_unpublished: int


class VersionDecisionRequest(BaseModel):
    decision: str
    notes: str | None = None


class VersionDecisionResponse(BaseModel):
    version_id: str
    status: str
    decided_by: str
    decided_at: str


class CreateProductRequest(BaseModel):
    name: str
    description: str = ""
    plugin_id: str | None = None
    fulfilment_type: str
    category: str | None = None
    content: dict = Field(default_factory=dict)


class ProductResponse(BaseModel):
    product_id: str
    name: str
    status: str
    fulfilment_type: str
    category: str = ""
    content: dict = Field(default_factory=dict)
    pa_status: str = "not_submitted"
    pa_reject_reason: str = ""
    mrp_inr: float = 0.0
    image_count: int = 0
    cities: list[str] = Field(default_factory=list)
    stock_status: str = "none"
    visibility: str = "hidden"
    brand: str = ""
    net_weight: str = ""
    sku: str = ""
    image_urls: list[str] = Field(default_factory=list)
    currency: str = "INR"


class ServiceCityResponse(BaseModel):
    city_id: str
    city_name: str
    warehouse_id: str
    pincodes: list[str] = Field(default_factory=list)
    currency: str | None = None
    resolved_currency: str = "INR"


class ServiceCityListResponse(BaseModel):
    cities: list[ServiceCityResponse]


class AddServiceCityRequest(BaseModel):
    city_name: str
    currency: str | None = None


class UpdateServiceCityRequest(BaseModel):
    currency: str | None = None


class SetCityPincodesRequest(BaseModel):
    pincodes: list[str]


class ProductCityAssignmentResponse(BaseModel):
    product_id: str
    product_name: str
    category: str
    cities: list[str] = Field(default_factory=list)
    status: str


class ProductCityAssignmentListResponse(BaseModel):
    items: list[ProductCityAssignmentResponse]


class SetProductServiceCitiesRequest(BaseModel):
    city_ids: list[str]


class SubmitProductListingRequest(BaseModel):
    product_id: str | None = None
    name: str
    description: str
    category: str
    sku: str
    mrp_inr: float = Field(gt=0)
    currency: str | None = None
    net_weight: str
    brand: str
    image_urls: list[str]
    authenticity_attested: bool
    city_ids: list[str] = Field(default_factory=list)
    fulfilment_type: str = "SHIP_PHYSICAL"


class ProductListResponse(BaseModel):
    products: list[ProductResponse]


class WarehouseRequest(BaseModel):
    name: str
    location: str
    capacity: int = Field(ge=0)


class WarehouseResponse(BaseModel):
    warehouse_id: str
    name: str
    location: str
    capacity: int
    units_stored: int
    sku_count: int


class WarehouseListResponse(BaseModel):
    warehouses: list[WarehouseResponse]


class InventoryRequest(BaseModel):
    product_id: str
    warehouse_id: str
    sku: str
    available: int = 0
    reorder_threshold: int | None = None


class InventoryAdjustRequest(BaseModel):
    available: int
    reorder_threshold: int | None = None


class InventoryResponse(BaseModel):
    inventory_id: str
    product_id: str
    product_name: str
    warehouse_id: str
    warehouse_name: str
    sku: str
    available: int
    reserved: int
    reorder_threshold: int = 20
    city_name: str | None = None
    status: str | None = None


class CityInventoryResponse(BaseModel):
    inventory_id: str
    product_id: str
    product_name: str
    city_id: str
    city_name: str
    sku: str
    available: int
    reserved: int
    reorder_threshold: int
    status: str


class InventoryListResponse(BaseModel):
    rows: list[InventoryResponse] = Field(default_factory=list)
    city_rows: list[CityInventoryResponse] = Field(default_factory=list)


class UpdateProductRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    content: dict | None = None


class CreateOfferingRequest(BaseModel):
    plan_name: str
    billing_period: str
    price_usd: Decimal
    currency: str | None = None
    included_transactions: int | None = None
    overage_price_per_1k: Decimal | None = None


class OfferingListItemResponse(BaseModel):
    offering_id: str
    product_id: str
    product_name: str
    plan_name: str
    status: str
    price: float
    currency: str = "INR"
    price_usd: float  # deprecated alias of amount


class UpdateOfferingPriceRequest(BaseModel):
    price_usd: Decimal
    currency: str | None = None


class OfferingListResponse(BaseModel):
    offerings: list[OfferingListItemResponse]


class OfferingResponse(BaseModel):
    offering_id: str
    product_id: str
    plan_name: str
    status: str


class CatalogItem(BaseModel):
    offering_id: str
    product_id: str
    product_name: str
    vendor: str
    vendor_id: str
    plan_name: str
    price: float
    currency: str = "INR"
    price_usd: float  # deprecated alias of amount
    billing_period: str
    fulfilment_type: str
    category: str
    avg_rating: float = 0.0
    review_count: int = 0
    in_stock: bool = True


class CatalogVendorFacet(BaseModel):
    vendor_id: str
    name: str


class CatalogFacets(BaseModel):
    vendors: list[CatalogVendorFacet] = Field(default_factory=list)


class CatalogResponse(BaseModel):
    results: list[CatalogItem]
    page: int = 1
    total: int
    facets: CatalogFacets = Field(default_factory=CatalogFacets)


class PublicProductReviewItem(BaseModel):
    rating: int
    comment: str
    customer_name: str
    created_at: str


class PublicProductReviewListResponse(BaseModel):
    reviews: list[PublicProductReviewItem]
    avg_rating: float = 0.0
    review_count: int = 0


class HomeResponse(BaseModel):
    categories: list[str]
    rails: dict[str, list[CatalogItem]]


class OfferingDetailItem(BaseModel):
    offering_id: str
    plan_name: str
    price: float
    currency: str = "INR"
    price_usd: float  # deprecated alias of amount
    billing_period: str
    status: str


class ProductDetailResponse(BaseModel):
    product_id: str
    name: str
    description: str
    fulfilment_type: str
    vendor: str
    category: str
    content: dict
    capabilities: list[str]
    offerings: list[OfferingDetailItem]


class InstallRequest(BaseModel):
    offering_id: str
    project_id: str | None = None
    accepted_capabilities: list[str] = Field(default_factory=list)


class InstallResponse(BaseModel):
    installation_id: str
    offering_id: str
    tenant_id: str
    status: str
    entitlement_id: str


class EntitlementItem(BaseModel):
    entitlement_id: str
    offering: str
    status: str
    installation_status: str
    granted_at: str


class EntitlementsResponse(BaseModel):
    entitlements: list[EntitlementItem]


class VendorInstallItem(BaseModel):
    installation_id: str
    tenant_name: str
    product_name: str
    fulfilment_type: str
    status: str
    since: str


class VendorInstallListResponse(BaseModel):
    installations: list[VendorInstallItem]
