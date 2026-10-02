from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.interface.api.dependencies import get_authorization_service
from identity.application.ports.keycloak import KeycloakClient
from identity.interface.api.dependencies import CurrentAuthDep, get_keycloak, get_session
from tenant.application.members import MemberService
from tenant.application.org_upgrade import OrgUpgradeService
from tenant.interface.api.schemas import (
    OrgInviteRequest,
    OrgInviteResponse,
    OrgRegisterRequest,
    OrgRegisterResponse,
    OrgRemoveResponse,
    TenantInviteRequest,
    TenantInviteResponse,
    TenantRemoveResponse,
)

router = APIRouter(prefix="/api/v1", tags=["tenant"])


def get_org_upgrade_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    keycloak: Annotated[KeycloakClient, Depends(get_keycloak)],
) -> OrgUpgradeService:
    return OrgUpgradeService(session, keycloak)


def get_member_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> MemberService:
    return MemberService(session, authorization)


@router.post(
    "/organizations/register",
    response_model=OrgRegisterResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def register_organization(
    body: OrgRegisterRequest,
    auth: CurrentAuthDep,
    service: Annotated[OrgUpgradeService, Depends(get_org_upgrade_service)],
) -> OrgRegisterResponse:
    user, _session, _credential = auth
    result = await service.submit(
        requester_user_id=user.id,
        requester_principal_id=user.principal_id,
        name=body.name,
        slug=body.slug,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        country=body.country,
    )
    return OrgRegisterResponse(
        request_id=str(result.request_id),
        status=result.status,
        org_id=str(result.org_id),
        estimated_ms=result.estimated_ms,
        keycloak_realm_ref=result.keycloak_realm_ref,
        realm_url=result.realm_url,
        error_message=result.error_message,
    )


@router.get(
    "/organizations/register/{request_id}",
    response_model=OrgRegisterResponse,
)
async def get_organization_registration(
    request_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[OrgUpgradeService, Depends(get_org_upgrade_service)],
) -> OrgRegisterResponse:
    user, _session, _credential = auth
    result = await service.get_status(request_id=request_id, requester_user_id=user.id)
    return OrgRegisterResponse(
        request_id=str(result.request_id),
        status=result.status,
        org_id=str(result.org_id),
        estimated_ms=result.estimated_ms,
        keycloak_realm_ref=result.keycloak_realm_ref,
        realm_url=result.realm_url,
        error_message=result.error_message,
    )


@router.post(
    "/tenants/{tenant_id}/members",
    response_model=TenantInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_tenant_member(
    tenant_id: UUID,
    body: TenantInviteRequest,
    auth: CurrentAuthDep,
    service: Annotated[MemberService, Depends(get_member_service)],
) -> TenantInviteResponse:
    user, _session, _credential = auth
    result = await service.invite_tenant_member(
        tenant_id=tenant_id,
        caller_principal_id=user.principal_id,
        user_id=UUID(body.user_id),
        role_name=body.role,
    )
    return TenantInviteResponse(
        membership_id=str(result.membership_id),
        tenant_id=str(result.tenant_id),
        user_id=str(result.user_id),
        role=result.role,
        status=result.status,
    )


@router.delete(
    "/tenants/{tenant_id}/members/{user_id}",
    response_model=TenantRemoveResponse,
)
async def remove_tenant_member(
    tenant_id: UUID,
    user_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[MemberService, Depends(get_member_service)],
) -> TenantRemoveResponse:
    user, _session, _credential = auth
    result = await service.remove_tenant_member(
        tenant_id=tenant_id,
        caller_principal_id=user.principal_id,
        user_id=user_id,
    )
    return TenantRemoveResponse(
        user_id=str(result.user_id),
        tenant_id=str(result.tenant_id),
        status=result.status,
    )


@router.post(
    "/organizations/{org_id}/members",
    response_model=OrgInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_org_member(
    org_id: UUID,
    body: OrgInviteRequest,
    auth: CurrentAuthDep,
    service: Annotated[MemberService, Depends(get_member_service)],
) -> OrgInviteResponse:
    user, _session, _credential = auth
    result = await service.invite_org_member(
        org_id=org_id,
        caller_user_id=user.id,
        email=body.email,
        org_role=body.org_role,
    )
    return OrgInviteResponse(
        invite_id=str(result.invite_id),
        email=result.email,
        org_role=result.org_role,
        status=result.status,
        user_id=str(result.user_id),
    )


@router.post(
    "/organizations/{org_id}/members/accept",
    response_model=OrgInviteResponse,
)
async def accept_org_invite(
    org_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[MemberService, Depends(get_member_service)],
) -> OrgInviteResponse:
    user, _session, _credential = auth
    result = await service.accept_org_invite(org_id=org_id, caller_user_id=user.id)
    return OrgInviteResponse(
        invite_id=str(result.invite_id),
        email=result.email,
        org_role=result.org_role,
        status=result.status,
        user_id=str(result.user_id),
    )


@router.delete(
    "/organizations/{org_id}/members/{user_id}",
    response_model=OrgRemoveResponse,
)
async def remove_org_member(
    org_id: UUID,
    user_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[MemberService, Depends(get_member_service)],
) -> OrgRemoveResponse:
    user, _session, _credential = auth
    result = await service.remove_org_member(
        org_id=org_id, caller_user_id=user.id, user_id=user_id
    )
    return OrgRemoveResponse(
        user_id=str(result.user_id),
        status=result.status,
        tenant_bindings_revoked=result.tenant_bindings_revoked,
    )
