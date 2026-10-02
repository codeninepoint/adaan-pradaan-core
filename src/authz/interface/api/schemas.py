from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RoleItem(BaseModel):
    role_id: str
    name: str
    is_system_role: bool
    status: str


class ListRolesResponse(BaseModel):
    items: list[RoleItem]


class BindingItem(BaseModel):
    binding_id: str
    role_id: str
    role_name: str
    status: str
    granted_at: datetime
    expires_at: datetime | None = None
    justification: str | None = None


class MemberItem(BaseModel):
    user_id: str
    principal_id: str
    email: str
    display_name: str
    membership_status: str
    bindings: list[BindingItem]


class ListMembersResponse(BaseModel):
    items: list[MemberItem]


class GrantBindingRequest(BaseModel):
    principal_id: str | None = None
    user_id: str | None = None
    expires_at: datetime | None = None
    justification: str | None = Field(default=None, max_length=1024)


class GrantBindingResponse(BaseModel):
    binding_id: str
    principal_id: str
    user_id: str | None = None
    role_id: str
    role: str
    status: str
    granted_by: str
    granted_at: datetime
    expires_at: datetime | None = None


class RevokeBindingRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1024)


class RevokeBindingResponse(BaseModel):
    binding_id: str
    status: str
    revoked_at: datetime
    effective: str
