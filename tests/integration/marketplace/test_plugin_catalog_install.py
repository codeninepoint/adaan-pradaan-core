from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from marketplace.infrastructure.models import InstallationRow, PayoutLedgerRow, ServiceInstanceRow
from shared.infrastructure.models import OutboxEventRow
from shared.infrastructure.outbox_processor import OutboxProcessor
from tenant.infrastructure.models import OrganizationRow, ProjectRow
from tests.integration.resources.test_create_resource import register_verify_login


async def _verified_vendor(client: AsyncClient, session_factory, email: str) -> dict:
    applicant = await register_verify_login(client, session_factory, email)
    operator = await register_verify_login(
        client, session_factory, f"op-{email}"
    )
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
            "legal_name": "Acme Metrics",
            "tax_id": "27AAAAA0000A1Z5",
            "payout_bank_account": "XXXXXXXX1234",
            "contact_email": email,
            "business_doc_url": "https://uploads.example.com/doc.pdf",
        },
    )
    assert reg.status_code == 202, reg.text
    verification_id = reg.json()["verification_id"]
    decision = await client.post(
        f"/api/v1/admin/vendor-verifications/{verification_id}/decision",
        headers=operator_headers,
        json={"decision": "approved", "notes": "ok"},
    )
    assert decision.status_code == 200, decision.text
    return {
        "vendor_id": reg.json()["vendor_id"],
        "org_id": org_id,
        "headers": applicant_headers,
        "operator_headers": operator_headers,
        "tenant_id": str(applicant.tenant_id),
        "buyer": applicant,
    }


