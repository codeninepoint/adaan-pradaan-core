from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.domain.security import utcnow
from marketplace.application.commerce_service import settlement_id_for
from marketplace.infrastructure.models import PayoutLedgerRow
from tests.integration.marketplace.test_platform_admin_governance import (
    _operator,
    _verified_vendor,
)


@pytest.mark.asyncio
async def test_vendor_payouts_summary_and_settlement_id(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "pay-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "pay-vendor@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

    now = utcnow()
    pending_id = uuid.uuid4()
    paid_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            PayoutLedgerRow(
                id=pending_id,
                vendor_id=uuid.UUID(vendor_id),
                period="Oct 1–7",
                gross=52430,
                platform_fee=3230,
                net=49200,
                status="pending",
                created_at=now - timedelta(days=2),
            )
        )
        session.add(
            PayoutLedgerRow(
                id=paid_id,
                vendor_id=uuid.UUID(vendor_id),
                period="Sep 24–30",
                gross=53020,
                platform_fee=3020,
                net=50000,
                status="paid",
                created_at=now - timedelta(days=5),
            )
        )
        await session.commit()

    resp = await client.get(f"/api/v1/vendors/{vendor_id}/payouts", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["currency"] == "INR"
    assert body["this_period"] is not None
    assert body["this_period"]["period"] == "Oct 1–7"
    assert body["this_period"]["settlement_id"] == settlement_id_for(pending_id)

    payouts = body["payouts"]
    assert len(payouts) == 2
    for row in payouts:
        assert re.fullmatch(r"SET-[0-9A-F]{6}", row["settlement_id"])

    by_period = {row["period"]: row for row in payouts}
    assert by_period["Oct 1–7"]["settlement_id"] == settlement_id_for(pending_id)
    assert by_period["Oct 1–7"]["net"] == 49200
    assert by_period["Sep 24–30"]["settlement_id"] == settlement_id_for(paid_id)
    assert by_period["Sep 24–30"]["status"] == "paid"

    summary = body["summary"]
    assert summary["earned_this_month"] == 52430 + 53020
    assert summary["commission_this_month"] == 3230 + 3020
    assert summary["total_settled"] == 50000
    assert summary["next_settlement"] == 49200
    assert summary["next_settlement_due_days"] == 5  # 7 - 2
    assert summary["commission_rate_pct"] == 10
