from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_ops.infrastructure.models import PlatformConfigRow, PlatformPolicyRow, PlatformTeamMemberRow
from tenant.infrastructure.models import OrganizationRow, TenantRow
from tests.integration.marketplace.test_platform_admin_governance import (
    _operator,
    _verified_vendor,
)
from tests.integration.resources.test_create_resource import PASSWORD, register_verify_login


async def _seed_platform_config(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        for key, value in {
            "platform_name": "AdanPradan FairShare",
            "commission_rate_pct": 10,
            "product_content_review_required": True,
        }.items():
            session.add(PlatformConfigRow(key=key, value=value))
        session.add(
            PlatformPolicyRow(
                id=uuid.uuid4(),
                name="Test Policy",
                scope="plugins",
                enforcement="mandatory",
                applies_to="All plugins",
                status="enforced",
                body={},
            )
        )
        await session.commit()


async def _super_admin(session_factory, client: AsyncClient, email: str) -> dict:
    op = await _operator(client, session_factory, email)
    async with session_factory() as session:
        session.add(
            PlatformTeamMemberRow(
                id=uuid.uuid4(),
                user_id=op["auth"].user_id,
                email=email.lower(),
                platform_role="super_admin",
                status="active",
            )
        )
        await session.commit()
    return op


async def _vendor_product_pending_review(
    client: AsyncClient, session_factory, operator_headers: dict, vendor_email: str
) -> dict:
    slug_suffix = vendor_email.split("@")[0].replace(".", "-")
    vendor = await _verified_vendor(client, session_factory, vendor_email, operator_headers)
    plugin = await client.post(
        f"/api/v1/vendors/{vendor['vendor_id']}/plugins",
        headers=vendor["headers"],
        json={
            "name": "Catalog Widget",
            "slug": f"catalog-widget-{slug_suffix}",
            "category": "widgets",
            "short_description": "widget",
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
        json={"capabilities": [{"scope": "widgets.read", "justification": "read widgets"}]},
    )
    assert caps.status_code == 200, caps.text
    decide = await client.post(
        f"/api/v1/admin/plugin-reviews/{version_id}/decision",
        headers=operator_headers,
        json={"decision": "approved", "notes": "ok"},
    )
    assert decide.status_code == 200, decide.text
    product = await client.post(
        f"/api/v1/vendors/{vendor['vendor_id']}/products",
        headers=vendor["headers"],
        json={
            "name": "Pending Widget",
            "description": "needs review",
            "plugin_id": plugin.json()["plugin_id"],
            "fulfilment_type": "PROVISION_SOFTWARE",
            "content": {"headline": "Buy now"},
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["product_id"]
    offering = await client.post(
        f"/api/v1/products/{product_id}/offerings",
        headers=vendor["headers"],
        json={
            "plan_name": "Starter",
            "billing_period": "monthly",
            "price_usd": "9.99",
        },
    )
    assert offering.status_code == 201, offering.text
    offering_id = offering.json()["offering_id"]
    publish = await client.post(
        f"/api/v1/offerings/{offering_id}/publish",
        headers=vendor["headers"],
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["status"] == "pending_review"
    return {
        "vendor": vendor,
        "product_id": product_id,
        "offering_id": offering_id,
    }


@pytest.mark.asyncio
async def test_vendor_directory_enrich_and_reinstate(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "pa-rem-vendor-op@example.com")
    vendor_ctx = await _verified_vendor(
        client, session_factory, "pa-rem-vendor@example.com", op["headers"]
    )

    listed = await client.get("/api/v1/admin/vendors?q=Std", headers=op["headers"])
    assert listed.status_code == 200, listed.text
    row = next(i for i in listed.json()["results"] if i["vendor_id"] == vendor_ctx["vendor_id"])
    assert "plugin_count" in row
    assert "warehouse_count" in row
    assert "kyc_status" in row
    assert "gmv_mtd" in row

    stats = await client.get("/api/v1/admin/vendors/stats", headers=op["headers"])
    assert stats.status_code == 200, stats.text
    assert stats.json()["active"] >= 1

    suspend = await client.post(
        f"/api/v1/admin/vendors/{vendor_ctx['vendor_id']}/suspend",
        headers=op["headers"],
        json={"reason": "policy breach"},
    )
    assert suspend.status_code == 200, suspend.text
    assert suspend.json()["status"] == "suspended"

    reinstate = await client.post(
        f"/api/v1/admin/vendors/{vendor_ctx['vendor_id']}/reinstate",
        headers=op["headers"],
    )
    assert reinstate.status_code == 200, reinstate.text
    assert reinstate.json()["status"] == "verified"


@pytest.mark.asyncio
async def test_tenant_list_and_suspend(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "pa-rem-tenant-op@example.com")
    tenant_user = await register_verify_login(client, session_factory, "pa-rem-tenant-user@example.com")

    listed = await client.get("/api/v1/admin/tenants", headers=op["headers"])
    assert listed.status_code == 200, listed.text
    assert any(i["tenant_id"] == str(tenant_user.tenant_id) for i in listed.json()["items"])

    stats = await client.get("/api/v1/admin/tenants/stats", headers=op["headers"])
    assert stats.status_code == 200, stats.text
    assert stats.json()["total"] >= 1

    suspend = await client.post(
        f"/api/v1/admin/tenants/{tenant_user.tenant_id}/suspend",
        headers=op["headers"],
    )
    assert suspend.status_code == 200, suspend.text
    assert suspend.json()["status"] == "suspended"
    assert suspend.json()["sessions_revoked"] >= 1

    async with session_factory() as session:
        tenant = await session.get(TenantRow, tenant_user.tenant_id)
        assert tenant is not None
        assert tenant.status == "suspended"
        org = await session.get(OrganizationRow, tenant.organization_id)
        assert org is not None
        assert org.status == "suspended"


@pytest.mark.asyncio
async def test_product_pa_status_approve_reject_and_catalog_gate(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_platform_config(session_factory)
    op = await _operator(client, session_factory, "pa-rem-product-op@example.com")
    ctx = await _vendor_product_pending_review(
        client, session_factory, op["headers"], "pa-rem-product-vendor@example.com"
    )

    pending = await client.get(
        "/api/v1/admin/products?pa_status=pending_review", headers=op["headers"]
    )
    assert pending.status_code == 200, pending.text
    assert any(i["product_id"] == ctx["product_id"] for i in pending.json()["items"])

    hidden = await client.get(f"/api/v1/marketplace/products/{ctx['product_id']}")
    assert hidden.status_code == 404

    approve = await client.post(
        f"/api/v1/admin/products/{ctx['product_id']}/approve",
        headers=op["headers"],
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["pa_status"] == "live"

    visible = await client.get(f"/api/v1/marketplace/products/{ctx['product_id']}")
    assert visible.status_code == 200, visible.text

    ctx2 = await _vendor_product_pending_review(
        client, session_factory, op["headers"], "pa-rem-product-vendor2@example.com"
    )
    reject = await client.post(
        f"/api/v1/admin/products/{ctx2['product_id']}/reject",
        headers=op["headers"],
        json={"reason": "Incomplete listing content"},
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["pa_status"] == "rejected"
    assert reject.json()["pa_reject_reason"] == "Incomplete listing content"

    pstats = await client.get("/api/v1/admin/products/stats", headers=op["headers"])
    assert pstats.status_code == 200, pstats.text
    assert pstats.json()["live"] >= 1
    assert pstats.json()["rejected"] >= 1


@pytest.mark.asyncio
async def test_audit_log_config_policies_dashboard(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_platform_config(session_factory)
    op = await _operator(client, session_factory, "pa-rem-ops-op@example.com")
    await client.post(
        f"/api/v1/admin/vendors/{(await _verified_vendor(client, session_factory, 'pa-rem-audit-vendor@example.com', op['headers']))['vendor_id']}/suspend",
        headers=op["headers"],
        json={"reason": "audit test"},
    )

    audit = await client.get(
        "/api/v1/admin/audit-log?action=vendor.suspended", headers=op["headers"]
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["total"] >= 1
    assert any(i["event_action"] == "vendor.suspended" for i in audit.json()["items"])

    config = await client.get("/api/v1/admin/config", headers=op["headers"])
    assert config.status_code == 200, config.text
    assert config.json()["values"]["product_content_review_required"] is True

    patched = await client.patch(
        "/api/v1/admin/config",
        headers=op["headers"],
        json={"updates": {"commission_rate_pct": 12}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["values"]["commission_rate_pct"] == 12

    policies = await client.get("/api/v1/admin/policies", headers=op["headers"])
    assert policies.status_code == 200, policies.text
    assert len(policies.json()["items"]) >= 1

    dashboard = await client.get("/api/v1/admin/dashboard", headers=op["headers"])
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["tenant_count"] >= 1
    assert body["vendor_count"] >= 1
    assert "recent_events" in body

    analytics = await client.get("/api/v1/admin/analytics?tab=users", headers=op["headers"])
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["tab"] == "users"


@pytest.mark.asyncio
async def test_team_invite_role_change_super_admin_transfer(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    sa = await _super_admin(session_factory, client, "pa-rem-sa@example.com")
    recipient = await register_verify_login(client, session_factory, "pa-rem-team-member@example.com")

    invite = await client.post(
        "/api/v1/admin/team/invite",
        headers=sa["headers"],
        json={"email": "pa-rem-team-member@example.com", "platform_role": "support"},
    )
    assert invite.status_code == 200, invite.text
    member_id = invite.json()["id"]
    assert invite.json()["platform_role"] == "support"
    assert invite.json()["status"] == "active"

    role = await client.patch(
        f"/api/v1/admin/team/{member_id}/role",
        headers=sa["headers"],
        json={"platform_role": "catalog_manager"},
    )
    assert role.status_code == 200, role.text
    assert role.json()["platform_role"] == "catalog_manager"

    blocked = await client.post(
        "/api/v1/admin/team/super-admin/transfer",
        headers=sa["headers"],
        json={"recipient_member_id": member_id, "password": "wrong-password"},
    )
    assert blocked.status_code == 401

    transfer = await client.post(
        "/api/v1/admin/team/super-admin/transfer",
        headers=sa["headers"],
        json={"recipient_member_id": member_id, "password": PASSWORD},
    )
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["recipient_role"] == "super_admin"
    assert transfer.json()["caller_role"] == "platform_admin"

    team = await client.get("/api/v1/admin/team", headers=sa["headers"])
    assert team.status_code == 200, team.text
    roles = {m["email"]: m["platform_role"] for m in team.json()["items"]}
    assert roles["pa-rem-sa@example.com"] == "platform_admin"
    assert roles["pa-rem-team-member@example.com"] == "super_admin"

    promote = await client.post(
        f"/api/v1/admin/users/{recipient.user_id}/promote-operator",
        headers=sa["headers"],
    )
    assert promote.status_code == 200, promote.text
    team_after_promote = await client.get("/api/v1/admin/team", headers=sa["headers"])
    assert team_after_promote.status_code == 200
    assert any(
        m["email"] == "pa-rem-team-member@example.com" for m in team_after_promote.json()["items"]
    )