@pytest.mark.asyncio
async def test_plugin_core_then_catalog_install(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    vendor = await _verified_vendor(client, session_factory, "plugin-vendor@example.com")
    headers = vendor["headers"]
    vendor_id = vendor["vendor_id"]

    pending = await client.post(
        f"/api/v1/vendors/{vendor_id}/plugins",
        headers={"Authorization": f"Bearer {(await register_verify_login(client, session_factory, 'unverified-plugin@example.com')).token}"},
        json={
            "name": "Nope",
            "slug": "nope-plugin",
            "category": "risk_management",
            "short_description": "should fail",
        },
    )
    assert pending.status_code == 403

    created = await client.post(
        f"/api/v1/vendors/{vendor_id}/plugins",
        headers=headers,
        json={
            "name": "Acme Fraud Scoring",
            "slug": "acme-fraud-scoring",
            "category": "risk_management",
            "short_description": "Real-time scoring",
        },
    )
    assert created.status_code == 201, created.text
    plugin_id = created.json()["plugin_id"]
    assert created.json()["status"] == "draft"
    mine = await client.get(f"/api/v1/organizations/{vendor['org_id']}/vendor", headers=headers)
    assert mine.status_code == 200, mine.text
    assert mine.json()["vendor_id"] == vendor_id
    listed = await client.get(f"/api/v1/vendors/{vendor_id}/plugins", headers=headers)
    assert listed.status_code == 200, listed.text
    assert plugin_id in {item["plugin_id"] for item in listed.json()["plugins"]}

    duplicate = await client.post(
        f"/api/v1/vendors/{vendor_id}/plugins",
        headers=headers,
        json={
            "name": "Other",
            "slug": "acme-fraud-scoring",
            "category": "risk_management",
            "short_description": "dup",
        },
    )
    assert duplicate.status_code == 409

    missing_sbom = await client.post(
        f"/api/v1/plugins/{plugin_id}/versions",
        headers=headers,
        json={
            "version": "1.0.0",
            "artifact_url": "oci://registry.example/acme:1.0.0",
            "changelog": "Initial",
            "sbom_url": "",
        },
    )
    assert missing_sbom.status_code == 422

    submitted = await client.post(
        f"/api/v1/plugins/{plugin_id}/versions",
        headers=headers,
        json={
            "version": "1.0.0",
            "artifact_url": "oci://registry.example/acme:1.0.0",
            "changelog": "Initial release.",
            "sbom_url": "https://uploads.example.com/sbom.json",
        },
    )
    assert submitted.status_code == 201, submitted.text
    version_id = submitted.json()["version_id"]
    assert submitted.json()["status"] == "pending_review"

    caps = await client.put(
        f"/api/v1/plugins/versions/{version_id}/capabilities",
        headers=headers,
        json={
            "capabilities": [
                {"scope": "transactions.read", "justification": "Score transactions"},
                {"scope": "webhooks.publish", "justification": "Emit events"},
            ]
        },
    )
    assert caps.status_code == 200, caps.text
    assert caps.json()["capability_count"] == 2

    review = await client.get(
        f"/api/v1/plugins/versions/{version_id}/review",
        headers=vendor["operator_headers"],
    )
    assert review.status_code == 200, review.text
    assert set(review.json()["requested_capabilities"]) == {
        "transactions.read",
        "webhooks.publish",
    }
    denied_review = await client.get(
        f"/api/v1/plugins/versions/{version_id}/review", headers=headers
    )
    assert denied_review.status_code == 403
    claim = await client.post(
        f"/api/v1/admin/plugin-reviews/{version_id}/claim",
        headers=vendor["operator_headers"],
    )
    assert claim.status_code == 200, claim.text

    history = await client.get(f"/api/v1/plugins/{plugin_id}/versions", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()["versions"][0]["version"] == "1.0.0"

    portal = await client.get(f"/api/v1/vendors/{vendor_id}/portal", headers=headers)
    assert portal.status_code == 200, portal.text
    assert portal.json()["pending_plugin_reviews"] == 1
    changes = await client.post(
        f"/api/v1/plugins/versions/{version_id}/request-changes",
        headers=vendor["operator_headers"],
        json={"notes": "Narrow transactions.read"},
    )
    assert changes.status_code == 200, changes.text
    assert changes.json()["status"] == "changes_requested"

    product = await client.post(
        f"/api/v1/vendors/{vendor_id}/products",
        headers=headers,
        json={
            "name": "Fraud Scoring Suite",
            "description": "Real-time and batch fraud scoring.",
            "plugin_id": plugin_id,
            "fulfilment_type": "PROVISION_SOFTWARE",
            "content": {"regions": ["ap-south-1"]},
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["product_id"]
    assert product.json()["status"] == "draft"

    bad_type = await client.post(
        f"/api/v1/vendors/{vendor_id}/products",
        headers=headers,
        json={
            "name": "Bad",
            "plugin_id": plugin_id,
            "fulfilment_type": "NOT_A_TYPE",
        },
    )
    assert bad_type.status_code == 422

    offering = await client.post(
        f"/api/v1/products/{product_id}/offerings",
        headers=headers,
        json={
            "plan_name": "Pro",
            "billing_period": "monthly",
            "price_usd": 499,
            "included_transactions": 100000,
            "overage_price_per_1k": 2.5,
        },
    )
    assert offering.status_code == 201, offering.text
    offering_id = offering.json()["offering_id"]

    too_soon = await client.post(
        f"/api/v1/offerings/{offering_id}/publish", headers=headers
    )
    assert too_soon.status_code == 409

    queue = await client.get("/api/v1/admin/plugin-reviews", headers=vendor["operator_headers"])
    assert queue.status_code == 200, queue.text
    assert version_id in {item["version_id"] for item in queue.json()["items"]}
    denied = await client.get("/api/v1/admin/plugin-reviews", headers=headers)
    assert denied.status_code == 403

    approved = await client.post(
        f"/api/v1/admin/plugin-reviews/{version_id}/decision",
        headers=vendor["operator_headers"],
        json={"decision": "approved", "notes": "SBOM clean"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    frozen = await client.put(
        f"/api/v1/plugins/versions/{version_id}/capabilities",
        headers=headers,
        json={"capabilities": [{"scope": "other.read", "justification": "no"}]},
    )
    assert frozen.status_code == 409

    published = await client.post(
        f"/api/v1/offerings/{offering_id}/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    catalog = await client.get(
        "/api/v1/marketplace/catalog", params={"category": "risk_management", "q": "Fraud"}
    )
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["total"] == 1
    assert catalog.json()["results"][0]["price_usd"] == 499

    home = await client.get("/api/v1/marketplace/home")
    assert home.status_code == 200
    assert home.json()["rails"]["new"]

    detail = await client.get(f"/api/v1/marketplace/products/{product_id}")
    assert detail.status_code == 200, detail.text
    assert set(detail.json()["capabilities"]) == {"transactions.read", "webhooks.publish"}

    physical = await client.post(
        f"/api/v1/vendors/{vendor_id}/products",
        headers=headers,
        json={
            "name": "Journal",
            "plugin_id": plugin_id,
            "fulfilment_type": "SHIP_PHYSICAL",
            "content": {"variants": [{"name": "Hardcover", "sku": "JRN-1"}]},
        },
    )
    assert physical.status_code == 201
    physical_offering = await client.post(
        f"/api/v1/products/{physical.json()['product_id']}/offerings",
        headers=headers,
        json={"plan_name": "Each", "billing_period": "one_time", "price_usd": 12},
    )
    physical_pub = await client.post(
        f"/api/v1/offerings/{physical_offering.json()['offering_id']}/publish",
        headers=headers,
    )
    assert physical_pub.status_code == 200

    async with session_factory() as session:
        project = (
            await session.execute(
                select(ProjectRow).where(ProjectRow.tenant_id == uuid.UUID(vendor["tenant_id"]))
            )
        ).scalars().first()
        assert project is not None
        project_id = str(project.id)

    cart_only = await client.post(
        f"/api/v1/tenants/{vendor['tenant_id']}/installations",
        headers=headers,
        json={
            "offering_id": physical_offering.json()["offering_id"],
            "project_id": project_id,
            "accepted_capabilities": ["transactions.read", "webhooks.publish"],
        },
    )
    assert cart_only.status_code == 409

    tenant_id = vendor["tenant_id"]
    physical_offering_id = physical_offering.json()["offering_id"]
    software_cart = await client.post(
        f"/api/v1/tenants/{tenant_id}/cart/lines",
        headers=headers,
        json={"offering_id": offering_id, "quantity": 1},
    )
    assert software_cart.status_code == 409, software_cart.text
    added = await client.post(
        f"/api/v1/tenants/{tenant_id}/cart/lines",
        headers=headers,
        json={"offering_id": physical_offering_id, "quantity": 1},
    )
    assert added.status_code == 200, added.text
    assert added.json()["lines"][0]["product_name"] == "Journal"
    duplicate_line = await client.post(
        f"/api/v1/tenants/{tenant_id}/cart/lines",
        headers=headers,
        json={"offering_id": physical_offering_id, "quantity": 1},
    )
    assert duplicate_line.status_code == 409
    no_address = await client.post(
        f"/api/v1/tenants/{tenant_id}/orders",
        headers=headers,
        json={"payment_method": "upi"},
    )
    assert no_address.status_code == 422, no_address.text
    address = await client.post(
        f"/api/v1/tenants/{tenant_id}/addresses",
        headers=headers,
        json={
            "label": "Head Office",
            "contact_name": "Acme",
            "line1": "12 Linking Road",
            "city": "Mumbai",
            "state": "MH",
            "pincode": "400001",
            "phone": "+919800000000",
        },
    )
    assert address.status_code == 201, address.text
    placed = await client.post(
        f"/api/v1/tenants/{tenant_id}/orders",
        headers=headers,
        json={"address_id": address.json()["address_id"], "payment_method": "upi"},
    )
    assert placed.status_code == 201, placed.text
    assert placed.json()["status"] == "placed"
    detail = await client.get(f"/api/v1/orders/{placed.json()['order_id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["lines"][0]["fulfilment_type"] == "SHIP_PHYSICAL"
    vendor_orders = await client.get(f"/api/v1/vendors/{vendor_id}/orders", headers=headers)
    assert vendor_orders.status_code == 200, vendor_orders.text
    vendor_lines = vendor_orders.json()["lines"]
    assert len(vendor_lines) == 1
    assert vendor_lines[0]["product_name"] == "Journal"
    assert vendor_lines[0]["customer_name"] == "Acme"
    assert vendor_lines[0]["status"] == "placed"
    assert vendor_lines[0]["quantity"] == 1
    assert vendor_lines[0]["total"] == 12
    assert vendor_lines[0]["line1"] == "12 Linking Road"
    assert vendor_lines[0]["city"] == "Mumbai"
    assert vendor_lines[0]["phone"] == "+919800000000"
    other_status = await client.get(
        f"/api/v1/vendors/{vendor_id}/orders", headers=headers, params={"status": "fulfilled"}
    )
    assert other_status.status_code == 200
    assert other_status.json()["lines"] == []
    order_id = placed.json()["order_id"]

    async def advance(target: str, **extra: str):
        moved = await client.patch(
            f"/api/v1/vendors/{vendor_id}/orders/{order_id}",
            headers=headers,
            json={"status": target, **extra},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["status"] == target
        buyer = await client.get(f"/api/v1/orders/{order_id}", headers=headers)
        assert buyer.json()["status"] == "placed"
        return moved

    skipped = await client.patch(
        f"/api/v1/vendors/{vendor_id}/orders/{order_id}",
        headers=headers,
        json={"status": "shipped", "courier": "City Courier", "tracking_number": "TRK-JRN-1"},
    )
    assert skipped.status_code == 422, skipped.text
    await advance("confirmed")
    await advance("processing")
    await advance("ready_to_ship")
    missing_tracking = await client.patch(
        f"/api/v1/vendors/{vendor_id}/orders/{order_id}",
        headers=headers,
        json={"status": "shipped"},
    )
    assert missing_tracking.status_code == 422, missing_tracking.text
    shipped = await advance("shipped", courier="City Courier", tracking_number="TRK-JRN-1")
    assert shipped.json()["tracking_number"] == "TRK-JRN-1"
    assert shipped.json()["courier"] == "City Courier"
    await advance("delivered")
    delivered = await client.get(f"/api/v1/vendors/{vendor_id}/orders", headers=headers)
    delivered_line = next(item for item in delivered.json()["lines"] if item["order_id"] == order_id)
    assert delivered_line["status"] == "delivered"
    assert delivered_line["tracking_number"] == "TRK-JRN-1"
    again = await client.post(
        f"/api/v1/tenants/{tenant_id}/cart/lines",
        headers=headers,
        json={"offering_id": physical_offering_id, "quantity": 1},
    )
    assert again.status_code == 200, again.text
    placed_again = await client.post(
        f"/api/v1/tenants/{tenant_id}/orders",
        headers=headers,
        json={"address_id": address.json()["address_id"], "payment_method": "upi"},
    )
    assert placed_again.status_code == 201, placed_again.text
    rejected = await client.patch(
        f"/api/v1/vendors/{vendor_id}/orders/{placed_again.json()['order_id']}",
        headers=headers,
        json={"status": "cancelled"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "cancelled"
    warehouse = await client.post(
        f"/api/v1/vendors/{vendor_id}/warehouses",
        headers=headers,
        json={"name": "Mumbai Central", "location": "Mumbai, MH", "capacity": 100},
    )
    assert warehouse.status_code == 201, warehouse.text
    stock = await client.post(
        f"/api/v1/vendors/{vendor_id}/inventory",
        headers=headers,
        json={
            "product_id": physical.json()["product_id"],
            "warehouse_id": warehouse.json()["warehouse_id"],
            "sku": "JRN-1",
            "available": 4,
        },
    )
    assert stock.status_code == 201, stock.text
    adjusted = await client.patch(
        f"/api/v1/vendors/{vendor_id}/inventory/{stock.json()['inventory_id']}",
        headers=headers,
        json={"available": 3},
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["available"] == 3
    houses = await client.get(f"/api/v1/vendors/{vendor_id}/warehouses", headers=headers)
    assert houses.status_code == 200
    assert houses.json()["warehouses"][0]["sku_count"] == 1
    assert houses.json()["warehouses"][0]["capacity"] == 100
    assert houses.json()["warehouses"][0]["units_stored"] == 3
    renamed = await client.patch(
        f"/api/v1/vendors/{vendor_id}/warehouses/{warehouse.json()['warehouse_id']}",
        headers=headers,
        json={"name": "Mumbai Central", "location": "Mumbai, Maharashtra", "capacity": 80},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["capacity"] == 80
    assert renamed.json()["units_stored"] == 3
    catalog_products = await client.get(f"/api/v1/vendors/{vendor_id}/products", headers=headers)
    journal = next(item for item in catalog_products.json()["products"] if item["name"] == "Journal")
    assert journal["content"]["variants"][0]["sku"] == "JRN-1"
    offering_list = await client.get(f"/api/v1/vendors/{vendor_id}/offerings", headers=headers)
    journal_offering = next(
        item for item in offering_list.json()["offerings"] if item["product_id"] == physical.json()["product_id"]
    )
    assert journal_offering["price_usd"] == 12
    edited = await client.patch(
        f"/api/v1/products/{physical.json()['product_id']}",
        headers=headers,
        json={
            "category": "Stationery",
            "content": {"variants": [{"name": "Softcover", "sku": "JRN-1"}]},
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["category"] == "Stationery"
    assert edited.json()["content"]["variants"][0]["name"] == "Softcover"
    priced = await client.patch(
        f"/api/v1/offerings/{physical_offering.json()['offering_id']}",
        headers=headers,
        json={"price_usd": 14},
    )
    assert priced.status_code == 200, priced.text
    assert priced.json()["price_usd"] == 14
    stock_rows = await client.get(f"/api/v1/vendors/{vendor_id}/inventory", headers=headers)
    assert stock_rows.json()["rows"][0]["sku"] == "JRN-1"
    assert stock_rows.json()["rows"][0]["available"] == 3
    opened = await client.post(
        f"/api/v1/orders/{placed.json()['order_id']}/returns",
        headers=headers,
        json={"line_id": detail.json()["lines"][0]["line_id"], "reason": "Damaged on arrival"},
    )
    assert opened.status_code == 201, opened.text
    vendor_returns = await client.get(f"/api/v1/vendors/{vendor_id}/returns", headers=headers)
    assert vendor_returns.status_code == 200, vendor_returns.text
    assert vendor_returns.json()["returns"][0]["status"] == "requested"
    assert vendor_returns.json()["returns"][0]["customer_name"] == "Acme"
    customers = await client.get(f"/api/v1/vendors/{vendor_id}/customers", headers=headers)
    assert customers.status_code == 200, customers.text
    assert customers.json()["customers"][0]["customer_name"] == "Acme"
    assert customers.json()["customers"][0]["order_count"] == 2
    assert customers.json()["customers"][0]["total"] == 24
    async with session_factory() as session:
        session.add(
            PayoutLedgerRow(
                vendor_id=uuid.UUID(vendor_id),
                period="2026-09",
                gross=100,
                platform_fee=20,
                net=80,
                status="paid",
            )
        )
        await session.commit()
    payouts = await client.get(f"/api/v1/vendors/{vendor_id}/payouts", headers=headers)
    assert payouts.status_code == 200, payouts.text
    assert payouts.json()["currency"] == "USD"
    assert payouts.json()["this_period"]["gross"] == 100
    assert payouts.json()["this_period"]["platform_fee"] == 20
    assert payouts.json()["payouts"][0]["net"] == 80
    settings = await client.get(f"/api/v1/vendors/{vendor_id}/settings", headers=headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()["legal_name"] == "Acme Metrics"
    assert settings.json()["tax_id"] == "27AAAAA0000A1Z5"
    invalid_ifsc = await client.patch(
        f"/api/v1/vendors/{vendor_id}/settings",
        headers=headers,
        json={"bank_ifsc": "nope"},
    )
    assert invalid_ifsc.status_code == 422
    saved_settings = await client.patch(
        f"/api/v1/vendors/{vendor_id}/settings",
        headers=headers,
        json={
            "support_email": "support@example.com",
            "bank_account_name": "Acme Metrics",
            "bank_account_number": "1234567890",
            "bank_ifsc": "HDFC0001234",
            "notify_install": False,
        },
    )
    assert saved_settings.status_code == 200, saved_settings.text
    assert saved_settings.json()["bank_account_number"] == "XXXXXX7890"
    assert saved_settings.json()["notify_install"] is False
    support = await client.post(
        f"/api/v1/vendors/{vendor_id}/support-requests",
        headers=headers,
        json={"subject": "Payout delayed", "message": "June payout still pending."},
    )
    assert support.status_code == 201, support.text
    assert support.json()["status"] == "open"
    listed_support = await client.get(
        f"/api/v1/vendors/{vendor_id}/support-requests", headers=headers
    )
    assert listed_support.status_code == 200
    assert listed_support.json()["requests"][0]["subject"] == "Payout delayed"
    saved = await client.post(
        f"/api/v1/tenants/{tenant_id}/wishlist",
        headers=headers,
        json={"product_id": physical.json()["product_id"]},
    )
    assert saved.status_code == 201, saved.text
    again_saved = await client.post(
        f"/api/v1/tenants/{tenant_id}/wishlist",
        headers=headers,
        json={"product_id": physical.json()["product_id"]},
    )
    assert again_saved.status_code == 409

    mismatch = await client.post(
        f"/api/v1/tenants/{vendor['tenant_id']}/installations",
        headers=headers,
        json={
            "offering_id": offering_id,
            "project_id": project_id,
            "accepted_capabilities": ["transactions.read"],
        },
    )
    assert mismatch.status_code == 409

    installed = await client.post(
        f"/api/v1/tenants/{vendor['tenant_id']}/installations",
        headers=headers,
        json={
            "offering_id": offering_id,
            "project_id": project_id,
            "accepted_capabilities": ["webhooks.publish", "transactions.read"],
        },
    )
    assert installed.status_code == 202, installed.text
    assert installed.json()["status"] == "active"
    installation_id = installed.json()["installation_id"]

    async with session_factory() as session:
        processor = OutboxProcessor(session)
        processed = await processor.process_pending()
        assert processed >= 1
        installation = await session.get(InstallationRow, uuid.UUID(installation_id))
        assert installation is not None
        assert installation.status == "active"
        instance = (
            await session.execute(
                select(ServiceInstanceRow).where(
                    ServiceInstanceRow.installation_id == installation.id
                )
            )
        ).scalar_one()
        assert instance.status == "active"
        scans = (
            await session.execute(
                select(OutboxEventRow).where(OutboxEventRow.type == "scan_plugin_artifact")
            )
        ).scalars().all()
        assert scans
        assert all(row.status == "processed" for row in scans)

    entitlements = await client.get(
        f"/api/v1/tenants/{vendor['tenant_id']}/entitlements", headers=headers
    )
    assert entitlements.status_code == 200, entitlements.text
    assert entitlements.json()["entitlements"][0]["installation_status"] == "active"

    vendor_installs = await client.get(
        f"/api/v1/vendors/{vendor_id}/installations", headers=headers
    )
    assert vendor_installs.status_code == 200, vendor_installs.text
    assert vendor_installs.json()["installations"][0]["status"] == "active"

    portal_after = await client.get(f"/api/v1/vendors/{vendor_id}/portal", headers=headers)
    assert portal_after.json()["active_installs"] == 1
    assert portal_after.json()["product_count"] == 2

    archived = await client.post(f"/api/v1/products/{product_id}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    hidden = await client.get(f"/api/v1/marketplace/products/{product_id}")
    assert hidden.status_code == 404
    listed = await client.get(f"/api/v1/vendors/{vendor_id}/products", headers=headers)
    assert any(item["status"] == "archived" for item in listed.json()["products"])

    directory = await client.get(
        "/api/v1/admin/vendors",
        headers=vendor["operator_headers"],
        params={"status": "verified"},
    )
    assert directory.status_code == 200, directory.text
    assert vendor_id in {item["vendor_id"] for item in directory.json()["results"]}
    denied_suspend = await client.post(
        f"/api/v1/admin/vendors/{vendor_id}/suspend",
        headers=headers,
        json={"reason": "no"},
    )
    assert denied_suspend.status_code == 403
    suspended = await client.post(
        f"/api/v1/admin/vendors/{vendor_id}/suspend",
        headers=vendor["operator_headers"],
        json={"reason": "Repeated SBOM policy violations."},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"
    assert suspended.json()["offerings_unpublished"] >= 1
    again = await client.post(
        f"/api/v1/admin/vendors/{vendor_id}/suspend",
        headers=vendor["operator_headers"],
        json={"reason": "again"},
    )
    assert again.status_code == 409
    still_installed = await client.get(
        f"/api/v1/tenants/{vendor['tenant_id']}/entitlements", headers=headers
    )
    assert still_installed.json()["entitlements"][0]["installation_status"] == "active"
    hidden_catalog = await client.get("/api/v1/marketplace/catalog", params={"q": "Journal"})
    assert hidden_catalog.json()["total"] == 0
