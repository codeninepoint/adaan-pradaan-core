from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from tenant.infrastructure.models import OrganizationRow, TenantRow
from tests.integration.resources.test_create_resource import register_verify_login


@pytest.mark.asyncio
async def test_j07_org_upgrade(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "org-upgrade@example.com")
    headers = {"Authorization": f"Bearer {auth.token}"}

    submit = await client.post(
        "/api/v1/organizations/register",
        headers=headers,
        json={
            "name": "Acme Corp",
            "slug": "acme-corp",
            "contact_name": "Alice",
            "contact_email": "alice@acme.com",
            "country": "IN",
        },
    )
    assert submit.status_code == 202, submit.text
    body = submit.json()
    assert body["status"] == "completed"
    assert body["keycloak_realm_ref"] == "acme-corp"
    request_id = body["request_id"]
    org_id = body["org_id"]

    poll = await client.get(f"/api/v1/organizations/register/{request_id}", headers=headers)
    assert poll.status_code == 200
    assert poll.json()["status"] == "completed"

    async with session_factory() as session:
        org = await session.get(OrganizationRow, uuid.UUID(org_id))
        assert org is not None
        assert org.org_type == "organization"
        assert org.slug == "acme-corp"
        assert org.keycloak_realm_ref == "acme-corp"
        tenants = (
            await session.execute(select(TenantRow).where(TenantRow.organization_id == org.id))
        ).scalars().all()
        assert any(t.slug == "acme-corp-default" for t in tenants)

    again = await client.post(
        "/api/v1/organizations/register",
        headers=headers,
        json={
            "name": "Other",
            "slug": "other-corp",
            "contact_name": "Alice",
            "contact_email": "alice@acme.com",
            "country": "IN",
        },
    )
    assert again.status_code == 403


