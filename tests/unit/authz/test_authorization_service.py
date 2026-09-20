from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

import pytest

from authz.application.authorization_service import AuthorizationService
from authz.domain.models import ApiSurface, AuthorizeCommand, PermissionRecord


class FakePrincipals:
    def __init__(self, status_by_id: dict[UUID, str | None]) -> None:
        self.status_by_id = status_by_id

    async def get_status(self, principal_id: UUID) -> str | None:
        return self.status_by_id.get(principal_id)


class FakeTenants:
    def __init__(self, *, active: set[UUID], members: set[tuple[UUID, UUID]]) -> None:
        self.active = active
        self.members = members

    async def is_tenant_active(self, tenant_id: UUID) -> bool:
        return tenant_id in self.active

    async def has_active_tenant_membership(self, principal_id: UUID, tenant_id: UUID) -> bool:
        return (principal_id, tenant_id) in self.members


class FakeOperators:
    def __init__(self, mapping: dict[UUID, UUID | None]) -> None:
        self.mapping = mapping

    async def find_active_operator_org_id(self, principal_id: UUID) -> UUID | None:
        return self.mapping.get(principal_id)


class FakePermissions:
    def __init__(self, by_code: dict[str, PermissionRecord]) -> None:
        self.by_code = by_code

    async def get_by_code(self, code: str) -> PermissionRecord | None:
        return self.by_code.get(code)


class FakeGrants:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[dict] = []

    async def has_exact_permission_grant(self, **kwargs) -> bool:
        self.calls.append(kwargs)
        return self.allow


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    async def append(self, **kwargs) -> None:
        self.entries.append(kwargs)


def _svc(**overrides) -> tuple[AuthorizationService, FakeAudit, FakeGrants]:
    principal_id = overrides.pop("principal_id", uuid.uuid4())
    tenant_id = overrides.pop("tenant_id", uuid.uuid4())
    perm = PermissionRecord(
        id=uuid.uuid4(),
        code="tenant.admin",
        scope_type="tenant",
        status="active",
    )
    audit = FakeAudit()
    grants = FakeGrants(allow=overrides.pop("grant", True))
    svc = AuthorizationService(
        principals=FakePrincipals({principal_id: overrides.pop("principal_status", "active")}),
        tenants=FakeTenants(
            active={tenant_id} if overrides.pop("tenant_active", True) else set(),
            members={(principal_id, tenant_id)} if overrides.pop("member", True) else set(),
        ),
        operators=FakeOperators({}),
        permissions=FakePermissions({perm.code: perm}),
        grants=grants,
        audit=audit,
    )
    return svc, audit, grants, principal_id, tenant_id


@pytest.mark.asyncio
async def test_default_deny_without_grant() -> None:
    svc, audit, grants, principal_id, tenant_id = _svc(grant=False)
    result = await svc.authorize(
        AuthorizeCommand(
            principal_id=principal_id,
            permission_code="tenant.admin",
            api_surface=ApiSurface.PUBLIC,
            tenant_id=tenant_id,
        )
    )
    assert result.allowed is False
    assert result.reason == "no_matching_role_permission"
    assert audit.entries[-1]["decision"] == "deny"
    assert grants.calls and grants.calls[0]["permission_id"]


@pytest.mark.asyncio
async def test_public_cannot_evaluate_platform_permission() -> None:
    svc, audit, _, principal_id, tenant_id = _svc()
    result = await svc.authorize(
        AuthorizeCommand(
            principal_id=principal_id,
            permission_code="platform.admin",
            api_surface=ApiSurface.PUBLIC,
            tenant_id=tenant_id,
        )
    )
    assert result.allowed is False
    assert result.reason == "public_surface_rejects_platform_permission"


@pytest.mark.asyncio
async def test_management_cannot_evaluate_tenant_permission() -> None:
    svc, _, _, principal_id, _ = _svc()
    result = await svc.authorize(
        AuthorizeCommand(
            principal_id=principal_id,
            permission_code="tenant.admin",
            api_surface=ApiSurface.MANAGEMENT,
        )
    )
    assert result.allowed is False
    assert result.reason == "management_surface_requires_platform_permission"


@pytest.mark.asyncio
async def test_allows_when_all_gates_pass() -> None:
    svc, audit, _, principal_id, tenant_id = _svc(grant=True)
    result = await svc.authorize(
        AuthorizeCommand(
            principal_id=principal_id,
            permission_code="tenant.admin",
            api_surface=ApiSurface.PUBLIC,
            tenant_id=tenant_id,
            at=datetime.now(timezone.utc),
        )
    )
    assert result.allowed is True
    assert result.reason == "granted"
    assert audit.entries[-1]["decision"] == "allow"


@pytest.mark.asyncio
async def test_denies_inactive_tenant() -> None:
    svc, _, _, principal_id, tenant_id = _svc(tenant_active=False)
    result = await svc.authorize(
        AuthorizeCommand(
            principal_id=principal_id,
            permission_code="tenant.admin",
            api_surface=ApiSurface.PUBLIC,
            tenant_id=tenant_id,
        )
    )
    assert result.allowed is False
    assert result.reason == "tenant_not_active"


@pytest.mark.asyncio
async def test_platform_allow_path() -> None:
    principal_id = uuid.uuid4()
    operator_org_id = uuid.uuid4()
    perm = PermissionRecord(
        id=uuid.uuid4(), code="platform.admin", scope_type="platform", status="active"
    )
    audit = FakeAudit()
    grants = FakeGrants(allow=True)
    svc = AuthorizationService(
        principals=FakePrincipals({principal_id: "active"}),
        tenants=FakeTenants(active=set(), members=set()),
        operators=FakeOperators({principal_id: operator_org_id}),
        permissions=FakePermissions({perm.code: perm}),
        grants=grants,
        audit=audit,
    )
    result = await svc.authorize(
        AuthorizeCommand(
            principal_id=principal_id,
            permission_code="platform.admin",
            api_surface=ApiSurface.MANAGEMENT,
        )
    )
    assert result.allowed is True
    assert result.operator_org_id == operator_org_id
    assert grants.calls[0]["scope_type"] == "platform"
    assert grants.calls[0]["operator_org_id"] == operator_org_id
