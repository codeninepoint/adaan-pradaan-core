from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.integration.resources.test_create_resource import register_verify_login


@pytest.mark.asyncio
async def test_auth_me_includes_last_login_and_mfa_flag(
    client: AsyncClient, session_factory
) -> None:
    auth = await register_verify_login(client, session_factory, "acct-me@example.com")
    headers = {"Authorization": f"Bearer {auth.token}"}

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    body = me.json()
    assert "last_login_at" in body
    assert body["last_login_at"] is not None
    assert "mfa_enabled" in body
    assert body["mfa_enabled"] is False
    assert body["email"] == "acct-me@example.com"


@pytest.mark.asyncio
async def test_service_account_list_includes_expiry_fields(
    client: AsyncClient, session_factory
) -> None:
    auth = await register_verify_login(client, session_factory, "acct-sa@example.com")
    headers = {
        "Authorization": f"Bearer {auth.token}",
        "X-Tenant-Id": str(auth.tenant_id),
    }

    create = await client.post(
        f"/api/v1/tenants/{auth.tenant_id}/service-accounts",
        headers=headers,
        json={
            "name": "svc-webhook-receiver",
            "description": "Webhook bot",
            "initial_role": "resource-admin",
        },
    )
    assert create.status_code == 201, create.text
    sa_id = create.json()["service_account_id"]

    listed = await client.get(
        f"/api/v1/tenants/{auth.tenant_id}/service-accounts", headers=headers
    )
    assert listed.status_code == 200, listed.text
    item = next(i for i in listed.json()["items"] if i["service_account_id"] == sa_id)
    assert item["account_type"] == "service_account"
    assert item["last_used_at"] is None
    assert item["expires_at"] is not None
    expires = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    assert timedelta(days=89) < (expires - now) < timedelta(days=91)
