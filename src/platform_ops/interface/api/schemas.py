from __future__ import annotations

from pydantic import BaseModel, Field


class TenantListItemResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    org_id: str
    org_name: str
    org_type: str
    participation: str
    member_count: int
    status: str


class TenantListResponse(BaseModel):
    items: list[TenantListItemResponse]


class TenantStatsResponse(BaseModel):
    active: int
    suspended: int
    total: int
    individual: int = 0
    organisation: int = 0
    vendor: int = 0


class TenantActionResponse(BaseModel):
    tenant_id: str
    status: str
    sessions_revoked: int | None = None
    created: bool | None = None
    org_id: str | None = None


class ProvisionTenantRequest(BaseModel):
    email: str
    org_name: str | None = None
    tenant_name: str = "default"


class DashboardResponse(BaseModel):
    tenant_count: int
    active_tenants: int
    vendor_count: int
    verified_vendors: int
    user_count: int
    pending_plugin_reviews: int
    pending_product_reviews: int
    revenue_mtd: float
    recent_events: list[dict] = Field(default_factory=list)


class AuditLogItemResponse(BaseModel):
    id: str
    event_action: str
    actor_user_id: str | None = None
    actor_email: str | None = None
    tenant_id: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: str


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItemResponse]
    total: int
    page: int
    page_size: int


class PolicyItemResponse(BaseModel):
    id: str
    name: str
    scope: str
    enforcement: str
    applies_to: str
    status: str
    body: dict = Field(default_factory=dict)


class PolicyListResponse(BaseModel):
    items: list[PolicyItemResponse]


class CreatePolicyRequest(BaseModel):
    name: str
    scope: str
    enforcement: str = "mandatory"
    applies_to: str = ""
    body: dict = Field(default_factory=dict)


class UpdatePolicyRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    enforcement: str | None = None
    applies_to: str | None = None
    body: dict | None = None


class ConfigResponse(BaseModel):
    values: dict[str, object]


class PatchConfigRequest(BaseModel):
    updates: dict[str, object]


class TeamMemberResponse(BaseModel):
    id: str
    user_id: str | None = None
    email: str
    platform_role: str
    status: str
    mfa_enabled: bool
    invited_at: str
    activated_at: str | None = None


class TeamListResponse(BaseModel):
    items: list[TeamMemberResponse]


class InviteTeamRequest(BaseModel):
    email: str
    platform_role: str
    invite_note: str = ""


class UpdateTeamRoleRequest(BaseModel):
    platform_role: str


class TransferSuperAdminRequest(BaseModel):
    recipient_member_id: str
    password: str


class TeamActionResponse(BaseModel):
    member_id: str | None = None
    status: str | None = None
    from_member_id: str | None = None
    to_member_id: str | None = None
    caller_role: str | None = None
    recipient_role: str | None = None
