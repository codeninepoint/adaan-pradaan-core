from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tenant.infrastructure.models import OrganizationRow
from tests.integration.resources.test_create_resource import register_verify_login


async def _operator(client: AsyncClient, session_factory, email: str) -> dict:
    auth = await register_verify_login(client, session_factory, email)
    headers = {"Authorization": f"Bearer {auth.token}"}
    me = await client.get("/auth/me", headers=headers)
    org_id = me.json()["organizations"][0]["org_id"]
    async with session_factory() as session:
        org = await session.get(OrganizationRow, uuid.UUID(org_id))
        assert org is not None
        org.is_platform_operator = True
        await session.commit()
    return {"headers": headers, "auth": auth, "tenant_id": str(auth.tenant_id)}


async def _verified_vendor(client: AsyncClient, session_factory, email: str, operator_headers: dict) -> dict:
    applicant = await register_verify_login(client, session_factory, email)
    headers = {"Authorization": f"Bearer {applicant.token}"}
    me = await client.get("/auth/me", headers=headers)
    org_id = me.json()["organizations"][0]["org_id"]
    reg = await client.post(
        f"/api/v1/organizations/{org_id}/vendor/register",
        headers=headers,
        json={
            "legal_name": "Std Plugin Vendor",
            "tax_id": "27BBBBB0000B1Z5",
            "payout_bank_account": "XXXXXXXX9999",
            "contact_email": email,
            "business_doc_url": "https://uploads.example.com/doc.pdf",
        },
    )
    assert reg.status_code == 202, reg.text
    decision = await client.post(
        f"/api/v1/admin/vendor-verifications/{reg.json()['verification_id']}/decision",
        headers=operator_headers,
        json={"decision": "approved", "notes": "ok"},
    )
    assert decision.status_code == 200, decision.text
    return {
        "vendor_id": reg.json()["vendor_id"],
        "headers": headers,
        "tenant_id": str(applicant.tenant_id),
    }


@pytest.mark.asyncio
async def test_standard_plugins_and_review_filters(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "pa-gov-op@example.com")
    vendor = await _verified_vendor(client, session_factory, "pa-gov-vendor@example.com", op["headers"])

    grid = await client.get("/api/v1/admin/standard-plugins", headers=op["headers"])
    assert grid.status_code == 200, grid.text
    assert len(grid.json()["items"]) == 9
    assert all(item["plugin_id"] is None for item in grid.json()["items"])

    created = await client.post(
        "/api/v1/admin/standard-plugins",
        headers=op["headers"],
        json={
            "name": "Platform Ship Physical",
            "slug": "platform-standard-ship-physical",
            "category": "SHIP_PHYSICAL",
            "short_description": "Default fulfilment",
            "version": "1.0.0",
            "artifact_url": "https://platform.example.com/ship.zip",
            "publish": True,
        },
    )
    assert created.status_code == 201, created.text
    plugin_id = created.json()["plugin_id"]
    assert created.json()["status"] == "active"

    grid2 = await client.get("/api/v1/admin/standard-plugins", headers=op["headers"])
    slot = next(i for i in grid2.json()["items"] if i["category"] == "SHIP_PHYSICAL")
    assert slot["plugin_id"] == plugin_id
    assert slot["status"] == "active"

    unpub = await client.post(
        f"/api/v1/admin/standard-plugins/{plugin_id}/unpublish", headers=op["headers"]
    )
    assert unpub.status_code == 200, unpub.text
    assert unpub.json()["status"] == "unpublished"

    pub = await client.post(
        f"/api/v1/admin/standard-plugins/{plugin_id}/publish", headers=op["headers"]
    )
    assert pub.status_code == 200
    assert pub.json()["status"] == "active"

    # Vendor plugin review queue with risk + claim filters
    plugin = await client.post(
        f"/api/v1/vendors/{vendor['vendor_id']}/plugins",
        headers=vendor["headers"],
        json={
            "name": "Pay Hook",
            "slug": "pay-hook-plugin",
            "category": "payments",
            "short_description": "payments",
        },
    )
    assert plugin.status_code == 201, plugin.text
    version = await client.post(
        f"/api/v1/plugins/{plugin.json()['plugin_id']}/versions",
        headers=vendor["headers"],
        json={
            "version": "1.0.0",
            "artifact_url": "https://example.com/a.zip",
            "sbom_url": "https://example.com/sbom.json",
            "changelog": "init",
        },
    )
    assert version.status_code == 201, version.text
    version_id = version.json()["version_id"]
    caps = await client.put(
        f"/api/v1/plugins/versions/{version_id}/capabilities",
        headers=vendor["headers"],
        json={"capabilities": [{"scope": "payments.write", "justification": "charge cards"}]},
    )
    assert caps.status_code == 200, caps.text

    stats = await client.get("/api/v1/admin/plugin-reviews/stats", headers=op["headers"])
    assert stats.status_code == 200, stats.text
    assert stats.json()["pending"] >= 1
    assert stats.json()["standard_plugins"] >= 1

    pending = await client.get(
        "/api/v1/admin/plugin-reviews?claimed=false&risk=high", headers=op["headers"]
    )
    assert pending.status_code == 200, pending.text
    assert any(i["version_id"] == version_id for i in pending.json()["items"])
    assert all(i["risk_level"] == "high" for i in pending.json()["items"])

    claim = await client.post(
        f"/api/v1/admin/plugin-reviews/{version_id}/claim", headers=op["headers"]
    )
    assert claim.status_code == 200, claim.text

    in_review = await client.get(
        "/api/v1/admin/plugin-reviews?claimed=true", headers=op["headers"]
    )
    assert any(i["version_id"] == version_id for i in in_review.json()["items"])

    decide = await client.post(
        f"/api/v1/admin/plugin-reviews/{version_id}/decision",
        headers=op["headers"],
        json={"decision": "approved", "notes": "ok"},
    )
    assert decide.status_code == 200, decide.text

    history = await client.get(
        "/api/v1/admin/plugin-reviews?status=approved", headers=op["headers"]
    )
    assert history.status_code == 200
    assert any(i["version_id"] == version_id for i in history.json()["items"])


