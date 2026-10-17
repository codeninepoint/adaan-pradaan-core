from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.platform_admin_users import PlatformAdminUserService
from identity.application.ports.keycloak import KeycloakClient
from identity.interface.api.dependencies import CurrentAuthDep, get_keycloak, get_session
from identity.interface.api.schemas import (
    AdminUserActionResponse,
    AdminUserItemResponse,
    AdminUserListResponse,
)

router = APIRouter(prefix="/api/v1", tags=["platform-admin-users"])


def get_platform_admin_user_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    keycloak: Annotated[KeycloakClient, Depends(get_keycloak)],
) -> PlatformAdminUserService:
    return PlatformAdminUserService(session, keycloak)


@router.get("/admin/users", response_model=AdminUserListResponse)
async def list_admin_users(
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminUserService, Depends(get_platform_admin_user_service)],
    q: Annotated[str | None, Query()] = None,
    principal_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query()] = 1,
    page_size: Annotated[int, Query()] = 50,
) -> AdminUserListResponse:
    user, _session, _credential = auth
    result = await service.list_users(
        caller_user_id=user.id,
        q=q,
        principal_type=principal_type,
        status=status,
        page=page,
        page_size=page_size,
    )
    return AdminUserListResponse(
        items=[
            AdminUserItemResponse(
                user_id=item.user_id,
                principal_id=item.principal_id,
                email=item.email,
                display_name=item.display_name,
                principal_type=item.principal_type,
                status=item.status,
                tenant_id=item.tenant_id,
                tenant_name=item.tenant_name,
                org_name=item.org_name,
                role_label=item.role_label,
                is_platform_operator=item.is_platform_operator,
                last_active_at=item.last_active_at,
            )
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post("/admin/users/{user_id}/suspend", response_model=AdminUserActionResponse)
async def suspend_admin_user(
    user_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminUserService, Depends(get_platform_admin_user_service)],
) -> AdminUserActionResponse:
    user, _session, _credential = auth
    result = await service.suspend_user(caller_user_id=user.id, target_user_id=user_id)
    return AdminUserActionResponse(**result)


@router.post("/admin/users/{user_id}/reinstate", response_model=AdminUserActionResponse)
async def reinstate_admin_user(
    user_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminUserService, Depends(get_platform_admin_user_service)],
) -> AdminUserActionResponse:
    user, _session, _credential = auth
    result = await service.reinstate_user(caller_user_id=user.id, target_user_id=user_id)
    return AdminUserActionResponse(**result)


@router.post("/admin/users/{user_id}/block", response_model=AdminUserActionResponse)
async def block_admin_user(
    user_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminUserService, Depends(get_platform_admin_user_service)],
) -> AdminUserActionResponse:
    user, _session, _credential = auth
    result = await service.block_user(caller_user_id=user.id, target_user_id=user_id)
    return AdminUserActionResponse(**result)


@router.post("/admin/users/{user_id}/reset-mfa", response_model=AdminUserActionResponse)
async def reset_admin_user_mfa(
    user_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminUserService, Depends(get_platform_admin_user_service)],
) -> AdminUserActionResponse:
    user, _session, _credential = auth
    result = await service.reset_mfa(caller_user_id=user.id, target_user_id=user_id)
    return AdminUserActionResponse(**result)


@router.post("/admin/users/{user_id}/promote-operator", response_model=AdminUserActionResponse)
async def promote_admin_user_operator(
    user_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PlatformAdminUserService, Depends(get_platform_admin_user_service)],
) -> AdminUserActionResponse:
    user, _session, _credential = auth
    result = await service.promote_operator(caller_user_id=user.id, target_user_id=user_id)
    return AdminUserActionResponse(**result)
