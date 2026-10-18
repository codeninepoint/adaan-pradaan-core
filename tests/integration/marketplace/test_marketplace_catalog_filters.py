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


@pytest.mark.asyncio
async def test_catalog_filters_facets_ratings_and_public_reviews(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add(PlatformConfigRow(key="product_content_review_required", value=True))
        await session.commit()

    op = await _operator(client, session_factory, "mkt-filt-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "mkt-filt-vendor@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

    city = await client.post(
        f"/api/v1/vendors/{vendor_id}/service-cities",
        headers=headers,
        json={"city_name": "Mumbai"},
    )
    assert city.status_code == 201, city.text
    city_id = city.json()["city_id"]
    warehouse_id = city.json()["warehouse_id"]
    pins = await client.put(
        f"/api/v1/vendors/{vendor_id}/service-cities/{city_id}/pincodes",
        headers=headers,
        json={"pincodes": ["400001"]},
    )
    assert pins.status_code == 200, pins.text

    submitted = await client.post(
        f"/api/v1/vendors/{vendor_id}/products/submit",
        headers=headers,
        json={
            "name": "Filter Test Yogurt",
            "description": "Creamy Greek yogurt.",
            "category": "Dairy",
            "sku": "FLT-YOG-1",
            "mrp_inr": 120.0,
            "net_weight": "400g",
            "brand": "FilterCo",
            "image_urls": [
                "https://cdn.example.com/yog-1.jpg",
                "https://cdn.example.com/yog-2.jpg",
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
        headers=op["headers"],
    )
    assert approve.status_code == 200, approve.text

    stock = await client.post(
        f"/api/v1/vendors/{vendor_id}/inventory",
        headers=headers,
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "sku": "FLT-YOG-1",
            "available": 20,
            "reorder_threshold": 5,
        },
    )
    assert stock.status_code == 201, stock.text

    catalog = await client.get(
        "/api/v1/marketplace/catalog",
        params={"q": "Filter Test Yogurt", "fulfilment": "physical"},
    )
    assert catalog.status_code == 200, catalog.text
    body = catalog.json()
    assert body["facets"]["vendors"]
    assert any(v["vendor_id"] == vendor_id for v in body["facets"]["vendors"])
    row = next(item for item in body["results"] if item["product_id"] == product_id)
    assert row["in_stock"] is True
    assert row["avg_rating"] == 0.0
    assert row["review_count"] == 0

    by_vendor = await client.get(
        "/api/v1/marketplace/catalog",
        params={"vendor_ids": vendor_id, "fulfilment": "physical"},
    )
    assert by_vendor.status_code == 200
    assert any(item["product_id"] == product_id for item in by_vendor.json()["results"])

    pin_ok = await client.get(
        "/api/v1/marketplace/catalog",
        params={"q": "Filter Test Yogurt", "pincode": "400001"},
    )
    assert pin_ok.status_code == 200
    assert any(item["product_id"] == product_id for item in pin_ok.json()["results"])

    pin_miss = await client.get(
        "/api/v1/marketplace/catalog",
        params={"q": "Filter Test Yogurt", "pincode": "999999"},
    )
    assert pin_miss.status_code == 200
    assert not any(item["product_id"] == product_id for item in pin_miss.json()["results"])

    in_stock = await client.get(
        "/api/v1/marketplace/catalog",
        params={"q": "Filter Test Yogurt", "in_stock": "true"},
    )
    assert in_stock.status_code == 200
    assert any(item["product_id"] == product_id for item in in_stock.json()["results"])

    digital_only = await client.get(
        "/api/v1/marketplace/catalog",
        params={"q": "Filter Test Yogurt", "fulfilment": "digital"},
    )
    assert digital_only.status_code == 200
    assert not any(item["product_id"] == product_id for item in digital_only.json()["results"])

    # Place order + review → public reviews + rating on card
    catalog_card = await client.get("/api/v1/marketplace/catalog", params={"q": "Filter Test Yogurt"})
    card = next(item for item in catalog_card.json()["results"] if item["product_id"] == product_id)
    offering_id = card["offering_id"]

    buyer = await register_verify_login(client, session_factory, "mkt-filt-buyer@example.com")
    buyer_headers = {"Authorization": f"Bearer {buyer.token}"}
    buyer_tenant = str(buyer.tenant_id)

    cart = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/cart/lines",
        headers=buyer_headers,
        json={"offering_id": offering_id, "quantity": 1},
    )
    assert cart.status_code == 200, cart.text
    address = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/addresses",
        headers=buyer_headers,
        json={
            "label": "Home",
            "contact_name": "Rhea K.",
            "line1": "1 Bandra",
            "city": "Mumbai",
            "state": "MH",
            "pincode": "400001",
            "phone": "+919800012345",
        },
    )
    assert address.status_code == 201, address.text
    placed = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/orders",
        headers=buyer_headers,
        json={"address_id": address.json()["address_id"], "payment_method": "upi"},
    )
    assert placed.status_code == 201, placed.text
    order_id = placed.json()["order_id"]
    detail = await client.get(f"/api/v1/orders/{order_id}", headers=buyer_headers)
    assert detail.status_code == 200
    line_id = detail.json()["lines"][0]["line_id"]

    created = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/reviews",
        headers=buyer_headers,
        json={
            "order_id": order_id,
            "line_id": line_id,
            "rating": 5,
            "comment": "Fresh and tasty.",
        },
    )
    assert created.status_code == 201, created.text

    public = await client.get(f"/api/v1/marketplace/products/{product_id}/reviews")
    assert public.status_code == 200, public.text
    assert public.json()["review_count"] == 1
    assert public.json()["avg_rating"] == 5.0
    assert public.json()["reviews"][0]["customer_name"] == "Rhea K."

    rated = await client.get("/api/v1/marketplace/catalog", params={"q": "Filter Test Yogurt"})
    rated_row = next(item for item in rated.json()["results"] if item["product_id"] == product_id)
    assert rated_row["avg_rating"] == 5.0
    assert rated_row["review_count"] == 1
