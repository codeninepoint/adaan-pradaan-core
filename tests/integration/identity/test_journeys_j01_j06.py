from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.infrastructure.models import OutboxEventRow as PlatformOutboxRow
from tests.integration.conftest import get_delivery_secret

PASSWORD = "SecurePass123!"


async def get_outbox_otp(session_factory: async_sessionmaker[AsyncSession], email: str) -> str:
    del email
    return await get_delivery_secret(session_factory, purpose="verification_email")


@pytest.mark.asyncio
async def test_j01_user_registration(client: AsyncClient, session_factory) -> None:
    resp = await client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "password": PASSWORD,
            "display_name": "Alice Smith",
            "agreed_to_terms": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending_verification"
    assert data["verification_email_sent"] is True
    assert "user_id" in data and "org_id" in data and "tenant_id" in data

    async with session_factory() as session:
        from identity.infrastructure.models import CredentialRow, PrincipalRow, UserRow
        from tenant.infrastructure.models import OrganizationRow, TenantRow
        from authz.infrastructure.models import PrincipalRoleRow, RoleRow

        user = await session.get(UserRow, uuid.UUID(data["user_id"]))
        assert user is not None and user.status == "pending_verification"
        assert user.principal_id is not None
        principal = await session.get(PrincipalRow, user.principal_id)
        assert principal is not None and principal.principal_type == "user"
        assert principal.status == "inactive"
        cred = await session.execute(
            select(CredentialRow).where(CredentialRow.principal_id == user.principal_id)
        )
        assert cred.scalar_one_or_none() is not None
        org = await session.get(OrganizationRow, uuid.UUID(data["org_id"]))
        assert org is not None and org.org_type == "individual"
        tenant = await session.get(TenantRow, uuid.UUID(data["tenant_id"]))
        assert tenant is not None and tenant.status == "active"
        roles = await session.execute(select(RoleRow).where(RoleRow.tenant_id == tenant.id))
        assert len(roles.scalars().all()) == 3
        binding = await session.execute(
            select(PrincipalRoleRow).where(PrincipalRoleRow.principal_id == user.principal_id)
        )
        assert binding.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_j02_email_verification(client: AsyncClient, session_factory) -> None:
    reg = await client.post(
        "/auth/register",
        json={
            "email": "bob@example.com",
            "password": PASSWORD,
            "display_name": "Bob",
            "agreed_to_terms": True,
        },
    )
    user_id = reg.json()["user_id"]
    otp = await get_outbox_otp(session_factory, "bob@example.com")
    resp = await client.post("/auth/verify-email", json={"email": "bob@example.com", "otp_code": otp})
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    async with session_factory() as session:
        from identity.infrastructure.models import UserRow

        user = await session.get(UserRow, uuid.UUID(user_id))
        assert user.status == "active"


