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


class PluginListResponse(BaseModel):
    plugins: list[PluginListItem]


class RegisterPluginResponse(BaseModel):
    plugin_id: str
    slug: str
    status: str
    vendor_id: str


class SubmitVersionRequest(BaseModel):
    version: str
    artifact_url: str
    changelog: str = ""
    sbom_url: str


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


class ListVersionsResponse(BaseModel):
    plugin_id: str
    versions: list[VersionItem]


class PendingReviewItem(BaseModel):
    version_id: str
    plugin_id: str
    plugin_slug: str
    version: str
    status: str
    vendor_id: str
    vendor_name: str
    claimed_by: str | None = None
    submitted_at: str = ""


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


class VendorDirectoryResponse(BaseModel):
    results: list[VendorDirectoryItemResponse]


class SuspendVendorRequest(BaseModel):
    reason: str


class SuspendVendorResponse(BaseModel):
    vendor_id: str
    status: str
    offerings_unpublished: int


class PendingReviewsResponse(BaseModel):
    items: list[PendingReviewItem]


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
    plugin_id: str
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


class InventoryAdjustRequest(BaseModel):
    available: int


class InventoryResponse(BaseModel):
    inventory_id: str
    product_id: str
    product_name: str
    warehouse_id: str
    warehouse_name: str
    sku: str
    available: int
    reserved: int


class InventoryListResponse(BaseModel):
    rows: list[InventoryResponse]


class UpdateProductRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    content: dict | None = None


class CreateOfferingRequest(BaseModel):
    plan_name: str
    billing_period: str
    price_usd: Decimal
    included_transactions: int | None = None
    overage_price_per_1k: Decimal | None = None


class OfferingListItemResponse(BaseModel):
    offering_id: str
    product_id: str
    product_name: str
    plan_name: str
    status: str
    price_usd: float


class UpdateOfferingPriceRequest(BaseModel):
    price_usd: Decimal


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
    price_usd: float
    billing_period: str
    fulfilment_type: str
    category: str


class CatalogResponse(BaseModel):
    results: list[CatalogItem]
    page: int = 1
    total: int


class HomeResponse(BaseModel):
    categories: list[str]
    rails: dict[str, list[CatalogItem]]


class OfferingDetailItem(BaseModel):
    offering_id: str
    plan_name: str
    price_usd: float
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
