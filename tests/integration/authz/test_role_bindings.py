from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from authz.infrastructure.models import RoleRow
from tests.integration.resources.test_create_resource import register_verify_login


@pytest.mark.asyncio
async def test_list_roles_and_members(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "roles-list@example.com")
    headers = {
        "Authorization": f"Bearer {auth.token}",
        "X-Tenant-Id": str(auth.tenant_id),
    }
    roles = await client.get(f"/api/v1/tenants/{auth.tenant_id}/roles", headers=headers)
    assert roles.status_code == 200, roles.text
    names = {r["name"] for r in roles.json()["items"]}
    assert {"tenant-admin", "resource-admin", "viewer"} <= names

    members = await client.get(f"/api/v1/tenants/{auth.tenant_id}/members", headers=headers)
    assert members.status_code == 200, members.text
    items = members.json()["items"]
    assert len(items) == 1
    assert items[0]["email"] == "roles-list@example.com"
    assert any(b["role_name"] == "tenant-admin" for b in items[0]["bindings"])


@pytest.mark.asyncio
async def test_grant_and_revoke_binding(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "roles-grant@example.com")
    headers = {
        "Authorization": f"Bearer {auth.token}",
        "X-Tenant-Id": str(auth.tenant_id),
    }
    async with session_factory() as session:
        role = (
            await session.execute(
                select(RoleRow).where(
                    RoleRow.tenant_id == auth.tenant_id,
                    RoleRow.name == "resource-admin",
                )
            )
        ).scalar_one()
        role_id = role.id

    grant = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/roles/{role_id}/bindings",
        headers=headers,
        json={"user_id": str(auth.user_id), "justification": "needs resource admin"},
    )
    assert grant.status_code == 201, grant.text
    body = grant.json()
    assert body["role"] == "resource-admin"
    assert body["status"] == "active"
    binding_id = body["binding_id"]

    dup = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/roles/{role_id}/bindings",
        headers=headers,
        json={"user_id": str(auth.user_id)},
    )
    assert dup.status_code == 409

    revoke = await client.request(
        "DELETE",
        f"/api/v1/tenants/{auth.tenant_id}/roles/{role_id}/bindings/{binding_id}",
        headers=headers,
        json={"reason": "no longer needed"},
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["status"] == "revoked"
    assert revoke.json()["effective"] == "immediately"


@pytest.mark.asyncio
async def test_cannot_revoke_last_tenant_admin(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "roles-lastadmin@example.com")
    headers = {"Authorization": f"Bearer {auth.token}"}
    members = await client.get(f"/api/v1/tenants/{auth.tenant_id}/members", headers=headers)
    assert members.status_code == 200
    admin_binding = next(
        b for b in members.json()["items"][0]["bindings"] if b["role_name"] == "tenant-admin"
    )
    resp = await client.request(
        "DELETE",
        f"/api/v1/tenants/{auth.tenant_id}/roles/{admin_binding['role_id']}/bindings/{admin_binding['binding_id']}",
        headers=headers,
        json={"reason": "oops"},
    )
    assert resp.status_code == 409
    assert "last tenant-admin" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_grant_forbidden_cross_tenant(client: AsyncClient, session_factory) -> None:
    alice = await register_verify_login(client, session_factory, "roles-alice@example.com", "Alice")
    bob = await register_verify_login(client, session_factory, "roles-bob@example.com", "Bob")
    async with session_factory() as session:
        role = (
            await session.execute(
                select(RoleRow).where(
                    RoleRow.tenant_id == bob.tenant_id,
                    RoleRow.name == "viewer",
                )
            )
        ).scalar_one()
        role_id = role.id

    resp = await client.post(
        f"/api/v1/tenants/{bob.tenant_id}/roles/{role_id}/bindings",
        headers={"Authorization": f"Bearer {alice.token}"},
        json={"user_id": str(bob.user_id)},
    )
    assert resp.status_code == 403
