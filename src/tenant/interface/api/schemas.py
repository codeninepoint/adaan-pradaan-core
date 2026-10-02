from __future__ import annotations

from pydantic import BaseModel, Field


class OrgRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=64)
    contact_name: str = Field(min_length=1, max_length=255)
    contact_email: str = Field(min_length=3, max_length=255)
    country: str = Field(min_length=2, max_length=8)


class OrgRegisterResponse(BaseModel):
    request_id: str
    status: str
    org_id: str
    estimated_ms: int = 0
    keycloak_realm_ref: str | None = None
    realm_url: str | None = None
    error_message: str | None = None


class TenantInviteRequest(BaseModel):
    user_id: str
    role: str = "viewer"


class TenantInviteResponse(BaseModel):
    membership_id: str
    tenant_id: str
    user_id: str
    role: str
    status: str


class TenantRemoveResponse(BaseModel):
    user_id: str
    tenant_id: str
    status: str


class OrgInviteRequest(BaseModel):
    email: str
    org_role: str = "member"


class OrgInviteResponse(BaseModel):
    invite_id: str
    email: str
    org_role: str
    status: str
    user_id: str | None = None


class OrgRemoveResponse(BaseModel):
    user_id: str
    status: str
    tenant_bindings_revoked: int
