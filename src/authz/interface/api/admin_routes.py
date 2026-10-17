from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.platform_admin_roles import PlatformAdminRoleService
from authz.interface.api.admin_schemas import (
    AdminBindingItem,
    AdminBindingListResponse,
    AdminCreateRoleRequest,
    AdminGrantBindingRequest,
    AdminPermissionItem,
    AdminPermissionListResponse,
    AdminRevokeBindingRequest,
    AdminRoleItem,
    AdminRoleListResponse,
    AdminUpdateRoleRequest,
)
from identity.interface.api.dependencies import CurrentAuthDep, get_session

router = APIRouter(prefix="/api/v1", tags=["platform-admin-authz"])


def get_platform_admin_role_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlatformAdminRoleService:
    return PlatformAdminRoleService(session)


def _role_item(view) -> AdminRoleItem:
    return AdminRoleItem(
        role_id=str(view.role_id) if view.role_id else None,
        name=view.name,
        scope_type=view.scope_type,
        is_system_role=view.is_system_role,
        tenant_id=str(view.tenant_id) if view.tenant_id else None,
        operator_org_id=str(view.operator_org_id) if view.operator_org_id else None,
        status=view.status,
        permission_codes=view.permission_codes,
    )


@router.get("/admin/permissions", response_model=AdminPermissionListResponse)
async def list_admin_permissions(
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminRoleService, Depends(get_platform_admin_role_service)],
) -> AdminPermissionListResponse:
    user, _session, _credential = auth
    items = await service.list_permissions(caller_user_id=user.id)
    return AdminPermissionListResponse(
        items=[
            AdminPermissionItem(code=i.code, scope_type=i.scope_type, description=i.description)
            for i in items
        ]
    )


@router.get("/admin/roles", response_model=AdminRoleListResponse)
async def list_admin_roles(
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminRoleService, Depends(get_platform_admin_role_service)],
) -> AdminRoleListResponse:
    user, _session, _credential = auth
    items = await service.list_roles(caller_user_id=user.id)
    return AdminRoleListResponse(items=[_role_item(i) for i in items])


@router.post("/admin/roles", response_model=AdminRoleItem, status_code=201)
async def create_admin_role(
    body: AdminCreateRoleRequest,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminRoleService, Depends(get_platform_admin_role_service)],
) -> AdminRoleItem:
    user, _session, _credential = auth
    view = await service.create_custom_role(
        caller_user_id=user.id,
        name=body.name,
        based_on=body.based_on,
        tenant_id=UUID(body.tenant_id),
        add_permissions=body.add_permissions,
        remove_permissions=body.remove_permissions,
    )
    return _role_item(view)


@router.patch("/admin/roles/{role_id}", response_model=AdminRoleItem)
async def update_admin_role(
    role_id: UUID,
    body: AdminUpdateRoleRequest,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminRoleService, Depends(get_platform_admin_role_service)],
) -> AdminRoleItem:
    user, _session, _credential = auth
    view = await service.update_custom_role(
        caller_user_id=user.id,
        role_id=role_id,
        permission_codes=body.permission_codes,
    )
    return _role_item(view)


@router.get("/admin/role-bindings", response_model=AdminBindingListResponse)
async def list_admin_role_bindings(
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminRoleService, Depends(get_platform_admin_role_service)],
) -> AdminBindingListResponse:
    user, _session, _credential = auth
    items = await service.list_bindings(caller_user_id=user.id)
    return AdminBindingListResponse(
        items=[
            AdminBindingItem(
                binding_id=str(i.binding_id),
                principal_id=str(i.principal_id),
                user_email=i.user_email,
                role_id=str(i.role_id),
                role_name=i.role_name,
                scope_type=i.scope_type,
                tenant_id=str(i.tenant_id) if i.tenant_id else None,
                tenant_name=i.tenant_name,
                granted_by=str(i.granted_by) if i.granted_by else None,
                since=i.since,
                status=i.status,
            )
            for i in items
        ]
    )


@router.post("/admin/role-bindings", response_model=AdminBindingItem, status_code=201)
async def grant_admin_role_binding(
    body: AdminGrantBindingRequest,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminRoleService, Depends(get_platform_admin_role_service)],
) -> AdminBindingItem:
    user, _session, _credential = auth
    view = await service.grant_binding(
        caller_user_id=user.id,
        role_id=UUID(body.role_id),
        principal_id=UUID(body.principal_id) if body.principal_id else None,
        user_id=UUID(body.user_id) if body.user_id else None,
        tenant_id=UUID(body.tenant_id) if body.tenant_id else None,
        justification=body.justification,
    )
    return AdminBindingItem(
        binding_id=str(view.binding_id),
        principal_id=str(view.principal_id),
        user_email=view.user_email,
        role_id=str(view.role_id),
        role_name=view.role_name,
        scope_type=view.scope_type,
        tenant_id=str(view.tenant_id) if view.tenant_id else None,
        tenant_name=view.tenant_name,
        granted_by=str(view.granted_by) if view.granted_by else None,
        since=view.since,
        status=view.status,
    )


@router.delete("/admin/role-bindings/{binding_id}")
async def revoke_admin_role_binding(
    binding_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminRoleService, Depends(get_platform_admin_role_service)],
    body: AdminRevokeBindingRequest | None = None,
) -> dict:
    user, _session, _credential = auth
    return await service.revoke_binding(
        caller_user_id=user.id,
        binding_id=binding_id,
        reason=body.reason if body else None,
    )
