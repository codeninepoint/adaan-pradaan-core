from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_ops.infrastructure.models import PlatformConfigRow
from tests.integration.marketplace.test_platform_admin_governance import (
    _operator,
    _verified_vendor,
)
from tests.integration.resources.test_create_resource import register_verify_login


async def _publish_physical(
    client: AsyncClient,
    *,
    op_headers: dict,
    vendor_id: str,
    vendor_headers: dict,
    name: str,
    sku: str,
    mrp: float,
) -> str:
    city = await client.post(
        f"/api/v1/vendors/{vendor_id}/service-cities",
        headers=vendor_headers,
        json={"city_name": "Mumbai"},
    )
    assert city.status_code == 201, city.text
    city_id = city.json()["city_id"]
    pins = await client.put(
        f"/api/v1/vendors/{vendor_id}/service-cities/{city_id}/pincodes",
        headers=vendor_headers,
        json={"pincodes": ["400001"]},
    )
    assert pins.status_code == 200, pins.text

    submitted = await client.post(
        f"/api/v1/vendors/{vendor_id}/products/submit",
        headers=vendor_headers,
        json={
            "name": name,
            "description": f"{name} description.",
            "category": "Dairy",
            "sku": sku,
            "mrp_inr": mrp,
            "net_weight": "1L",
            "brand": "MultiBrand",
            "image_urls": [
                "https://cdn.example.com/mv-1.jpg",
                "https://cdn.example.com/mv-2.jpg",
            ],
            "authenticity_attested": True,
            "city_ids": [city_id],
            "fulfilment_type": "SHIP_PHYSICAL",
        },
    )
    assert submitted.status_code == 201, submitted.text
    product_id = submitted.json()["product_id"]
    approve = await client.post(
        f"/api/v1/admin/products/{product_id}/approve",
        headers=op_headers,
    )
    assert approve.status_code == 200, approve.text

    catalog = await client.get("/api/v1/marketplace/catalog", params={"q": name})
    card = next(item for item in catalog.json()["results"] if item["product_id"] == product_id)
    return card["offering_id"]


async def _buyer_with_address(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    email: str,
) -> dict:
    buyer = await register_verify_login(client, session_factory, email)
    headers = {"Authorization": f"Bearer {buyer.token}"}
    tenant_id = str(buyer.tenant_id)
    address = await client.post(
        f"/api/v1/tenants/{tenant_id}/addresses",
        headers=headers,
        json={
            "label": "Home",
            "contact_name": "Multi Buyer",
            "line1": "12 Link Road",
            "city": "Mumbai",
            "state": "MH",
            "pincode": "400001",
            "phone": "+919800011122",
        },
    )
    assert address.status_code == 201, address.text
    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "address_id": address.json()["address_id"],
    }


async def _place_two_vendor_order(
    client: AsyncClient,
    *,
    buyer: dict,
    offering_a: str,
    offering_b: str,
) -> str:
    for offering_id in (offering_a, offering_b):
        cart = await client.post(
            f"/api/v1/tenants/{buyer['tenant_id']}/cart/lines",
            headers=buyer["headers"],
            json={"offering_id": offering_id, "quantity": 1},
        )
        assert cart.status_code == 200, cart.text
    placed = await client.post(
        f"/api/v1/tenants/{buyer['tenant_id']}/orders",
        headers=buyer["headers"],
        json={"address_id": buyer["address_id"], "payment_method": "upi"},
    )
    assert placed.status_code == 201, placed.text
    return placed.json()["order_id"]