@pytest.mark.asyncio
async def test_j08_j09_service_accounts(client: AsyncClient, session_factory) -> None:
    auth = await register_verify_login(client, session_factory, "sa-keys@example.com")
    headers = {
        "Authorization": f"Bearer {auth.token}",
        "X-Tenant-Id": str(auth.tenant_id),
    }

    create = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/service-accounts",
        headers=headers,
        json={
            "name": "sa-deploy-prod",
            "description": "CI bot",
            "initial_role": "resource-admin",
        },
    )
    assert create.status_code == 201, create.text
    created = create.json()
    assert created["api_key"].startswith("ak_")
    assert created["role_assigned"] == "resource-admin"
    sa_id = created["service_account_id"]
    key_id = created["key_id"]

    listed = await client.get(
        f"/api/v1/tenants/{auth.tenant_id}/service-accounts", headers=headers
    )
    assert listed.status_code == 200
    assert any(i["service_account_id"] == sa_id for i in listed.json()["items"])

    rotate = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/service-accounts/{sa_id}/api-keys/rotate",
        headers=headers,
        json={"reason": "routine"},
    )
    assert rotate.status_code == 200, rotate.text
    rotated = rotate.json()
    assert rotated["old_key_status"] == "revoked"
    assert rotated["new_api_key"].startswith("ak_")
    new_key_id = rotated["new_key_id"]

    revoke = await client.request(
        "DELETE",
        f"/api/v1/tenants/{auth.tenant_id}/service-accounts/{sa_id}/api-keys/{new_key_id}",
        headers=headers,
        json={"reason": "compromised"},
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["status"] == "revoked"

    # old key id already revoked
    again = await client.request(
        "DELETE",
        f"/api/v1/tenants/{auth.tenant_id}/service-accounts/{sa_id}/api-keys/{key_id}",
        headers=headers,
        json={},
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_j14_j19_invite_and_j20_j21_vendor(client: AsyncClient, session_factory) -> None:
    owner = await register_verify_login(client, session_factory, "invite-owner@example.com")
    invitee = await register_verify_login(client, session_factory, "invitee@example.com")
    owner_headers = {"Authorization": f"Bearer {owner.token}"}

    # Upgrade owner org first (vendor requires organization)
    up = await client.post(
        "/api/v1/organizations/register",
        headers=owner_headers,
        json={
            "name": "Invite Org",
            "slug": "invite-org",
            "contact_name": "Owner",
            "contact_email": "invite-owner@example.com",
            "country": "US",
        },
    )
    assert up.status_code == 202, up.text
    org_id = up.json()["org_id"]

    # Refresh me to find org-default tenant
    me = await client.get("/auth/me", headers=owner_headers)
    assert me.status_code == 200
    tenants = me.json()["tenants"]
    org_default = next(t for t in tenants if t["slug"] == "invite-org-default")
    tenant_id = org_default["tenant_id"]

    # J19 org invite
    org_invite = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_headers,
        json={"email": "invitee@example.com", "org_role": "member"},
    )
    assert org_invite.status_code == 201, org_invite.text
    assert org_invite.json()["status"] == "invited"

    invitee_headers = {"Authorization": f"Bearer {invitee.token}"}
    accept = await client.post(
        f"/api/v1/organizations/{org_id}/members/accept",
        headers=invitee_headers,
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["status"] == "active"

    # J14 tenant invite
    tenant_invite = await client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        headers={**owner_headers, "X-Tenant-Id": tenant_id},
        json={"user_id": str(invitee.user_id), "role": "viewer"},
    )
    assert tenant_invite.status_code == 201, tenant_invite.text
    assert tenant_invite.json()["role"] == "viewer"

    # J20 eligibility
    elig = await client.get(
        f"/api/v1/organizations/{org_id}/vendor-eligibility",
        headers=owner_headers,
    )
    assert elig.status_code == 200
    assert elig.json()["eligible"] is True

    # J21 register
    reg = await client.post(
        f"/api/v1/organizations/{org_id}/vendor/register",
        headers=owner_headers,
        json={
            "legal_name": "Invite Org Pvt Ltd",
            "tax_id": "27AAAAA0000A1Z5",
            "payout_bank_account": "XXXXXXXX1234",
            "contact_email": "vendor-ops@invite.org",
            "business_doc_url": "https://uploads.example.com/doc.pdf",
        },
    )
    assert reg.status_code == 202, reg.text
    vendor_id = reg.json()["vendor_id"]
    verification_id = reg.json()["verification_id"]

    status = await client.get(
        f"/api/v1/vendors/{vendor_id}/verification",
        headers=owner_headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "pending_verification"

    # Decision requires platform operator — expect 403 for normal owner
    decision = await client.post(
        f"/api/v1/admin/vendor-verifications/{verification_id}/decision",
        headers=owner_headers,
        json={"decision": "approved", "notes": "ok"},
    )
    assert decision.status_code == 403


@pytest.mark.asyncio
async def test_individual_vendor_then_organization(client: AsyncClient, session_factory) -> None:
    """Vendor registration is allowed on an individual org, and a later org upgrade keeps it."""
    auth = await register_verify_login(client, session_factory, "vendor-first@example.com")
    headers = {"Authorization": f"Bearer {auth.token}"}

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    org = me.json()["organizations"][0]
    org_id = org["org_id"]
    assert org["org_type"] == "individual"
    assert org["participation"] == "consumer"

    elig = await client.get(
        f"/api/v1/organizations/{org_id}/vendor-eligibility",
        headers=headers,
    )
    assert elig.status_code == 200
    assert elig.json()["eligible"] is True

    reg = await client.post(
        f"/api/v1/organizations/{org_id}/vendor/register",
        headers=headers,
        json={
            "legal_name": "Solo Vendor",
            "tax_id": "27AAAAA0000A1Z5",
            "payout_bank_account": "XXXXXXXX1234",
            "contact_email": "vendor-first@example.com",
            "business_doc_url": "https://uploads.example.com/doc.pdf",
        },
    )
    assert reg.status_code == 202, reg.text
    vendor_id = reg.json()["vendor_id"]

    again = await client.post(
        f"/api/v1/organizations/{org_id}/vendor/register",
        headers=headers,
        json={
            "legal_name": "Solo Vendor",
            "tax_id": "27AAAAA0000A1Z5",
            "payout_bank_account": "XXXXXXXX1234",
            "contact_email": "vendor-first@example.com",
            "business_doc_url": "https://uploads.example.com/doc.pdf",
        },
    )
    assert again.status_code == 409

    me_vendor = await client.get("/auth/me", headers=headers)
    vendor_org = next(o for o in me_vendor.json()["organizations"] if o["org_id"] == org_id)
    assert vendor_org["org_type"] == "individual"
    assert vendor_org["participation"] == "consumer_and_vendor"

    upgrade = await client.post(
        "/api/v1/organizations/register",
        headers=headers,
        json={
            "name": "Solo Org",
            "slug": "solo-org",
            "contact_name": "Vendor",
            "contact_email": "vendor-first@example.com",
            "country": "IN",
        },
    )
    assert upgrade.status_code == 202, upgrade.text
    assert upgrade.json()["status"] == "completed"
    assert upgrade.json()["org_id"] == org_id

    me_org = await client.get("/auth/me", headers=headers)
    upgraded = next(o for o in me_org.json()["organizations"] if o["org_id"] == org_id)
    assert upgraded["org_type"] == "organization"
    assert upgraded["participation"] == "consumer_and_vendor"

    status = await client.get(f"/api/v1/vendors/{vendor_id}/verification", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["vendor_id"] == vendor_id
    assert status.json()["status"] == "pending_verification"


@pytest.mark.asyncio
async def test_operator_approves_vendor_verification(client: AsyncClient, session_factory) -> None:
    applicant = await register_verify_login(client, session_factory, "vendor-applicant@example.com")
    operator = await register_verify_login(client, session_factory, "vendor-operator@example.com")
    stranger = await register_verify_login(client, session_factory, "vendor-stranger@example.com")
    applicant_headers = {"Authorization": f"Bearer {applicant.token}"}
    operator_headers = {"Authorization": f"Bearer {operator.token}"}

    me = await client.get("/auth/me", headers=applicant_headers)
    org_id = me.json()["organizations"][0]["org_id"]
    op_me = await client.get("/auth/me", headers=operator_headers)
    operator_org_id = op_me.json()["organizations"][0]["org_id"]

    async with session_factory() as session:
        org = await session.get(OrganizationRow, uuid.UUID(operator_org_id))
        assert org is not None
        org.is_platform_operator = True
        await session.commit()

    reg = await client.post(
        f"/api/v1/organizations/{org_id}/vendor/register",
        headers=applicant_headers,
        json={
            "legal_name": "Queued Vendor",
            "tax_id": "27AAAAA0000A1Z5",
            "payout_bank_account": "XXXXXXXX1234",
            "contact_email": "vendor-applicant@example.com",
            "business_doc_url": "https://uploads.example.com/doc.pdf",
        },
    )
    assert reg.status_code == 202, reg.text
    vendor_id = reg.json()["vendor_id"]
    verification_id = reg.json()["verification_id"]

    denied = await client.get(
        "/api/v1/admin/vendor-verifications",
        headers={"Authorization": f"Bearer {stranger.token}"},
    )
    assert denied.status_code == 403

    queue = await client.get("/api/v1/admin/vendor-verifications", headers=operator_headers)
    assert queue.status_code == 200, queue.text
    assert any(item["verification_id"] == verification_id for item in queue.json()["items"])

    decision = await client.post(
        f"/api/v1/admin/vendor-verifications/{verification_id}/decision",
        headers=operator_headers,
        json={"decision": "approved", "notes": "looks good"},
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "approved"

    status = await client.get(
        f"/api/v1/vendors/{vendor_id}/verification",
        headers=applicant_headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "verified"
    assert status.json()["verification_status"] == "approved"

    queue_after = await client.get("/api/v1/admin/vendor-verifications", headers=operator_headers)
    assert queue_after.status_code == 200
    assert all(item["verification_id"] != verification_id for item in queue_after.json()["items"])
