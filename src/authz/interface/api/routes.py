from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from authz.application.role_bindings import RoleBindingService
from authz.interface.api.dependencies import get_role_binding_service
from authz.interface.api.schemas import (
    BindingItem,
    GrantBindingRequest,
    GrantBindingResponse,
    ListMembersResponse,
    ListRolesResponse,
    MemberItem,
    RevokeBindingRequest,
    RevokeBindingResponse,
    RoleItem,
)
from identity.interface.api.dependencies import CurrentAuthDep

router = APIRouter(prefix="/api/v1", tags=["authz"])


@router.get("/tenants/{tenant_id}/roles", response_model=ListRolesResponse)
async def list_roles(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[RoleBindingService, Depends(get_role_binding_service)],
) -> ListRolesResponse:
    user, _session, _credential = auth
    roles = await service.list_roles(tenant_id=tenant_id, caller_principal_id=user.principal_id)
    return ListRolesResponse(
        items=[
            RoleItem(
                role_id=str(r.role_id),
                name=r.name,
                is_system_role=r.is_system_role,
                status=r.status,
            )
            for r in roles
        ]
    )


@router.get("/tenants/{tenant_id}/members", response_model=ListMembersResponse)
async def list_members(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[RoleBindingService, Depends(get_role_binding_service)],
) -> ListMembersResponse:
    user, _session, _credential = auth
    members = await service.list_members(tenant_id=tenant_id, caller_principal_id=user.principal_id)
    return ListMembersResponse(
        items=[
            MemberItem(
                user_id=str(m.user_id),
                principal_id=str(m.principal_id),
                email=m.email,
                display_name=m.display_name,
                membership_status=m.membership_status,
                bindings=[
                    BindingItem(
                        binding_id=str(b.binding_id),
                        role_id=str(b.role_id),
                        role_name=b.role_name,
                        status=b.status,
                        granted_at=b.granted_at,
                        expires_at=b.expires_at,
                        justification=b.justification,
                    )
                    for b in m.bindings
                ],
            )
            for m in members
        ]
    )


@router.post(
    "/tenants/{tenant_id}/roles/{role_id}/bindings",
    response_model=GrantBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_binding(
    tenant_id: UUID,
    role_id: UUID,
    body: GrantBindingRequest,
    auth: CurrentAuthDep,
    service: Annotated[RoleBindingService, Depends(get_role_binding_service)],
) -> GrantBindingResponse:
    user, _session, _credential = auth
    result = await service.grant(
        tenant_id=tenant_id,
        role_id=role_id,
        caller_principal_id=user.principal_id,
        principal_id=UUID(body.principal_id) if body.principal_id else None,
        user_id=UUID(body.user_id) if body.user_id else None,
        expires_at=body.expires_at,
        justification=body.justification,
    )
    return GrantBindingResponse(
        binding_id=str(result.binding_id),
        principal_id=str(result.principal_id),
        user_id=str(result.user_id) if result.user_id else None,
        role_id=str(result.role_id),
        role=result.role_name,
        status=result.status,
        granted_by=str(result.granted_by_principal_id),
        granted_at=result.granted_at,
        expires_at=result.expires_at,
    )


@router.delete(
    "/tenants/{tenant_id}/roles/{role_id}/bindings/{binding_id}",
    response_model=RevokeBindingResponse,
)
async def revoke_binding(
    tenant_id: UUID,
    role_id: UUID,
    binding_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[RoleBindingService, Depends(get_role_binding_service)],
    body: RevokeBindingRequest | None = None,
) -> RevokeBindingResponse:
    user, _session, _credential = auth
    result = await service.revoke(
        tenant_id=tenant_id,
        role_id=role_id,
        binding_id=binding_id,
        caller_principal_id=user.principal_id,
        reason=body.reason if body else None,
    )
    return RevokeBindingResponse(
        binding_id=str(result.binding_id),
        status=result.status,
        revoked_at=result.revoked_at,
        effective=result.effective,
    )
