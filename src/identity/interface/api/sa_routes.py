from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.interface.api.dependencies import get_authorization_service
from identity.application.service_accounts import ServiceAccountService
from identity.interface.api.dependencies import CurrentAuthDep, get_session
from identity.interface.api.sa_schemas import (
    AssignSaRoleRequest,
    AssignSaRoleResponse,
    CreateServiceAccountRequest,
    CreateServiceAccountResponse,
    ListServiceAccountsResponse,
    RevokeApiKeyRequest,
    RevokeApiKeyResponse,
    RotateApiKeyRequest,
    RotateApiKeyResponse,
    ServiceAccountItem,
)

router = APIRouter(prefix="/api/v1", tags=["service-accounts"])


def get_service_account_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> ServiceAccountService:
    return ServiceAccountService(session, authorization)


@router.get(
    "/tenants/{tenant_id}/service-accounts",
    response_model=ListServiceAccountsResponse,
)
async def list_service_accounts(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> ListServiceAccountsResponse:
    user, _session, _credential = auth
    items = await service.list(tenant_id=tenant_id, caller_principal_id=user.principal_id)
    return ListServiceAccountsResponse(
        items=[
            ServiceAccountItem(
                service_account_id=str(i.service_account_id),
                principal_id=str(i.principal_id),
                name=i.name,
                description=i.description,
                status=i.status,
                key_prefix=i.key_prefix,
            )
            for i in items
        ]
    )


@router.post(
    "/tenants/{tenant_id}/service-accounts",
    response_model=CreateServiceAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_account(
    tenant_id: UUID,
    body: CreateServiceAccountRequest,
    auth: CurrentAuthDep,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> CreateServiceAccountResponse:
    user, _session, _credential = auth
    result = await service.create(
        tenant_id=tenant_id,
        caller_principal_id=user.principal_id,
        name=body.name,
        description=body.description,
        initial_role=body.initial_role,
    )
    return CreateServiceAccountResponse(
        service_account_id=str(result.service_account_id),
        principal_id=str(result.principal_id),
        name=result.name,
        api_key=result.api_key,
        key_prefix=result.key_prefix,
        key_id=str(result.key_id),
        status=result.status,
        role_assigned=result.role_assigned,
    )


@router.post(
    "/tenants/{tenant_id}/service-accounts/{sa_id}/roles",
    response_model=AssignSaRoleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_sa_role(
    tenant_id: UUID,
    sa_id: UUID,
    body: AssignSaRoleRequest,
    auth: CurrentAuthDep,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> AssignSaRoleResponse:
    user, _session, _credential = auth
    result = await service.assign_role(
        tenant_id=tenant_id,
        sa_id=sa_id,
        caller_principal_id=user.principal_id,
        role_id=UUID(body.role_id),
        justification=body.justification,
    )
    return AssignSaRoleResponse(
        user_role_id=str(result.user_role_id),
        principal_type=result.principal_type,
        role=result.role,
        scope=result.scope,
        status=result.status,
    )


@router.post(
    "/tenants/{tenant_id}/service-accounts/{sa_id}/api-keys/rotate",
    response_model=RotateApiKeyResponse,
)
async def rotate_api_key(
    tenant_id: UUID,
    sa_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
    body: RotateApiKeyRequest | None = None,
) -> RotateApiKeyResponse:
    user, _session, _credential = auth
    result = await service.rotate_key(
        tenant_id=tenant_id,
        sa_id=sa_id,
        caller_principal_id=user.principal_id,
        reason=body.reason if body else None,
    )
    return RotateApiKeyResponse(
        old_key_prefix=result.old_key_prefix,
        old_key_status=result.old_key_status,
        new_api_key=result.new_api_key,
        new_key_prefix=result.new_key_prefix,
        new_key_id=str(result.new_key_id),
        new_status=result.new_status,
    )


@router.delete(
    "/tenants/{tenant_id}/service-accounts/{sa_id}/api-keys/{key_id}",
    response_model=RevokeApiKeyResponse,
)
async def revoke_api_key(
    tenant_id: UUID,
    sa_id: UUID,
    key_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
    body: RevokeApiKeyRequest | None = None,
) -> RevokeApiKeyResponse:
    user, _session, _credential = auth
    result = await service.revoke_key(
        tenant_id=tenant_id,
        sa_id=sa_id,
        key_id=key_id,
        caller_principal_id=user.principal_id,
        reason=body.reason if body else None,
    )
    return RevokeApiKeyResponse(
        key_id=str(result.key_id),
        key_prefix=result.key_prefix,
        status=result.status,
        revoked_at=result.revoked_at.isoformat(),
    )