@pytest.mark.asyncio
async def test_multi_vendor_fulfilment_rollup_and_refund(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add(PlatformConfigRow(key="product_content_review_required", value=True))
        await session.commit()

    op = await _operator(client, session_factory, "mv-op@example.com")
    vendor_a = await _verified_vendor(client, session_factory, "mv-vendor-a@example.com", op["headers"])
    vendor_b = await _verified_vendor(client, session_factory, "mv-vendor-b@example.com", op["headers"])

    offering_a = await _publish_physical(
        client,
        op_headers=op["headers"],
        vendor_id=vendor_a["vendor_id"],
        vendor_headers=vendor_a["headers"],
        name="Multi Vendor Milk A",
        sku="MV-A-1",
        mrp=50.0,
    )
    offering_b = await _publish_physical(
        client,
        op_headers=op["headers"],
        vendor_id=vendor_b["vendor_id"],
        vendor_headers=vendor_b["headers"],
        name="Multi Vendor Milk B",
        sku="MV-B-1",
        mrp=75.0,
    )

    buyer = await _buyer_with_address(client, session_factory, "mv-buyer@example.com")
    order_id = await _place_two_vendor_order(
        client, buyer=buyer, offering_a=offering_a, offering_b=offering_b
    )

    detail = await client.get(f"/api/v1/orders/{order_id}", headers=buyer["headers"])
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "placed"
    assert len(body["vendors"]) == 2
    assert {v["status"] for v in body["vendors"]} == {"placed"}
    assert body["address"] is not None
    assert len(body["timeline"]) >= 3

    confirm_a = await client.patch(
        f"/api/v1/vendors/{vendor_a['vendor_id']}/orders/{order_id}",
        headers=vendor_a["headers"],
        json={"status": "confirmed"},
    )
    assert confirm_a.status_code == 200, confirm_a.text

    cancel_b = await client.patch(
        f"/api/v1/vendors/{vendor_b['vendor_id']}/orders/{order_id}",
        headers=vendor_b["headers"],
        json={"status": "cancelled"},
    )
    assert cancel_b.status_code == 200, cancel_b.text

    after = await client.get(f"/api/v1/orders/{order_id}", headers=buyer["headers"])
    assert after.status_code == 200, after.text
    assert after.json()["status"] == "partial"
    slice_b = next(v for v in after.json()["vendors"] if v["vendor_id"] == vendor_b["vendor_id"])
    assert slice_b["status"] == "cancelled"
    assert slice_b["refund_status"] == "pending"
    assert slice_b["refund_amount"] == 75.0

    refunded = await client.post(
        f"/api/v1/vendors/{vendor_b['vendor_id']}/orders/{order_id}/refund-slice",
        headers=vendor_b["headers"],
    )
    assert refunded.status_code == 200, refunded.text
    assert refunded.json()["refund_status"] == "refunded"

    after_refund = await client.get(f"/api/v1/orders/{order_id}", headers=buyer["headers"])
    slice_b2 = next(
        v for v in after_refund.json()["vendors"] if v["vendor_id"] == vendor_b["vendor_id"]
    )
    assert slice_b2["refund_status"] == "refunded"


@pytest.mark.asyncio
async def test_multi_vendor_delivered_and_delayed_is_partial(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add(PlatformConfigRow(key="product_content_review_required", value=True))
        await session.commit()

    op = await _operator(client, session_factory, "mv2-op@example.com")
    vendor_a = await _verified_vendor(client, session_factory, "mv2-vendor-a@example.com", op["headers"])
    vendor_b = await _verified_vendor(client, session_factory, "mv2-vendor-b@example.com", op["headers"])

    offering_a = await _publish_physical(
        client,
        op_headers=op["headers"],
        vendor_id=vendor_a["vendor_id"],
        vendor_headers=vendor_a["headers"],
        name="Partial Path A",
        sku="MV2-A-1",
        mrp=40.0,
    )
    offering_b = await _publish_physical(
        client,
        op_headers=op["headers"],
        vendor_id=vendor_b["vendor_id"],
        vendor_headers=vendor_b["headers"],
        name="Partial Path B",
        sku="MV2-B-1",
        mrp=60.0,
    )

    buyer = await _buyer_with_address(client, session_factory, "mv2-buyer@example.com")
    order_id = await _place_two_vendor_order(
        client, buyer=buyer, offering_a=offering_a, offering_b=offering_b
    )

    for status in ("confirmed", "processing", "ready_to_ship"):
        moved = await client.patch(
            f"/api/v1/vendors/{vendor_a['vendor_id']}/orders/{order_id}",
            headers=vendor_a["headers"],
            json={"status": status},
        )
        assert moved.status_code == 200, moved.text
    shipped = await client.patch(
        f"/api/v1/vendors/{vendor_a['vendor_id']}/orders/{order_id}",
        headers=vendor_a["headers"],
        json={"status": "shipped", "courier": "Fast", "tracking_number": "TRK-A"},
    )
    assert shipped.status_code == 200, shipped.text
    delivered = await client.patch(
        f"/api/v1/vendors/{vendor_a['vendor_id']}/orders/{order_id}",
        headers=vendor_a["headers"],
        json={"status": "delivered"},
    )
    assert delivered.status_code == 200, delivered.text

    for status in ("confirmed", "processing", "delayed"):
        moved = await client.patch(
            f"/api/v1/vendors/{vendor_b['vendor_id']}/orders/{order_id}",
            headers=vendor_b["headers"],
            json={"status": status},
        )
        assert moved.status_code == 200, moved.text

    detail = await client.get(f"/api/v1/orders/{order_id}", headers=buyer["headers"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "partial"
    by_vendor = {v["vendor_id"]: v["status"] for v in detail.json()["vendors"]}
    assert by_vendor[vendor_a["vendor_id"]] == "delivered"
    assert by_vendor[vendor_b["vendor_id"]] == "delayed"


@pytest.mark.asyncio
async def test_buyer_cancel_only_while_all_placed(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add(PlatformConfigRow(key="product_content_review_required", value=True))
        await session.commit()

    op = await _operator(client, session_factory, "mv3-op@example.com")
    vendor_a = await _verified_vendor(client, session_factory, "mv3-vendor-a@example.com", op["headers"])
    vendor_b = await _verified_vendor(client, session_factory, "mv3-vendor-b@example.com", op["headers"])

    offering_a = await _publish_physical(
        client,
        op_headers=op["headers"],
        vendor_id=vendor_a["vendor_id"],
        vendor_headers=vendor_a["headers"],
        name="Cancel Path A",
        sku="MV3-A-1",
        mrp=30.0,
    )
    offering_b = await _publish_physical(
        client,
        op_headers=op["headers"],
        vendor_id=vendor_b["vendor_id"],
        vendor_headers=vendor_b["headers"],
        name="Cancel Path B",
        sku="MV3-B-1",
        mrp=35.0,
    )

    buyer = await _buyer_with_address(client, session_factory, "mv3-buyer@example.com")
    order_ok = await _place_two_vendor_order(
        client, buyer=buyer, offering_a=offering_a, offering_b=offering_b
    )
    cancelled = await client.post(
        f"/api/v1/tenants/{buyer['tenant_id']}/orders/{order_ok}/cancel",
        headers=buyer["headers"],
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert all(v["status"] == "cancelled" for v in cancelled.json()["vendors"])
    assert all(v["refund_status"] == "pending" for v in cancelled.json()["vendors"])

    order_blocked = await _place_two_vendor_order(
        client, buyer=buyer, offering_a=offering_a, offering_b=offering_b
    )
    confirmed = await client.patch(
        f"/api/v1/vendors/{vendor_a['vendor_id']}/orders/{order_blocked}",
        headers=vendor_a["headers"],
        json={"status": "confirmed"},
    )
    assert confirmed.status_code == 200, confirmed.text
    blocked = await client.post(
        f"/api/v1/tenants/{buyer['tenant_id']}/orders/{order_blocked}/cancel",
        headers=buyer["headers"],
    )
    assert blocked.status_code in (409, 422), blocked.text
