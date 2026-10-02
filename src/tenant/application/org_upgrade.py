from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.infrastructure.models import PrincipalRoleRow, RoleRow
from authz.infrastructure.seed import seed_tenant_system_roles
from identity.application.ports.keycloak import KeycloakClient
from identity.domain.security import utcnow
from identity.infrastructure.keycloak_admin import KeycloakUnavailable
from identity.infrastructure.models import AuditLogRow, IdentityRealmRow
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shared.settings import settings
from tenant.infrastructure.models import (
    OrganizationRegistrationRequestRow,
    OrganizationRow,
    OrgMembershipRow,
    ProjectRow,
    TenantMembershipRow,
    TenantRow,
)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class OrgRegisterResult:
    request_id: UUID
    status: str
    org_id: UUID
    estimated_ms: int
    keycloak_realm_ref: str | None = None
    realm_url: str | None = None
    error_message: str | None = None


class OrgUpgradeService:
    """J07 — individual org → organization upgrade.

    `TENANT_WORKFLOW_MODE=inline` finishes the pipeline in this request (tests).
    `temporal` commits `processing` and hands the pipeline to OrgUpgradeWorkflow.
    """

    def __init__(self, session: AsyncSession, keycloak: KeycloakClient) -> None:
        self._session = session
        self._keycloak = keycloak

    async def submit(
        self,
        *,
        requester_user_id: UUID,
        requester_principal_id: UUID,
        name: str,
        slug: str,
        contact_name: str,
        contact_email: str,
        country: str,
    ) -> OrgRegisterResult:
        name = name.strip()
        slug = slug.strip().lower()
        contact_name = contact_name.strip()
        contact_email = contact_email.strip().lower()
        country = country.strip().upper()

        if not name or len(name) > 255:
            raise ValidationError("invalid organization name")
        if not _SLUG_RE.match(slug) or len(slug) < 2 or len(slug) > 64:
            raise ValidationError("invalid slug format")
        if not contact_name or not contact_email or "@" not in contact_email:
            raise ValidationError("invalid contact details")
        if len(country) < 2 or len(country) > 8:
            raise ValidationError("invalid country")

        org = await self._owned_individual_org(requester_user_id)
        await self._assert_slug_available(slug, org.id)

        request = OrganizationRegistrationRequestRow(
            id=uuid.uuid4(),
            org_id=org.id,
            requester_user_id=requester_user_id,
            name=name,
            slug=slug,
            contact_name=contact_name,
            contact_email=contact_email,
            country=country,
            status="processing",
        )
        self._session.add(request)
        await self._session.flush()

        if (settings.workflow_mode or "inline").lower() == "temporal":
            await self._session.commit()
            payload = {
                "request_id": str(request.id),
                "requester_principal_id": str(requester_principal_id),
            }
            try:
                from workflows.starter import start_org_upgrade

                await start_org_upgrade(payload)
            except Exception as exc:  # noqa: BLE001 — surface start failure on the request row
                await self._mark_failed(request.id, org.id, requester_user_id, name, slug, contact_name, contact_email, country, str(exc))
                return OrgRegisterResult(
                    request_id=request.id,
                    status="failed",
                    org_id=org.id,
                    estimated_ms=0,
                    error_message=str(exc)[:500],
                )
            return OrgRegisterResult(
                request_id=request.id,
                status="processing",
                org_id=org.id,
                estimated_ms=15000,
            )

        try:
            result = await self._run_pipeline(
                request=request,
                org=org,
                requester_user_id=requester_user_id,
                requester_principal_id=requester_principal_id,
            )
        except KeycloakUnavailable:
            await self._session.rollback()
            raise
        except Exception as exc:  # noqa: BLE001 — persist failed request for poll
            await self._session.rollback()
            await self._mark_failed(
                request.id, org.id, requester_user_id, name, slug, contact_name, contact_email, country, str(exc)
            )
            return OrgRegisterResult(
                request_id=request.id,
                status="failed",
                org_id=org.id,
                estimated_ms=0,
                error_message=str(exc)[:500],
            )

        await self._session.commit()
        return result

    async def run_for_request(
        self, *, request_id: UUID, requester_principal_id: UUID
    ) -> OrgRegisterResult:
        """Worker entry: finish a request already stored as processing."""
        request = await self._session.get(OrganizationRegistrationRequestRow, request_id)
        if request is None:
            raise NotFoundError("request not found")
        if request.status == "completed":
            return OrgRegisterResult(
                request_id=request.id,
                status="completed",
                org_id=request.org_id,
                estimated_ms=0,
                keycloak_realm_ref=request.keycloak_realm_ref,
                realm_url=(
                    f"{request.keycloak_realm_ref}.auth.platform.io"
                    if request.keycloak_realm_ref
                    else None
                ),
            )
        org = await self._session.get(OrganizationRow, request.org_id)
        if org is None:
            raise NotFoundError("organization not found")
        try:
            result = await self._run_pipeline(
                request=request,
                org=org,
                requester_user_id=request.requester_user_id,
                requester_principal_id=requester_principal_id,
            )
            await self._session.commit()
            return result
        except KeycloakUnavailable:
            await self._session.rollback()
            raise
        except Exception as exc:  # noqa: BLE001
            await self._session.rollback()
            await self._mark_failed(
                request.id,
                org.id,
                request.requester_user_id,
                request.name,
                request.slug,
                request.contact_name,
                request.contact_email,
                request.country,
                str(exc),
            )
            return OrgRegisterResult(
                request_id=request.id,
                status="failed",
                org_id=org.id,
                estimated_ms=0,
                error_message=str(exc)[:500],
            )

    async def _mark_failed(
        self,
        request_id: UUID,
        org_id: UUID,
        requester_user_id: UUID,
        name: str,
        slug: str,
        contact_name: str,
        contact_email: str,
        country: str,
        error: str,
    ) -> None:
        existing = await self._session.get(OrganizationRegistrationRequestRow, request_id)
        if existing is None:
            existing = OrganizationRegistrationRequestRow(
                id=request_id,
                org_id=org_id,
                requester_user_id=requester_user_id,
                name=name,
                slug=slug,
                contact_name=contact_name,
                contact_email=contact_email,
                country=country,
                status="failed",
                error_message=error[:500],
                completed_at=utcnow(),
            )
            self._session.add(existing)
        else:
            existing.status = "failed"
            existing.error_message = error[:500]
            existing.completed_at = utcnow()
        await self._session.commit()

    async def get_status(
        self, *, request_id: UUID, requester_user_id: UUID
    ) -> OrgRegisterResult:
        request = await self._session.get(OrganizationRegistrationRequestRow, request_id)
        if request is None:
            raise NotFoundError("request not found")
        if request.requester_user_id != requester_user_id:
            raise ForbiddenError("not the request owner")
        realm_url = (
            f"{request.keycloak_realm_ref}.auth.platform.io"
            if request.keycloak_realm_ref
            else None
        )
        return OrgRegisterResult(
            request_id=request.id,
            status=request.status,
            org_id=request.org_id,
            estimated_ms=0 if request.status != "processing" else 15000,
            keycloak_realm_ref=request.keycloak_realm_ref,
            realm_url=realm_url,
            error_message=request.error_message,
        )

    async def _run_pipeline(
        self,
        *,
        request: OrganizationRegistrationRequestRow,
        org: OrganizationRow,
        requester_user_id: UUID,
        requester_principal_id: UUID,
    ) -> OrgRegisterResult:
        slug = request.slug
        realm_name = await self._keycloak.create_realm(slug)

        issuer = f"https://{slug}.auth.platform.io"
        existing_realm = (
            await self._session.execute(select(IdentityRealmRow).where(IdentityRealmRow.realm_name == slug))
        ).scalar_one_or_none()
        if existing_realm is None:
            self._session.add(
                IdentityRealmRow(
                    id=uuid.uuid4(),
                    realm_name=slug,
                    realm_type="organization",
                    issuer=issuer,
                    issuer_url=issuer,
                    keycloak_realm_id=realm_name,
                    organization_id=org.id,
                    status="active",
                )
            )

        org.name = request.name
        org.slug = slug
        org.org_type = "organization"
        org.keycloak_realm_ref = slug
        org.status = "active"

        tenant = TenantRow(
            id=uuid.uuid4(),
            organization_id=org.id,
            name=f"{request.name} default",
            slug=f"{slug}-default",
            status="active",
        )
        self._session.add(tenant)
        await self._session.flush()

        self._session.add(
            TenantMembershipRow(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=requester_user_id,
                status="active",
            )
        )
        self._session.add(
            ProjectRow(id=uuid.uuid4(), tenant_id=tenant.id, name="default-project")
        )

        await seed_tenant_system_roles(self._session, tenant.id)
        roles = (
            await self._session.execute(
                select(RoleRow).where(
                    RoleRow.tenant_id == tenant.id,
                    RoleRow.scope_type == "tenant",
                    RoleRow.name == "tenant-admin",
                )
            )
        ).scalar_one()

        now = utcnow()
        self._session.add(
            PrincipalRoleRow(
                id=uuid.uuid4(),
                principal_id=requester_principal_id,
                role_id=roles.id,
                scope_type="tenant",
                tenant_id=tenant.id,
                status="active",
                assigned_by=requester_principal_id,
                valid_from=now,
                created_at=now,
            )
        )

        request.status = "completed"
        request.keycloak_realm_ref = slug
        request.completed_at = now
        request.error_message = None

        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="organization.registered",
                actor_user_id=requester_user_id,
                tenant_id=tenant.id,
                payload_json={
                    "org_id": str(org.id),
                    "slug": slug,
                    "request_id": str(request.id),
                    "new_tenant_id": str(tenant.id),
                },
            )
        )
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="keycloak.realm.created",
                actor_user_id=requester_user_id,
                tenant_id=tenant.id,
                payload_json={"realm": slug, "org_id": str(org.id)},
            )
        )

        return OrgRegisterResult(
            request_id=request.id,
            status="completed",
            org_id=org.id,
            estimated_ms=0,
            keycloak_realm_ref=slug,
            realm_url=f"{slug}.auth.platform.io",
        )

    async def _owned_individual_org(self, user_id: UUID) -> OrganizationRow:
        row = (
            await self._session.execute(
                select(OrganizationRow)
                .join(OrgMembershipRow, OrgMembershipRow.organization_id == OrganizationRow.id)
                .where(
                    OrgMembershipRow.user_id == user_id,
                    OrgMembershipRow.role == "owner",
                    OrgMembershipRow.status == "active",
                    OrganizationRow.status == "active",
                )
                .order_by(OrganizationRow.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise ForbiddenError("no owned organization")
        if row.org_type != "individual":
            raise ForbiddenError("already an organization")
        return row

    async def _assert_slug_available(self, slug: str, org_id: UUID) -> None:
        existing = (
            await self._session.execute(
                select(OrganizationRow.id).where(
                    OrganizationRow.slug == slug,
                    OrganizationRow.id != org_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("slug already taken")
        pending = (
            await self._session.execute(
                select(OrganizationRegistrationRequestRow.id).where(
                    OrganizationRegistrationRequestRow.slug == slug,
                    OrganizationRegistrationRequestRow.status.in_(("processing", "completed")),
                )
            )
        ).scalar_one_or_none()
        if pending is not None:
            raise ConflictError("slug already taken")