@pytest.mark.asyncio
async def test_admin_users_and_roles(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "pa-users-op@example.com")
    target = await register_verify_login(client, session_factory, "pa-users-target@example.com")

    users = await client.get("/api/v1/admin/users", headers=op["headers"])
    assert users.status_code == 200, users.text
    assert users.json()["total"] >= 2
    assert any(u["email"] == "pa-users-target@example.com" for u in users.json()["items"])

    suspend = await client.post(
        f"/api/v1/admin/users/{target.user_id}/suspend", headers=op["headers"]
    )
    assert suspend.status_code == 200, suspend.text
    assert suspend.json()["status"] == "locked"

    reinstate = await client.post(
        f"/api/v1/admin/users/{target.user_id}/reinstate", headers=op["headers"]
    )
    assert reinstate.status_code == 200, reinstate.text
    assert reinstate.json()["status"] == "active"

    reset = await client.post(
        f"/api/v1/admin/users/{target.user_id}/reset-mfa", headers=op["headers"]
    )
    assert reset.status_code == 200, reset.text

    perms = await client.get("/api/v1/admin/permissions", headers=op["headers"])
    assert perms.status_code == 200, perms.text
    codes = {p["code"] for p in perms.json()["items"]}
    assert "platform.plugin.review" in codes
    assert "platform.user.manage" in codes

    roles = await client.get("/api/v1/admin/roles", headers=op["headers"])
    assert roles.status_code == 200, roles.text
    names = {r["name"] for r in roles.json()["items"]}
    assert "platform-admin" in names
    assert "tenant-admin" in names

    custom = await client.post(
        "/api/v1/admin/roles",
        headers=op["headers"],
        json={
            "name": "catalog-reader",
            "based_on": "viewer",
            "tenant_id": op["tenant_id"],
            "add_permissions": ["vendor.read"],
            "remove_permissions": [],
        },
    )
    assert custom.status_code == 201, custom.text
    assert custom.json()["is_system_role"] is False
    assert "vendor.read" in custom.json()["permission_codes"]

    bindings = await client.get("/api/v1/admin/role-bindings", headers=op["headers"])
    assert bindings.status_code == 200, bindings.text
