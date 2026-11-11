from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.ports.keycloak import KeycloakClient
from identity.interface.api.dependencies import CurrentAuthDep, get_keycloak, get_session
from platform_ops.application.admin_ops_service import AdminOpsService
from platform_ops.application.communications_service import CommunicationsService
from platform_ops.application.settlement_service import SettlementService
from platform_ops.interface.api.schemas import (
    AuditLogItemResponse,
    AuditLogListResponse,
    CommunicationConsentResponse,
    CommunicationTemplateItem,
    CommunicationTemplateListResponse,
    CommunicationTemplateSummary,
    CommunicationUsageItem,
    CommunicationUsageListResponse,
    CommunicationUsageSummary,
    ConfigResponse,
    CreateCommunicationTemplateRequest,
    CreatePolicyRequest,
    DashboardResponse,
    InviteTeamRequest,
    PatchConfigRequest,
    PolicyItemResponse,
    PolicyListResponse,
    ProvisionTenantRequest,
    ResolveSettlementReturnRequest,
    SettlementFraudActionRequest,
    TeamActionResponse,
    TeamListResponse,
    TeamMemberResponse,
    TenantActionResponse,
    TenantListItemResponse,
    TenantListResponse,
    TenantStatsResponse,
    TransferSuperAdminRequest,
    UpdatePolicyRequest,
    UpdateTeamRoleRequest,
)

router = APIRouter(prefix="/api/v1", tags=["platform-admin-ops"])


def get_admin_ops_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    keycloak: Annotated[KeycloakClient, Depends(get_keycloak)],
) -> AdminOpsService:
    return AdminOpsService(session, keycloak)


def get_communications_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommunicationsService:
    return CommunicationsService(session)


def get_settlement_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SettlementService:
    return SettlementService(session)


