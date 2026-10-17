from __future__ import annotations

from pydantic import BaseModel, Field


class AdminPermissionItem(BaseModel):
    code: str
    scope_type: str
    description: str | None = None


class AdminPermissionListResponse(BaseModel):
    items: list[AdminPermissionItem]


class AdminRoleItem(BaseModel):
    role_id: str | None = None
    name: str
    scope_type: str
    is_system_role: bool
    tenant_id: str | None = None
    operator_org_id: str | None = None
    status: str
    permission_codes: list[str] = Field(default_factory=list)


class AdminRoleListResponse(BaseModel):
    items: list[AdminRoleItem]


class AdminCreateRoleRequest(BaseModel):
    name: str
    based_on: str
    tenant_id: str
    add_permissions: list[str] = Field(default_factory=list)
    remove_permissions: list[str] = Field(default_factory=list)


class AdminUpdateRoleRequest(BaseModel):
    permission_codes: list[str]


class AdminBindingItem(BaseModel):
    binding_id: str
    principal_id: str
    user_email: str | None = None
    role_id: str
    role_name: str
    scope_type: str
    tenant_id: str | None = None
    tenant_name: str | None = None
    granted_by: str | None = None
    since: str
    status: str


class AdminBindingListResponse(BaseModel):
    items: list[AdminBindingItem]


class AdminGrantBindingRequest(BaseModel):
    role_id: str
    principal_id: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
    justification: str | None = Field(default=None, max_length=1024)


class AdminRevokeBindingRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1024)
