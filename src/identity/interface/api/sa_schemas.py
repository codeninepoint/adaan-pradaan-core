from __future__ import annotations

from pydantic import BaseModel, Field


class CreateServiceAccountRequest(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    description: str | None = None
    initial_role: str | None = "resource-admin"


class CreateServiceAccountResponse(BaseModel):
    service_account_id: str
    principal_id: str
    name: str
    api_key: str
    key_prefix: str
    key_id: str
    status: str
    role_assigned: str | None = None


class ServiceAccountItem(BaseModel):
    service_account_id: str
    principal_id: str
    name: str
    description: str | None = None
    status: str
    key_prefix: str | None = None


class ListServiceAccountsResponse(BaseModel):
    items: list[ServiceAccountItem]


class AssignSaRoleRequest(BaseModel):
    role_id: str
    justification: str | None = None


class AssignSaRoleResponse(BaseModel):
    user_role_id: str
    principal_type: str
    role: str
    scope: str
    status: str


class RotateApiKeyRequest(BaseModel):
    reason: str | None = None


class RotateApiKeyResponse(BaseModel):
    old_key_prefix: str
    old_key_status: str
    new_api_key: str
    new_key_prefix: str
    new_key_id: str
    new_status: str


class RevokeApiKeyRequest(BaseModel):
    reason: str | None = None


class RevokeApiKeyResponse(BaseModel):
    key_id: str
    key_prefix: str
    status: str
    revoked_at: str