def _comm_template(item) -> CommunicationTemplateItem:
    return CommunicationTemplateItem(
        id=item.id,
        code=item.code,
        name=item.name,
        channel=item.channel,
        plugin=item.plugin,
        message_type=item.message_type,
        body=item.body,
        approval_status=item.approval_status,
        dlt_reference=item.dlt_reference,
        vendors_using=item.vendors_using,
        messages_sent_month=item.messages_sent_month,
        variable_map=item.variable_map,
        meta=item.meta,
        submitted_at=item.submitted_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _tenant(item) -> TenantListItemResponse:
    return TenantListItemResponse(
        tenant_id=str(item.tenant_id),
        tenant_name=item.tenant_name,
        org_id=str(item.org_id),
        org_name=item.org_name,
        org_type=item.org_type,
        participation=item.participation,
        member_count=item.member_count,
        status=item.status,
    )


def _policy(item) -> PolicyItemResponse:
    return PolicyItemResponse(
        id=str(item.id),
        name=item.name,
        scope=item.scope,
        enforcement=item.enforcement,
        applies_to=item.applies_to,
        status=item.status,
        body=item.body,
    )


def _team(item) -> TeamMemberResponse:
    return TeamMemberResponse(
        id=str(item.id),
        user_id=str(item.user_id) if item.user_id else None,
        email=item.email,
        platform_role=item.platform_role,
        status=item.status,
        mfa_enabled=item.mfa_enabled,
        invited_at=item.invited_at,
        activated_at=item.activated_at,
    )


@router.get("/admin/tenants", response_model=TenantListResponse)
async def list_admin_tenants(
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
    q: Annotated[str | None, Query()] = None,
    org_type: Annotated[str | None, Query()] = None,
) -> TenantListResponse:
    user, _session, _credential = auth
    items = await service.list_tenants(caller_user_id=user.id, q=q, org_type=org_type)
    return TenantListResponse(items=[_tenant(item) for item in items])


@router.get("/admin/tenants/stats", response_model=TenantStatsResponse)
async def admin_tenant_stats(
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TenantStatsResponse:
    user, _session, _credential = auth
    stats = await service.tenant_stats(caller_user_id=user.id)
    return TenantStatsResponse(
        active=stats.active,
        suspended=stats.suspended,
        total=stats.total,
        individual=stats.individual,
        organisation=stats.organisation,
        vendor=stats.vendor,
    )


@router.post("/admin/tenants/{tenant_id}/suspend", response_model=TenantActionResponse)
async def suspend_admin_tenant(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TenantActionResponse:
    user, _session, _credential = auth
    result = await service.suspend_tenant(tenant_id=tenant_id, caller_user_id=user.id)
    return TenantActionResponse(**result)


@router.post("/admin/tenants/{tenant_id}/reinstate", response_model=TenantActionResponse)
async def reinstate_admin_tenant(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TenantActionResponse:
    user, _session, _credential = auth
    result = await service.reinstate_tenant(tenant_id=tenant_id, caller_user_id=user.id)
    return TenantActionResponse(**result)


@router.post("/admin/tenants", response_model=TenantActionResponse)
async def provision_admin_tenant(
    body: ProvisionTenantRequest,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TenantActionResponse:
    user, _session, _credential = auth
    result = await service.provision_tenant(
        caller_user_id=user.id,
        email=body.email,
        org_name=body.org_name,
        tenant_name=body.tenant_name,
    )
    return TenantActionResponse(**result)


@router.get("/admin/dashboard", response_model=DashboardResponse)
async def admin_dashboard(
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> DashboardResponse:
    user, _session, _credential = auth
    summary = await service.dashboard(caller_user_id=user.id)
    return DashboardResponse(
        tenant_count=summary.tenant_count,
        active_tenants=summary.active_tenants,
        vendor_count=summary.vendor_count,
        verified_vendors=summary.verified_vendors,
        user_count=summary.user_count,
        pending_plugin_reviews=summary.pending_plugin_reviews,
        pending_product_reviews=summary.pending_product_reviews,
        revenue_mtd=summary.revenue_mtd,
        recent_events=summary.recent_events,
    )


@router.get("/admin/analytics")
async def admin_analytics(
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
    tab: Annotated[str, Query()] = "users",
) -> dict:
    user, _session, _credential = auth
    return await service.analytics(caller_user_id=user.id, tab=tab)


@router.get("/admin/audit-log", response_model=AuditLogListResponse)
async def list_admin_audit_log(
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
    action: Annotated[str | None, Query()] = None,
    actor: Annotated[UUID | None, Query()] = None,
    from_dt: Annotated[datetime | None, Query(alias="from")] = None,
    to_dt: Annotated[datetime | None, Query(alias="to")] = None,
    q: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query()] = 1,
    page_size: Annotated[int, Query()] = 50,
) -> AuditLogListResponse:
    user, _session, _credential = auth
    result = await service.list_audit_log(
        caller_user_id=user.id,
        action=action,
        actor=actor,
        from_dt=from_dt,
        to_dt=to_dt,
        q=q,
        page=page,
        page_size=page_size,
    )
    return AuditLogListResponse(
        items=[
            AuditLogItemResponse(
                id=str(item.id),
                event_action=item.event_action,
                actor_user_id=str(item.actor_user_id) if item.actor_user_id else None,
                actor_email=item.actor_email,
                tenant_id=str(item.tenant_id) if item.tenant_id else None,
                payload=item.payload,
                created_at=item.created_at,
            )
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/admin/policies", response_model=PolicyListResponse)
async def list_admin_policies(
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> PolicyListResponse:
    user, _session, _credential = auth
    items = await service.list_policies(caller_user_id=user.id)
    return PolicyListResponse(items=[_policy(item) for item in items])


@router.post("/admin/policies", response_model=PolicyItemResponse)
async def create_admin_policy(
    body: CreatePolicyRequest,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> PolicyItemResponse:
    user, _session, _credential = auth
    item = await service.create_policy(
        caller_user_id=user.id,
        name=body.name,
        scope=body.scope,
        enforcement=body.enforcement,
        applies_to=body.applies_to,
        body=body.body,
    )
    return _policy(item)


@router.patch("/admin/policies/{policy_id}", response_model=PolicyItemResponse)
async def update_admin_policy(
    policy_id: UUID,
    body: UpdatePolicyRequest,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> PolicyItemResponse:
    user, _session, _credential = auth
    item = await service.update_policy(
        caller_user_id=user.id,
        policy_id=policy_id,
        name=body.name,
        status=body.status,
        enforcement=body.enforcement,
        applies_to=body.applies_to,
        body=body.body,
    )
    return _policy(item)


@router.post("/admin/policies/{policy_id}/toggle", response_model=PolicyItemResponse)
async def toggle_admin_policy(
    policy_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> PolicyItemResponse:
    user, _session, _credential = auth
    item = await service.toggle_policy_status(caller_user_id=user.id, policy_id=policy_id)
    return _policy(item)


@router.get("/admin/config", response_model=ConfigResponse)
async def get_admin_config(
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> ConfigResponse:
    user, _session, _credential = auth
    values = await service.get_config(caller_user_id=user.id)
    return ConfigResponse(values=values)


@router.patch("/admin/config", response_model=ConfigResponse)
async def patch_admin_config(
    body: PatchConfigRequest,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> ConfigResponse:
    user, _session, _credential = auth
    values = await service.patch_config(caller_user_id=user.id, updates=body.updates)
    return ConfigResponse(values=values)


@router.get("/admin/team", response_model=TeamListResponse)
async def list_admin_team(
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TeamListResponse:
    user, _session, _credential = auth
    items = await service.list_team(caller_user_id=user.id)
    return TeamListResponse(items=[_team(item) for item in items])


@router.post("/admin/team/invite", response_model=TeamMemberResponse)
async def invite_admin_team_member(
    body: InviteTeamRequest,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TeamMemberResponse:
    user, _session, _credential = auth
    item = await service.invite_team_member(
        caller_user_id=user.id,
        email=body.email,
        platform_role=body.platform_role,
        invite_note=body.invite_note,
    )
    return _team(item)


@router.patch("/admin/team/{member_id}/role", response_model=TeamMemberResponse)
async def update_admin_team_role(
    member_id: UUID,
    body: UpdateTeamRoleRequest,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TeamMemberResponse:
    user, _session, _credential = auth
    item = await service.update_team_role(
        caller_user_id=user.id,
        member_id=member_id,
        platform_role=body.platform_role,
    )
    return _team(item)


@router.post("/admin/team/{member_id}/suspend", response_model=TeamMemberResponse)
async def suspend_admin_team_member(
    member_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TeamMemberResponse:
    user, _session, _credential = auth
    item = await service.suspend_team_member(caller_user_id=user.id, member_id=member_id)
    return _team(item)


@router.post("/admin/team/{member_id}/reactivate", response_model=TeamMemberResponse)
async def reactivate_admin_team_member(
    member_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TeamMemberResponse:
    user, _session, _credential = auth
    item = await service.reactivate_team_member(caller_user_id=user.id, member_id=member_id)
    return _team(item)


@router.post("/admin/team/{member_id}/reset-mfa", response_model=TeamActionResponse)
async def reset_admin_team_mfa(
    member_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TeamActionResponse:
    user, _session, _credential = auth
    result = await service.reset_team_mfa(caller_user_id=user.id, member_id=member_id)
    return TeamActionResponse(**result)


@router.post("/admin/team/super-admin/transfer", response_model=TeamActionResponse)
async def transfer_admin_super_admin(
    body: TransferSuperAdminRequest,
    auth: CurrentAuthDep,
    service: Annotated[AdminOpsService, Depends(get_admin_ops_service)],
) -> TeamActionResponse:
    user, _session, _credential = auth
    result = await service.transfer_super_admin(
        caller_user_id=user.id,
        recipient_member_id=UUID(body.recipient_member_id),
        password=body.password,
    )
    return TeamActionResponse(**result)


@router.get(
    "/admin/communications/templates",
    response_model=CommunicationTemplateListResponse,
)
async def list_communication_templates(
    auth: CurrentAuthDep,
    service: Annotated[CommunicationsService, Depends(get_communications_service)],
    status: Annotated[str | None, Query()] = None,
) -> CommunicationTemplateListResponse:
    user, _session, _credential = auth
    items, summary = await service.list_templates(
        caller_user_id=user.id, status_filter=status
    )
    return CommunicationTemplateListResponse(
        items=[_comm_template(item) for item in items],
        summary=CommunicationTemplateSummary(
            live=summary.live,
            pending=summary.pending,
            sms=summary.sms,
            whatsapp=summary.whatsapp,
            email=summary.email,
            inapp=summary.inapp,
        ),
    )


@router.get(
    "/admin/communications/templates/{template_id}",
    response_model=CommunicationTemplateItem,
)
async def get_communication_template(
    template_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommunicationsService, Depends(get_communications_service)],
) -> CommunicationTemplateItem:
    user, _session, _credential = auth
    item = await service.get_template(caller_user_id=user.id, template_id=template_id)
    return _comm_template(item)


@router.post(
    "/admin/communications/templates",
    response_model=CommunicationTemplateItem,
    status_code=201,
)
async def create_communication_template(
    body: CreateCommunicationTemplateRequest,
    auth: CurrentAuthDep,
    service: Annotated[CommunicationsService, Depends(get_communications_service)],
) -> CommunicationTemplateItem:
    user, _session, _credential = auth
    item = await service.create_template(
        caller_user_id=user.id,
        name=body.name,
        channel=body.channel,
        plugin=body.plugin,
        message_type=body.message_type,
        body=body.body,
        code=body.code,
        buttons=body.buttons,
    )
    return _comm_template(item)


@router.get("/admin/communications/dlt")
async def communication_dlt_center(
    auth: CurrentAuthDep,
    service: Annotated[CommunicationsService, Depends(get_communications_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.dlt_center(caller_user_id=user.id)


@router.get(
    "/admin/communications/usage",
    response_model=CommunicationUsageListResponse,
)
async def communication_usage_logs(
    auth: CurrentAuthDep,
    service: Annotated[CommunicationsService, Depends(get_communications_service)],
) -> CommunicationUsageListResponse:
    user, _session, _credential = auth
    items, summary = await service.usage_logs(caller_user_id=user.id)
    return CommunicationUsageListResponse(
        items=[
            CommunicationUsageItem(
                id=item.id,
                occurred_at=item.occurred_at,
                vendor_name=item.vendor_name,
                channel=item.channel,
                template_code=item.template_code,
                template_name=item.template_name,
                audience=item.audience,
                sent=item.sent,
                delivered=item.delivered,
                status=item.status,
            )
            for item in items
        ],
        summary=CommunicationUsageSummary(
            messages_this_month=summary.messages_this_month,
            sms_sent=summary.sms_sent,
            whatsapp_sent=summary.whatsapp_sent,
            email_sent=summary.email_sent,
            inapp_sent=summary.inapp_sent,
            failed_or_opted_out=summary.failed_or_opted_out,
            warning=summary.warning,
        ),
    )


@router.get(
    "/admin/communications/consent",
    response_model=CommunicationConsentResponse,
)
async def communication_consent_registry(
    auth: CurrentAuthDep,
    service: Annotated[CommunicationsService, Depends(get_communications_service)],
) -> CommunicationConsentResponse:
    user, _session, _credential = auth
    data = await service.consent_registry(caller_user_id=user.id)
    return CommunicationConsentResponse(**data)


@router.get("/admin/settlement/dashboard")
async def settlement_dashboard(
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
    period: Annotated[str, Query()] = "today",
) -> dict:
    user, _session, _credential = auth
    return await service.dashboard(caller_user_id=user.id, period=period)


@router.get("/admin/settlement/returns")
async def settlement_return_queue(
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.return_queue(caller_user_id=user.id)


@router.post("/admin/settlement/returns/{case_id}/resolve")
async def settlement_resolve_return(
    case_id: UUID,
    body: ResolveSettlementReturnRequest,
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.resolve_return(
        caller_user_id=user.id,
        case_id=case_id,
        outcome=body.outcome,
        amount=body.amount,
        reason=body.reason,
    )


@router.get("/admin/settlement/ledger")
async def settlement_vendor_ledger(
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
    vendor: Annotated[str | None, Query()] = None,
) -> dict:
    user, _session, _credential = auth
    return await service.vendor_ledger(caller_user_id=user.id, vendor_name=vendor)


@router.get("/admin/settlement/tds")
async def settlement_tds_gst(
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.tds_gst(caller_user_id=user.id)


@router.get("/admin/settlement/escrow")
async def settlement_escrow(
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.escrow(caller_user_id=user.id)


@router.get("/admin/settlement/faults")
async def settlement_faults(
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.faults(caller_user_id=user.id)


@router.get("/admin/settlement/fraud")
async def settlement_fraud(
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.fraud_signals(caller_user_id=user.id)


@router.post("/admin/settlement/fraud/{signal_id}/action")
async def settlement_fraud_action(
    signal_id: UUID,
    body: SettlementFraudActionRequest,
    auth: CurrentAuthDep,
    service: Annotated[SettlementService, Depends(get_settlement_service)],
) -> dict:
    user, _session, _credential = auth
    return await service.act_on_fraud(
        caller_user_id=user.id, signal_id=signal_id, action=body.action
    )
