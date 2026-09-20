from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from authz.infrastructure.models import PrincipalRoleRow, RoleRow
from identity.infrastructure.models import UserRow
from tenant.infrastructure.models import TenantMembershipRow, TenantRow

from tests.integration.conftest import get_delivery_secret

PASSWORD = "SecurePass123!"


@dataclass
class AuthedTenant:
    email: str
    token: str
    user_id: uuid.UUID
    principal_id: uuid.UUID
    tenant_id: uuid.UUID


async def _outbox_otp(session_factory: async_sessionmaker[AsyncSession], email: str) -> str:
    del email
    return await get_delivery_secret(session_factory, purpose="verification_email")


async def register_verify_login(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    email: str,
    display_name: str = "User",
) -> AuthedTenant:
    reg = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": display_name,
            "agreed_to_terms": True,
        },
    )
    assert reg.status_code == 201, reg.text
    data = reg.json()
    otp = await _outbox_otp(session_factory, email)
    verify = await client.post("/auth/verify-email", json={"email": email, "otp_code": otp})
    assert verify.status_code == 200, verify.text
    login = await client.post(
        "/auth/token",
        json={"email": email, "password": PASSWORD, "realm_hint": "platform"},
    )
    assert login.status_code == 200, login.text
    async with session_factory() as session:
        user = await session.get(UserRow, uuid.UUID(data["user_id"]))
        assert user is not None
        principal_id = user.principal_id
    return AuthedTenant(
        email=email,
        token=login.json()["access_token"],
        user_id=uuid.UUID(data["user_id"]),
        principal_id=principal_id,
        tenant_id=uuid.UUID(data["tenant_id"]),
    )


@pytest.mark.asyncio
async def test_create_resource_success(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "res-ok@example.com")
    resp = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/resources",
        headers={"Authorization": f"Bearer {auth.token}"},
        json={"name": "cluster-1", "resource_type": "compute.cluster"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "cluster-1"
    assert body["resource_type"] == "compute.cluster"
    assert body["status"] == "active"
    assert body["tenant_id"] == str(auth.tenant_id)
    assert "id" in body


@pytest.mark.asyncio
async def test_create_resource_missing_membership(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "res-nomember@example.com")
    async with session_factory() as session:
        await session.execute(
            delete(TenantMembershipRow).where(
                TenantMembershipRow.user_id == auth.user_id,
                TenantMembershipRow.tenant_id == auth.tenant_id,
            )
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/resources",
        headers={"Authorization": f"Bearer {auth.token}"},
        json={"name": "cluster-1", "resource_type": "compute.cluster"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_create_resource_missing_permission(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "res-noperm@example.com")
    async with session_factory() as session:
        bindings = (
            await session.execute(
                select(PrincipalRoleRow).where(PrincipalRoleRow.principal_id == auth.principal_id)
            )
        ).scalars().all()
        for binding in bindings:
            binding.status = "revoked"
        viewer = (
            await session.execute(
                select(RoleRow).where(
                    RoleRow.tenant_id == auth.tenant_id,
                    RoleRow.name == "viewer",
                )
            )
        ).scalar_one()
        session.add(
            PrincipalRoleRow(
                id=uuid.uuid4(),
                principal_id=auth.principal_id,
                role_id=viewer.id,
                scope_type="tenant",
                tenant_id=auth.tenant_id,
                status="active",
            )
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/resources",
        headers={"Authorization": f"Bearer {auth.token}"},
        json={"name": "cluster-1", "resource_type": "compute.cluster"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_create_resource_revoked_role(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "res-revoked@example.com")
    async with session_factory() as session:
        bindings = (
            await session.execute(
                select(PrincipalRoleRow).where(PrincipalRoleRow.principal_id == auth.principal_id)
            )
        ).scalars().all()
        for binding in bindings:
            binding.status = "revoked"
        await session.commit()

    resp = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/resources",
        headers={"Authorization": f"Bearer {auth.token}"},
        json={"name": "cluster-1", "resource_type": "compute.cluster"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_create_resource_inactive_tenant(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "res-inactive@example.com")
    async with session_factory() as session:
        tenant = await session.get(TenantRow, auth.tenant_id)
        assert tenant is not None
        tenant.status = "suspended"
        await session.commit()

    resp = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/resources",
        headers={"Authorization": f"Bearer {auth.token}"},
        json={"name": "cluster-1", "resource_type": "compute.cluster"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_create_resource_tenant_a_accessing_tenant_b(
    client: AsyncClient, session_factory
) -> None:
    alice = await register_verify_login(client, session_factory, "res-alice@example.com", "Alice")
    bob = await register_verify_login(client, session_factory, "res-bob@example.com", "Bob")

    resp = await client.post(
        f"/api/v1/tenants/{bob.tenant_id}/resources",
        headers={"Authorization": f"Bearer {alice.token}"},
        json={"name": "stolen", "resource_type": "compute.cluster"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_create_resource_invalid_jwt(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "res-jwt@example.com")
    resp = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/resources",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
        json={"name": "cluster-1", "resource_type": "compute.cluster"},
    )
    assert resp.status_code == 401