@pytest.mark.asyncio
async def test_j03_user_login(client: AsyncClient, session_factory) -> None:
    await client.post(
        "/auth/register",
        json={
            "email": "carol@example.com",
            "password": PASSWORD,
            "display_name": "Carol",
            "agreed_to_terms": True,
        },
    )
    otp = await get_outbox_otp(session_factory, "carol@example.com")
    await client.post("/auth/verify-email", json={"email": "carol@example.com", "otp_code": otp})

    resp = await client.post(
        "/auth/token",
        json={"email": "carol@example.com", "password": PASSWORD, "realm_hint": "platform"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 900
    assert "access_token" in data and data["refresh_token"]
    assert data["principal_id"]

    from jose import jwt
    from shared.settings import settings

    payload = jwt.decode(
        data["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": True},
    )
    # Multi-tenant SME rule: never embed RBAC in JWT — live AuthZ on every call
    assert "roles" not in payload and "permissions" not in payload
    assert payload["typ"] == "user"
    assert payload["sid"] == data["session_id"]
    assert payload["uid"] == data["user_id"]
    assert payload["pid"] == data["principal_id"]


@pytest.mark.asyncio
async def test_j04_token_refresh_rotates(client: AsyncClient, session_factory) -> None:
    await client.post(
        "/auth/register",
        json={
            "email": "dave@example.com",
            "password": PASSWORD,
            "display_name": "Dave",
            "agreed_to_terms": True,
        },
    )
    otp = await get_outbox_otp(session_factory, "dave@example.com")
    await client.post("/auth/verify-email", json={"email": "dave@example.com", "otp_code": otp})
    login = await client.post(
        "/auth/token",
        json={"email": "dave@example.com", "password": PASSWORD},
    )
    body = login.json()
    refresh = await client.post(
        "/auth/token/refresh",
        json={"refresh_token": body["refresh_token"], "session_id": body["session_id"]},
    )
    assert refresh.status_code == 200, refresh.text
    rotated = refresh.json()
    assert rotated["refresh_token"] != body["refresh_token"]
    assert rotated["access_token"] != body["access_token"]

    # Old refresh must fail and revoke the session (reuse detection)
    reuse = await client.post(
        "/auth/token/refresh",
        json={"refresh_token": body["refresh_token"], "session_id": body["session_id"]},
    )
    assert reuse.status_code == 401

    # Rotated refresh also fails after reuse-triggered revoke
    after = await client.post(
        "/auth/token/refresh",
        json={"refresh_token": rotated["refresh_token"], "session_id": body["session_id"]},
    )
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_j05_session_revocation(client: AsyncClient, session_factory) -> None:
    await client.post(
        "/auth/register",
        json={
            "email": "eve@example.com",
            "password": PASSWORD,
            "display_name": "Eve",
            "agreed_to_terms": True,
        },
    )
    otp = await get_outbox_otp(session_factory, "eve@example.com")
    await client.post("/auth/verify-email", json={"email": "eve@example.com", "otp_code": otp})
    login = await client.post(
        "/auth/token",
        json={"email": "eve@example.com", "password": PASSWORD},
    )
    body = login.json()
    token = body["access_token"]
    refresh = body["refresh_token"]
    session_id = body["session_id"]

    logout = await client.delete("/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200

    # Access JWT fails once session is revoked
    again = await client.delete("/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert again.status_code == 401

    # Refresh cannot revive a revoked session
    revive = await client.post(
        "/auth/token/refresh",
        json={"refresh_token": refresh, "session_id": session_id},
    )
    assert revive.status_code in {401, 403}


@pytest.mark.asyncio
async def test_j05b_principal_access_revocation(client: AsyncClient, session_factory) -> None:
    reg = await client.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": PASSWORD,
            "display_name": "Admin",
            "agreed_to_terms": True,
        },
    )
    tenant_id = reg.json()["tenant_id"]
    user_id = reg.json()["user_id"]
    otp = await get_outbox_otp(session_factory, "admin@example.com")
    await client.post("/auth/verify-email", json={"email": "admin@example.com", "otp_code": otp})

    # Second login session to revoke after admin call (admin call needs live auth)
    login_a = await client.post(
        "/auth/token",
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    login_b = await client.post(
        "/auth/token",
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    a = login_a.json()
    b = login_b.json()

    revoke = await client.post(
        f"/auth/users/{user_id}/revoke-access",
        headers={
            "Authorization": f"Bearer {a['access_token']}",
            "X-Tenant-Id": tenant_id,
        },
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["sessions_revoked"] >= 1
    assert revoke.json()["status"] == "locked"

    # Both sessions dead for API and refresh
    for tok in (a, b):
        dead = await client.delete(
            "/auth/sessions",
            headers={"Authorization": f"Bearer {tok['access_token']}"},
        )
        assert dead.status_code == 401
        refresh_dead = await client.post(
            "/auth/token/refresh",
            json={"refresh_token": tok["refresh_token"], "session_id": tok["session_id"]},
        )
        assert refresh_dead.status_code in {401, 403}

    # Re-login also blocked while locked
    blocked = await client.post(
        "/auth/token",
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    assert blocked.status_code in {401, 403}


@pytest.mark.asyncio
async def test_j06_password_reset(client: AsyncClient, session_factory) -> None:
    await client.post(
        "/auth/register",
        json={
            "email": "frank@example.com",
            "password": PASSWORD,
            "display_name": "Frank",
            "agreed_to_terms": True,
        },
    )
    otp = await get_outbox_otp(session_factory, "frank@example.com")
    await client.post("/auth/verify-email", json={"email": "frank@example.com", "otp_code": otp})
    login = await client.post(
        "/auth/token",
        json={"email": "frank@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200

    req = await client.post("/auth/password/reset-request", json={"email": "frank@example.com"})
    assert req.status_code == 200

    async with session_factory() as session:
        result = await session.execute(
            select(PlatformOutboxRow).where(PlatformOutboxRow.type == "send_password_reset_email")
        )
        row = result.scalars().first()
        assert row is not None
        assert "reset_token" not in row.payload_json
        assert "delivery_secret_id" in row.payload_json

    reset_token = await get_delivery_secret(session_factory, purpose="password_reset_email")

    new_password = "NewSecure456!"
    reset = await client.post(
        "/auth/password/reset",
        json={"reset_token": reset_token, "new_password": new_password},
    )
    assert reset.status_code == 200

    login_old = await client.post(
        "/auth/token",
        json={"email": "frank@example.com", "password": PASSWORD},
    )
    assert login_old.status_code == 401

    login_new = await client.post(
        "/auth/token",
        json={"email": "frank@example.com", "password": new_password},
    )
    assert login_new.status_code == 200
