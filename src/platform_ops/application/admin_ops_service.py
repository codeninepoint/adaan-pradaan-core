"""Platform operator admin control-plane: tenants, dashboard, audit, policies, config, team."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.ports.keycloak import KeycloakClient
from identity.domain.security import utcnow
from identity.infrastructure.models import (
    AuditLogRow,
    CredentialRow,
    IdentityRealmRow,
    SessionRow,
    UserRow,
)
from marketplace.application.access import require_platform_operator
from marketplace.infrastructure.models import (
    OfferingRow,
    OrderLineRow,
    OrderRow,
    PluginRow,
    PluginVersionRow,
    ProductRow,
)
from platform_ops.application.team_bootstrap import upsert_operator_team_member
from platform_ops.infrastructure.models import (
    PlatformConfigRow,
    PlatformPolicyRow,
    PlatformTeamMemberRow,
)
from shared.domain.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from tenant.infrastructure.models import (
    OrgMembershipRow,
    OrganizationRow,
    TenantMembershipRow,
    TenantRow,
)
from vendor.infrastructure.models import VendorProfileRow

PLATFORM_TEAM_ROLES = frozenset(
    {
        "super_admin",
        "platform_admin",
        "finance_manager",
        "content_moderator",
        "kyc_reviewer",
        "support_agent",
        # Aliases accepted by invite/role APIs (normalized in UI ROLE_ALIASES)
        "catalog_manager",
        "support",
    }
)


@dataclass(frozen=True, slots=True)
class TenantListItem:
    tenant_id: UUID
    tenant_name: str
    org_id: UUID
    org_name: str
    org_type: str
    participation: str
    member_count: int
    status: str


@dataclass(frozen=True, slots=True)
class TenantStats:
    active: int
    suspended: int
    total: int
    individual: int = 0
    organisation: int = 0
    vendor: int = 0


@dataclass(frozen=True, slots=True)
class AuditLogItem:
    id: UUID
    event_action: str
    actor_user_id: UUID | None
    actor_email: str | None
    tenant_id: UUID | None
    payload: dict
    created_at: str


@dataclass(frozen=True, slots=True)
class AuditLogListResult:
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class PolicyItem:
    id: UUID
    name: str
    scope: str
    enforcement: str
    applies_to: str
    status: str
    body: dict


@dataclass(frozen=True, slots=True)
class TeamMemberItem:
    id: UUID
    user_id: UUID | None
    email: str
    platform_role: str
    status: str
    mfa_enabled: bool
    invited_at: str
    activated_at: str | None


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    tenant_count: int
    active_tenants: int
    vendor_count: int
    verified_vendors: int
    user_count: int
    pending_plugin_reviews: int
    pending_product_reviews: int
    revenue_mtd: float
    recent_events: list[dict] = field(default_factory=list)


class AdminOpsService:
    def __init__(self, session: AsyncSession, keycloak: KeycloakClient) -> None:
        self._session = session
        self._keycloak = keycloak

    async def list_tenants(
        self,
        *,
        caller_user_id: UUID,
        q: str | None = None,
        org_type: str | None = None,
    ) -> list[TenantListItem]:
        await require_platform_operator(self._session, caller_user_id)
        stmt = (
            select(TenantRow, OrganizationRow)
            .join(OrganizationRow, OrganizationRow.id == TenantRow.organization_id)
            .where(OrganizationRow.is_platform_operator.is_(False))
            .order_by(TenantRow.created_at.desc())
        )
        if org_type:
            stmt = stmt.where(OrganizationRow.org_type == org_type)
        if q and q.strip():
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(TenantRow.name).like(pattern),
                    func.lower(OrganizationRow.name).like(pattern),
                    func.lower(OrganizationRow.slug).like(pattern),
                )
            )
        rows = (await self._session.execute(stmt)).all()
        if not rows:
            return []
        tenant_ids = [tenant.id for tenant, _org in rows]
        member_counts = dict(
            (
                await self._session.execute(
                    select(TenantMembershipRow.tenant_id, func.count(TenantMembershipRow.id))
                    .where(
                        TenantMembershipRow.tenant_id.in_(tenant_ids),
                        TenantMembershipRow.status == "active",
                    )
                    .group_by(TenantMembershipRow.tenant_id)
                )
            ).all()
        )
        return [
            TenantListItem(
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                org_id=org.id,
                org_name=org.name,
                org_type=org.org_type,
                participation=org.participation,
                member_count=int(member_counts.get(tenant.id, 0)),
                status=tenant.status if tenant.status != "active" else org.status,
            )
            for tenant, org in rows
        ]

    async def tenant_stats(self, *, caller_user_id: UUID) -> TenantStats:
        await require_platform_operator(self._session, caller_user_id)

        async def _count_status(status: str) -> int:
            return int(
                (
                    await self._session.execute(
                        select(func.count(TenantRow.id))
                        .join(OrganizationRow, OrganizationRow.id == TenantRow.organization_id)
                        .where(
                            OrganizationRow.is_platform_operator.is_(False),
                            TenantRow.status == status,
                        )
                    )
                ).scalar_one()
            )

        async def _count_type(*, org_type: str | None = None, participation: str | None = None) -> int:
            stmt = (
                select(func.count(TenantRow.id))
                .join(OrganizationRow, OrganizationRow.id == TenantRow.organization_id)
                .where(OrganizationRow.is_platform_operator.is_(False))
            )
            if org_type is not None:
                stmt = stmt.where(OrganizationRow.org_type == org_type)
            if participation is not None:
                stmt = stmt.where(OrganizationRow.participation == participation)
            return int((await self._session.execute(stmt)).scalar_one())

        active = await _count_status("active")
        suspended = await _count_status("suspended")
        return TenantStats(
            active=active,
            suspended=suspended,
            total=active + suspended,
            individual=await _count_type(org_type="individual"),
            organisation=await _count_type(org_type="organization"),
            vendor=await _count_type(participation="vendor"),
        )

    async def suspend_tenant(self, *, tenant_id: UUID, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        tenant = await self._session.get(TenantRow, tenant_id)
        if tenant is None:
            raise NotFoundError("tenant not found")
        org = await self._session.get(OrganizationRow, tenant.organization_id)
        if org is None or org.is_platform_operator:
            raise ForbiddenError("cannot suspend platform operator tenant")
        if tenant.status == "suspended":
            raise ConflictError("already suspended")
        tenant.status = "suspended"
        org.status = "suspended"
        revoked = await self._revoke_tenant_sessions(tenant_id, caller_user_id)
        await self._audit(
            "tenant.suspended",
            caller_user_id,
            {"tenant_id": str(tenant_id), "sessions_revoked": revoked},
        )
        await self._session.commit()
        return {"tenant_id": str(tenant_id), "status": tenant.status, "sessions_revoked": revoked}

    async def reinstate_tenant(self, *, tenant_id: UUID, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        tenant = await self._session.get(TenantRow, tenant_id)
        if tenant is None:
            raise NotFoundError("tenant not found")
        org = await self._session.get(OrganizationRow, tenant.organization_id)
        if org is None:
            raise NotFoundError("tenant not found")
        if tenant.status != "suspended":
            raise ConflictError("tenant is not suspended")
        tenant.status = "active"
        org.status = "active"
        await self._audit("tenant.reinstated", caller_user_id, {"tenant_id": str(tenant_id)})
        await self._session.commit()
        return {"tenant_id": str(tenant_id), "status": tenant.status}

    async def provision_tenant(
        self,
        *,
        caller_user_id: UUID,
        email: str,
        org_name: str | None = None,
        tenant_name: str = "default",
    ) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        normalized = email.strip().lower()
        if not normalized:
            raise ValidationError("email is required")
        user = (
            await self._session.execute(select(UserRow).where(UserRow.normalized_email == normalized))
        ).scalar_one_or_none()
        if user is None:
            raise NotFoundError("user not found")
        existing = (
            await self._session.execute(
                select(TenantMembershipRow, TenantRow, OrganizationRow)
                .join(TenantRow, TenantRow.id == TenantMembershipRow.tenant_id)
                .join(OrganizationRow, OrganizationRow.id == TenantRow.organization_id)
                .where(
                    TenantMembershipRow.user_id == user.id,
                    TenantMembershipRow.status == "active",
                    OrganizationRow.is_platform_operator.is_(False),
                )
                .limit(1)
            )
        ).first()
        if existing is not None:
            _membership, tenant, org = existing
            return {
                "tenant_id": str(tenant.id),
                "org_id": str(org.id),
                "status": tenant.status,
                "created": False,
            }

        slug_base = normalized.split("@")[0].replace(".", "-")[:32] or "org"
        org = OrganizationRow(
            id=uuid.uuid4(),
            name=org_name or f"{user.display_name} organization",
            slug=f"{slug_base}-{str(uuid.uuid4())[:8]}",
            org_type="organization",
            participation="consumer",
            status="active",
        )
        self._session.add(org)
        await self._session.flush()
        self._session.add(
            OrgMembershipRow(
                id=uuid.uuid4(),
                organization_id=org.id,
                user_id=user.id,
                role="owner",
                status="active",
            )
        )
        tenant = TenantRow(
            id=uuid.uuid4(),
            organization_id=org.id,
            name=tenant_name,
            slug=f"{slug_base}-default",
            status="active",
        )
        self._session.add(tenant)
        await self._session.flush()
        self._session.add(
            TenantMembershipRow(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
                status="active",
            )
        )
        await self._audit(
            "tenant.provisioned",
            caller_user_id,
            {"tenant_id": str(tenant.id), "user_id": str(user.id), "email": normalized},
        )
        await self._session.commit()
        return {
            "tenant_id": str(tenant.id),
            "org_id": str(org.id),
            "status": tenant.status,
            "created": True,
        }

    async def dashboard(self, *, caller_user_id: UUID) -> DashboardSummary:
        await require_platform_operator(self._session, caller_user_id)
        tenant_count = int(
            (
                await self._session.execute(
                    select(func.count(TenantRow.id))
                    .join(OrganizationRow, OrganizationRow.id == TenantRow.organization_id)
                    .where(OrganizationRow.is_platform_operator.is_(False))
                )
            ).scalar_one()
        )
        active_tenants = int(
            (
                await self._session.execute(
                    select(func.count(TenantRow.id))
                    .join(OrganizationRow, OrganizationRow.id == TenantRow.organization_id)
                    .where(
                        OrganizationRow.is_platform_operator.is_(False),
                        TenantRow.status == "active",
                    )
                )
            ).scalar_one()
        )
        vendor_count = int(
            (await self._session.execute(select(func.count(VendorProfileRow.id)))).scalar_one()
        )
        verified_vendors = int(
            (
                await self._session.execute(
                    select(func.count(VendorProfileRow.id)).where(VendorProfileRow.status == "verified")
                )
            ).scalar_one()
        )
        user_count = int(
            (await self._session.execute(select(func.count(UserRow.id)))).scalar_one()
        )
        pending_plugin_reviews = int(
            (
                await self._session.execute(
                    select(func.count(PluginVersionRow.id)).where(
                        PluginVersionRow.status == "pending_review"
                    )
                )
            ).scalar_one()
        )
        pending_product_reviews = int(
            (
                await self._session.execute(
                    select(func.count(ProductRow.id)).where(ProductRow.pa_status == "pending_review")
                )
            ).scalar_one()
        )
        month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        revenue_mtd = float(
            (
                await self._session.execute(
                    select(func.coalesce(func.sum(OrderLineRow.unit_price * OrderLineRow.quantity), 0))
                    .select_from(OrderLineRow)
                    .join(OrderRow, OrderRow.id == OrderLineRow.order_id)
                    .where(OrderRow.created_at >= month_start)
                )
            ).scalar_one()
        )
        recent = (
            await self._session.execute(
                select(AuditLogRow)
                .order_by(AuditLogRow.created_at.desc())
                .limit(8)
            )
        ).scalars().all()
        recent_events = [
            {
                "action": row.event_action,
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in recent
        ]
        return DashboardSummary(
            tenant_count=tenant_count,
            active_tenants=active_tenants,
            vendor_count=vendor_count,
            verified_vendors=verified_vendors,
            user_count=user_count,
            pending_plugin_reviews=pending_plugin_reviews,
            pending_product_reviews=pending_product_reviews,
            revenue_mtd=revenue_mtd,
            recent_events=recent_events,
        )

    async def analytics(self, *, caller_user_id: UUID, tab: str) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        if tab not in ("users", "vendors", "plugins", "revenue"):
            raise ValidationError("tab must be users, vendors, plugins, or revenue")
        if tab == "users":
            total = int(
                (await self._session.execute(select(func.count(UserRow.id)))).scalar_one()
            )
            active = int(
                (
                    await self._session.execute(
                        select(func.count(UserRow.id)).where(UserRow.status == "active")
                    )
                ).scalar_one()
            )
            return {"tab": tab, "total_users": total, "active_users": active}
        if tab == "vendors":
            rows = (
                await self._session.execute(
                    select(VendorProfileRow.status, func.count(VendorProfileRow.id)).group_by(
                        VendorProfileRow.status
                    )
                )
            ).all()
            return {"tab": tab, "by_status": {status: int(count) for status, count in rows}}
        if tab == "plugins":
            rows = (
                await self._session.execute(
                    select(PluginVersionRow.status, func.count(PluginVersionRow.id)).group_by(
                        PluginVersionRow.status
                    )
                )
            ).all()
            plugin_total = int(
                (await self._session.execute(select(func.count(PluginRow.id)))).scalar_one()
            )
            return {
                "tab": tab,
                "total_plugins": plugin_total,
                "versions_by_status": {status: int(count) for status, count in rows},
            }
        month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        revenue_mtd = float(
            (
                await self._session.execute(
                    select(func.coalesce(func.sum(OrderLineRow.unit_price * OrderLineRow.quantity), 0))
                    .select_from(OrderLineRow)
                    .join(OrderRow, OrderRow.id == OrderLineRow.order_id)
                    .where(OrderRow.created_at >= month_start)
                )
            ).scalar_one()
        )
        order_count = int(
            (
                await self._session.execute(
                    select(func.count(OrderRow.id)).where(OrderRow.created_at >= month_start)
                )
            ).scalar_one()
        )
        return {"tab": tab, "revenue_mtd": revenue_mtd, "orders_mtd": order_count}

    async def list_audit_log(
        self,
        *,
        caller_user_id: UUID,
        action: str | None = None,
        actor: UUID | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditLogListResult:
        await require_platform_operator(self._session, caller_user_id)
        if page < 1:
            raise ValidationError("page must be >= 1")
        if page_size < 1 or page_size > 200:
            raise ValidationError("page_size must be 1..200")
        stmt = select(AuditLogRow).order_by(AuditLogRow.created_at.desc())
        if action:
            stmt = stmt.where(AuditLogRow.event_action == action)
        if actor is not None:
            stmt = stmt.where(AuditLogRow.actor_user_id == actor)
        if from_dt is not None:
            stmt = stmt.where(AuditLogRow.created_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(AuditLogRow.created_at <= to_dt)
        if q and q.strip():
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(func.lower(AuditLogRow.event_action).like(pattern))
        rows = (await self._session.execute(stmt)).scalars().all()
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        actor_ids = {row.actor_user_id for row in page_rows if row.actor_user_id}
        emails: dict[UUID, str] = {}
        if actor_ids:
            users = (
                await self._session.execute(select(UserRow).where(UserRow.id.in_(actor_ids)))
            ).scalars().all()
            emails = {user.id: user.email for user in users}
        items = [
            AuditLogItem(
                id=row.id,
                event_action=row.event_action,
                actor_user_id=row.actor_user_id,
                actor_email=emails.get(row.actor_user_id) if row.actor_user_id else None,
                tenant_id=row.tenant_id,
                payload=row.payload_json or {},
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
            for row in page_rows
        ]
        return AuditLogListResult(items=items, total=total, page=page, page_size=page_size)

    async def list_policies(self, *, caller_user_id: UUID) -> list[PolicyItem]:
        await require_platform_operator(self._session, caller_user_id)
        rows = (
            await self._session.execute(
                select(PlatformPolicyRow).order_by(PlatformPolicyRow.name.asc())
            )
        ).scalars().all()
        return [self._policy_item(row) for row in rows]

    async def create_policy(
        self,
        *,
        caller_user_id: UUID,
        name: str,
        scope: str,
        enforcement: str,
        applies_to: str,
        body: dict | None = None,
    ) -> PolicyItem:
        await require_platform_operator(self._session, caller_user_id)
        cleaned_name = name.strip()
        if not cleaned_name or not scope.strip():
            raise ValidationError("name and scope are required")
        row = PlatformPolicyRow(
            id=uuid.uuid4(),
            name=cleaned_name,
            scope=scope.strip(),
            enforcement=enforcement.strip() or "mandatory",
            applies_to=applies_to.strip(),
            status="enforced",
            body=body or {},
        )
        self._session.add(row)
        await self._audit("policy.created", caller_user_id, {"policy_id": str(row.id), "name": cleaned_name})
        await self._session.commit()
        return self._policy_item(row)

    async def update_policy(
        self,
        *,
        caller_user_id: UUID,
        policy_id: UUID,
        name: str | None = None,
        status: str | None = None,
        enforcement: str | None = None,
        applies_to: str | None = None,
        body: dict | None = None,
    ) -> PolicyItem:
        await require_platform_operator(self._session, caller_user_id)
        row = await self._session.get(PlatformPolicyRow, policy_id)
        if row is None:
            raise NotFoundError("policy not found")
        if name is not None and name.strip():
            row.name = name.strip()
        if status is not None:
            row.status = status.strip()
        if enforcement is not None:
            row.enforcement = enforcement.strip()
        if applies_to is not None:
            row.applies_to = applies_to.strip()
        if body is not None:
            row.body = body
        await self._audit("policy.updated", caller_user_id, {"policy_id": str(row.id)})
        await self._session.commit()
        return self._policy_item(row)

    async def toggle_policy_status(
        self, *, caller_user_id: UUID, policy_id: UUID
    ) -> PolicyItem:
        await require_platform_operator(self._session, caller_user_id)
        row = await self._session.get(PlatformPolicyRow, policy_id)
        if row is None:
            raise NotFoundError("policy not found")
        row.status = "disabled" if row.status == "enforced" else "enforced"
        await self._audit(
            "policy.status_toggled",
            caller_user_id,
            {"policy_id": str(row.id), "status": row.status},
        )
        await self._session.commit()
        return self._policy_item(row)

    async def get_config(self, *, caller_user_id: UUID) -> dict[str, object]:
        await require_platform_operator(self._session, caller_user_id)
        rows = (await self._session.execute(select(PlatformConfigRow))).scalars().all()
        if not rows:
            return self._default_config()
        return {row.key: row.value for row in rows}

    async def patch_config(
        self, *, caller_user_id: UUID, updates: dict[str, object]
    ) -> dict[str, object]:
        await require_platform_operator(self._session, caller_user_id)
        if not updates:
            raise ValidationError("updates required")
        for key, value in updates.items():
            row = await self._session.get(PlatformConfigRow, key)
            if row is None:
                row = PlatformConfigRow(key=key, value=value, updated_by=caller_user_id)
                self._session.add(row)
            else:
                row.value = value
                row.updated_by = caller_user_id
                row.updated_at = utcnow()
        await self._audit("config.updated", caller_user_id, {"keys": list(updates.keys())})
        await self._session.commit()
        return await self.get_config(caller_user_id=caller_user_id)

    async def list_team(self, *, caller_user_id: UUID) -> list[TeamMemberItem]:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_caller_team_row(caller_user_id)
        rows = (
            await self._session.execute(
                select(PlatformTeamMemberRow).order_by(PlatformTeamMemberRow.invited_at.desc())
            )
        ).scalars().all()
        return [self._team_item(row) for row in rows]

    async def invite_team_member(
        self,
        *,
        caller_user_id: UUID,
        email: str,
        platform_role: str,
        invite_note: str = "",
    ) -> TeamMemberItem:
        await require_platform_operator(self._session, caller_user_id)
        normalized = email.strip().lower()
        if not normalized:
            raise ValidationError("email is required")
        if platform_role not in PLATFORM_TEAM_ROLES:
            raise ValidationError("invalid platform_role")
        if platform_role == "super_admin":
            raise ForbiddenError("cannot invite super_admin directly")
        user = (
            await self._session.execute(select(UserRow).where(UserRow.normalized_email == normalized))
        ).scalar_one_or_none()
        row = await upsert_operator_team_member(
            self._session,
            email=normalized,
            user_id=user.id if user else None,
            platform_role=platform_role,
            invited_by=caller_user_id,
            status="active" if user is not None else "invited",
        )
        row.invite_note = invite_note.strip()
        if user is not None:
            await self._ensure_operator_org_membership(user.id)
        await self._audit(
            "team.invited",
            caller_user_id,
            {"email": normalized, "platform_role": platform_role, "member_id": str(row.id)},
        )
        await self._session.commit()
        return self._team_item(row)

    async def update_team_role(
        self, *, caller_user_id: UUID, member_id: UUID, platform_role: str
    ) -> TeamMemberItem:
        await require_platform_operator(self._session, caller_user_id)
        if platform_role not in PLATFORM_TEAM_ROLES:
            raise ValidationError("invalid platform_role")
        if platform_role == "super_admin":
            raise ForbiddenError("use super-admin transfer to assign super_admin")
        row = await self._session.get(PlatformTeamMemberRow, member_id)
        if row is None:
            raise NotFoundError("team member not found")
        if row.platform_role == "super_admin":
            raise ForbiddenError("cannot change super_admin role directly")
        row.platform_role = platform_role
        await self._audit(
            "team.role_changed",
            caller_user_id,
            {"member_id": str(member_id), "platform_role": platform_role},
        )
        await self._session.commit()
        return self._team_item(row)

    async def suspend_team_member(self, *, caller_user_id: UUID, member_id: UUID) -> TeamMemberItem:
        await require_platform_operator(self._session, caller_user_id)
        row = await self._require_team_member(member_id)
        if row.platform_role == "super_admin":
            raise ForbiddenError("cannot suspend super_admin")
        if row.status == "suspended":
            raise ConflictError("already suspended")
        row.status = "suspended"
        if row.user_id is not None:
            await self._revoke_user_sessions(row.user_id, caller_user_id)
        await self._audit("team.suspended", caller_user_id, {"member_id": str(member_id)})
        await self._session.commit()
        return self._team_item(row)

    async def reactivate_team_member(
        self, *, caller_user_id: UUID, member_id: UUID
    ) -> TeamMemberItem:
        await require_platform_operator(self._session, caller_user_id)
        row = await self._require_team_member(member_id)
        if row.status != "suspended":
            raise ConflictError("member is not suspended")
        row.status = "active"
        if row.activated_at is None:
            row.activated_at = utcnow()
        await self._audit("team.reactivated", caller_user_id, {"member_id": str(member_id)})
        await self._session.commit()
        return self._team_item(row)

    async def reset_team_mfa(self, *, caller_user_id: UUID, member_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        row = await self._require_team_member(member_id)
        if row.user_id is None:
            raise ConflictError("invited member has no user account yet")
        user = await self._session.get(UserRow, row.user_id)
        if user is None:
            raise NotFoundError("user not found")
        cred = (
            await self._session.execute(
                select(CredentialRow, IdentityRealmRow)
                .join(IdentityRealmRow, IdentityRealmRow.id == CredentialRow.identity_realm_id)
                .where(CredentialRow.principal_id == user.principal_id)
                .limit(1)
            )
        ).first()
        if cred is not None:
            credential, realm = cred
            await self._keycloak.reset_mfa(realm.realm_name, credential.keycloak_subject)
            await self._revoke_user_sessions(user.id, caller_user_id)
        else:
            await self._audit(
                "team.mfa_reset_stub",
                caller_user_id,
                {"member_id": str(member_id), "user_id": str(user.id)},
            )
        row.mfa_enabled = False
        await self._audit("team.mfa_reset", caller_user_id, {"member_id": str(member_id)})
        await self._session.commit()
        return {"member_id": str(member_id), "status": "mfa_reset_required"}

    async def transfer_super_admin(
        self,
        *,
        caller_user_id: UUID,
        recipient_member_id: UUID,
        password: str,
    ) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        caller_row = await self._caller_team_row(caller_user_id)
        if caller_row is None or caller_row.platform_role != "super_admin":
            raise ForbiddenError("only super_admin may transfer super_admin role")
        recipient = await self._require_team_member(recipient_member_id)
        if recipient.status != "active":
            raise ConflictError("recipient must be an active team member")
        if recipient.user_id is None:
            raise ConflictError("recipient must have an activated user account")
        caller_user = await self._session.get(UserRow, caller_user_id)
        if caller_user is None:
            raise NotFoundError("caller not found")
        cred = (
            await self._session.execute(
                select(CredentialRow, IdentityRealmRow)
                .join(IdentityRealmRow, IdentityRealmRow.id == CredentialRow.identity_realm_id)
                .where(CredentialRow.principal_id == caller_user.principal_id)
                .limit(1)
            )
        ).first()
        if cred is None:
            raise NotFoundError("credential not found")
        _credential, realm = cred
        try:
            await self._keycloak.authenticate(realm.realm_name, caller_user.email, password)
        except ValueError as exc:
            raise UnauthorizedError("invalid password") from exc
        caller_row.platform_role = "platform_admin"
        recipient.platform_role = "super_admin"
        await self._audit(
            "team.super_admin_transferred",
            caller_user_id,
            {
                "from_member_id": str(caller_row.id),
                "to_member_id": str(recipient.id),
            },
        )
        await self._session.commit()
        return {
            "from_member_id": str(caller_row.id),
            "to_member_id": str(recipient.id),
            "caller_role": caller_row.platform_role,
            "recipient_role": recipient.platform_role,
        }

    async def _ensure_caller_team_row(self, caller_user_id: UUID) -> None:
        user = await self._session.get(UserRow, caller_user_id)
        if user is None:
            return
        await upsert_operator_team_member(
            self._session,
            email=user.email,
            user_id=user.id,
            platform_role="platform_admin",
            status="active",
        )

    async def _caller_team_row(self, caller_user_id: UUID) -> PlatformTeamMemberRow | None:
        user = await self._session.get(UserRow, caller_user_id)
        if user is None:
            return None
        return (
            await self._session.execute(
                select(PlatformTeamMemberRow).where(
                    PlatformTeamMemberRow.email == user.email.lower()
                )
            )
        ).scalar_one_or_none()

    async def _require_team_member(self, member_id: UUID) -> PlatformTeamMemberRow:
        row = await self._session.get(PlatformTeamMemberRow, member_id)
        if row is None:
            raise NotFoundError("team member not found")
        return row

    async def _ensure_operator_org_membership(self, user_id: UUID) -> None:
        operator_org = (
            await self._session.execute(
                select(OrganizationRow).where(OrganizationRow.is_platform_operator.is_(True)).limit(1)
            )
        ).scalar_one_or_none()
        if operator_org is None:
            return
        existing = (
            await self._session.execute(
                select(OrgMembershipRow.id).where(
                    OrgMembershipRow.organization_id == operator_org.id,
                    OrgMembershipRow.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(
                OrgMembershipRow(
                    id=uuid.uuid4(),
                    organization_id=operator_org.id,
                    user_id=user_id,
                    role="member",
                    status="active",
                )
            )

    async def _revoke_tenant_sessions(self, tenant_id: UUID, actor_user_id: UUID) -> int:
        user_ids = (
            await self._session.execute(
                select(TenantMembershipRow.user_id).where(
                    TenantMembershipRow.tenant_id == tenant_id,
                    TenantMembershipRow.status == "active",
                )
            )
        ).scalars().all()
        revoked = 0
        for user_id in user_ids:
            revoked += await self._revoke_user_sessions(user_id, actor_user_id)
        return revoked

    async def _revoke_user_sessions(self, user_id: UUID, actor_user_id: UUID) -> int:
        del actor_user_id
        sessions = (
            await self._session.execute(
                select(SessionRow).where(SessionRow.user_id == user_id, SessionRow.status == "active")
            )
        ).scalars().all()
        now = utcnow()
        for session in sessions:
            session.status = "revoked"
            session.revoked_at = now
            session.refresh_token_hash = None
        return len(sessions)

    async def _audit(self, action: str, actor_user_id: UUID, payload: dict) -> None:
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action=action,
                actor_user_id=actor_user_id,
                tenant_id=None,
                payload_json=payload,
            )
        )

    @staticmethod
    def _policy_item(row: PlatformPolicyRow) -> PolicyItem:
        return PolicyItem(
            id=row.id,
            name=row.name,
            scope=row.scope,
            enforcement=row.enforcement,
            applies_to=row.applies_to,
            status=row.status,
            body=row.body or {},
        )

    @staticmethod
    def _team_item(row: PlatformTeamMemberRow) -> TeamMemberItem:
        return TeamMemberItem(
            id=row.id,
            user_id=row.user_id,
            email=row.email,
            platform_role=row.platform_role,
            status=row.status,
            mfa_enabled=row.mfa_enabled,
            invited_at=row.invited_at.isoformat() if row.invited_at else "",
            activated_at=row.activated_at.isoformat() if row.activated_at else None,
        )

    @staticmethod
    def _default_config() -> dict[str, object]:
        return {
            "platform_name": "AdanPradan FairShare",
            "commission_rate_pct": 10,
            "settlement_cycle": "weekly_t7",
            "plugin_review_sla_days": 3,
            "webhook_hmac_key": "",
            "product_content_review_required": True,
        }
