from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.marketplace.test_platform_admin_governance import _operator, _verified_vendor
from tests.integration.resources.test_create_resource import register_verify_login

IMPORT_BODY = {
    "consents": {"data_processing": True, "third_party_transfer": True, "terms_confirmed": True},
    "connection": {
        "business_display_name": "Crafted Roots Co.",
        "contact_email": "hello@craftedroots.co",
        "gst_or_business_id": "27AAPCI234F1Z5",
        "affiliate_terms_accepted": True,
    },
}


@pytest.mark.asyncio
async def test_vendor_imports_sales_pipeline_and_works_board(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "vgp-op@example.com")
    vendor = await _verified_vendor(client, session_factory, "vgp-vendor@example.com", op["headers"])
    base = f"/api/v1/vendors/{vendor['vendor_id']}/growth-plugins"

    listed = await client.get(base, headers=vendor["headers"])
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [item["key"] for item in items] == ["sales-pipeline", "digital-marketing", "publicity"]
    sales = items[0]
    assert sales["installation_status"] == "not_imported"
    assert sales["price_label"] == "Free"
    assert len(sales["modules"]) == 6

    # Wizard cannot finish without the consents from steps 1 and 4.
    missing_consent = await client.post(
        f"{base}/sales-pipeline/import",
        headers=vendor["headers"],
        json={**IMPORT_BODY, "consents": {"data_processing": True}},
    )
    assert missing_consent.status_code == 422, missing_consent.text

    imported = await client.post(f"{base}/sales-pipeline/import", headers=vendor["headers"], json=IMPORT_BODY)
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["installation_status"] == "active"
    assert body["connection"]["business_display_name"] == "Crafted Roots Co."
    crm = next(m for m in body["vendor_modules"] if m["key"] == "crm-export")
    assert crm["enabled"] is False  # platform-disabled in Platform Admin

    board = await client.get(f"{base}/sales-pipeline/board", headers=vendor["headers"])
    assert board.status_code == 200, board.text
    board_body = board.json()
    assert [stage["label"] for stage in board_body["stages"]] == [
        "New Lead",
        "Contacted",
        "Proposal Sent",
        "Negotiation",
        "Closed",
    ]
    assert len(board_body["deals"]) == 7  # sample board seeded on import
    assert board_body["stats"]["deals_open"] == 6
    assert board_body["stats"]["total_pipeline_inr"] == 315000
    assert len(board_body["followups"]) == 3

    created = await client.post(
        f"{base}/sales-pipeline/deals",
        headers=vendor["headers"],
        json={"company": "New Buyer Co", "contact_name": "Retail", "value_inr": 50000},
    )
    assert created.status_code == 201, created.text
    deal_id = created.json()["deal_id"]
    assert created.json()["stage"] == "new-lead"

    moved = await client.patch(
        f"{base}/sales-pipeline/deals/{deal_id}",
        headers=vendor["headers"],
        json={"stage": "negotiation"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["stage"] == "negotiation"

    followup_id = board_body["followups"][0]["followup_id"]
    done = await client.post(
        f"{base}/sales-pipeline/followups/{followup_id}/complete", headers=vendor["headers"]
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"

    # Plugin Settings: vendor can turn a module off, never on past the platform.
    settings = await client.patch(
        f"{base}/sales-pipeline",
        headers=vendor["headers"],
        json={
            "modules": [
                {"key": "lead-capture", "label": "Lead Capture & Scoring", "enabled": False},
                {"key": "crm-export", "label": "CRM Export", "enabled": True},
            ]
        },
    )
    assert settings.status_code == 200, settings.text
    modules = {m["key"]: m["enabled"] for m in settings.json()["vendor_modules"]}
    assert modules["lead-capture"] is False
    assert modules["crm-export"] is False

    other = await register_verify_login(client, session_factory, "vgp-other@example.com")
    forbidden = await client.get(base, headers={"Authorization": f"Bearer {other.token}"})
    assert forbidden.status_code == 403, forbidden.text

    anon = await client.get(base)
    assert anon.status_code == 401, anon.text


@pytest.mark.asyncio
async def test_vendor_imports_digital_marketing_and_works_campaigns(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "vgp-dm-op@example.com")
    vendor = await _verified_vendor(client, session_factory, "vgp-dm-vendor@example.com", op["headers"])
    base = f"/api/v1/vendors/{vendor['vendor_id']}/growth-plugins"

    board_before = await client.get(f"{base}/digital-marketing/board", headers=vendor["headers"])
    assert board_before.status_code == 404, board_before.text

    imported = await client.post(
        f"{base}/digital-marketing/import", headers=vendor["headers"], json=IMPORT_BODY
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["installation_status"] == "active"
    assert len(imported.json()["vendor_modules"]) == 7

    board = await client.get(f"{base}/digital-marketing/board", headers=vendor["headers"])
    assert board.status_code == 200, board.text
    body = board.json()
    assert len(body["campaigns"]) == 5  # sample campaigns seeded on import
    assert body["stats"]["total_ad_spend_inr"] == 41600
    assert body["stats"]["conversions"] == 284
    assert body["stats"]["cost_per_conversion_inr"] == 146
    assert [row["stage"] for row in body["race_funnel"]] == ["Reach", "Act", "Convert", "Engage"]
    assert body["daily_spend_cap_inr"] == 50000

    created = await client.post(
        f"{base}/digital-marketing/campaigns",
        headers=vendor["headers"],
        json={"name": "Spring Sale", "channel": "Meta + Google", "spend_inr": 3000, "status": "live"},
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["campaign_id"]

    over_cap = await client.post(
        f"{base}/digital-marketing/campaigns",
        headers=vendor["headers"],
        json={"name": "Too Big", "channel": "Meta", "spend_inr": 60000, "status": "live"},
    )
    assert over_cap.status_code == 422, over_cap.text

    paused = await client.patch(
        f"{base}/digital-marketing/campaigns/{campaign_id}",
        headers=vendor["headers"],
        json={"status": "paused"},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_vendor_imports_publicity_and_publishes_release(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "vgp-pub-op@example.com")
    vendor = await _verified_vendor(client, session_factory, "vgp-pub-vendor@example.com", op["headers"])
    base = f"/api/v1/vendors/{vendor['vendor_id']}/growth-plugins"

    board_before = await client.get(f"{base}/publicity/board", headers=vendor["headers"])
    assert board_before.status_code == 404, board_before.text

    imported = await client.post(f"{base}/publicity/import", headers=vendor["headers"], json=IMPORT_BODY)
    assert imported.status_code == 200, imported.text
    assert imported.json()["lifecycle"] == "beta"
    modules = {m["key"]: m["enabled"] for m in imported.json()["vendor_modules"]}
    assert modules["press-release-builder"] is True
    assert modules["pr-mention-tracker"] is False  # "Soon" in Platform Admin

    board = await client.get(f"{base}/publicity/board", headers=vendor["headers"])
    assert board.status_code == 200, board.text
    body = board.json()
    assert body["stats"]["releases_sent"] == 4
    assert body["stats"]["drafts"] == 1
    assert body["ai_tokens_per_month"] == 100000
    assert [t["label"] for t in body["templates"]] == [
        "Product Launch",
        "Festival Campaign",
        "Partnership Announcement",
        "Award / Recognition",
    ]

    draft = await client.post(
        f"{base}/publicity/ai-draft",
        headers=vendor["headers"],
        json={"template": "product-launch", "topic": "a New Monsoon Artisan Range"},
    )
    assert draft.status_code == 200, draft.text
    assert "FOR IMMEDIATE RELEASE" in draft.json()["body"]
    assert "Crafted Roots Co." in draft.json()["headline"]

    created = await client.post(
        f"{base}/publicity/releases",
        headers=vendor["headers"],
        json={
            "headline": draft.json()["headline"],
            "template": "product-launch",
            "distribution": "pr-newswire",
            "body": draft.json()["body"],
        },
    )
    assert created.status_code == 201, created.text
    release_id = created.json()["release_id"]
    assert created.json()["status"] == "draft"

    distributed = await client.patch(
        f"{base}/publicity/releases/{release_id}",
        headers=vendor["headers"],
        json={"status": "sent"},
    )
    assert distributed.status_code == 200, distributed.text
    assert distributed.json()["status"] == "sent"

    after = await client.get(f"{base}/publicity/board", headers=vendor["headers"])
    assert after.json()["stats"]["releases_sent"] == 5

    empty_sent = await client.post(
        f"{base}/publicity/releases",
        headers=vendor["headers"],
        json={"headline": "", "body": "", "status": "sent"},
    )
    assert empty_sent.status_code == 422, empty_sent.text
