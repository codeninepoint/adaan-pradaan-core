"""Customer Order Hub.

Active/past orders, 30-minute return window, photo return form, vendor chat
(locked on return), and refund status — seeded from the Customer Order mock.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from marketplace.application.access import audit
from platform_ops.infrastructure.models import CustomerHubOrderRow, CustomerHubReturnRow
from shared.domain.exceptions import ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import TenantMembershipRow, TenantRow

CATEGORIES = (
    "wrong_item",
    "missing_item",
    "quality",
    "quantity",
    "foreign_object",
)

CATEGORY_LABELS = {
    "wrong_item": "Wrong item",
    "missing_item": "Missing item",
    "quality": "Quality issue",
    "quantity": "Short quantity",
    "foreign_object": "Foreign object",
}


def _d(value: str | float | int) -> Decimal:
    return Decimal(str(value))


ACTIVE_SEED = {
    "order_ref": "#4521",
    "vendor_name": "Idli Dosa Co.",
    "zone": "Airoli",
    "placed_label": "Placed 14:22",
    "status": "return_window",
    "total": _d("200"),
    "summary": "Masala Dosa, Filter Coffee, Medu Vada",
    "is_active": True,
    "window_seconds": 1114,
    "window_closes_label": "15:28",
    "timeline": [
        {
            "key": "placed",
            "title": "Order Placed",
            "detail": "14:22 · Payment ₹200 confirmed",
            "state": "done",
        },
        {
            "key": "preparing",
            "title": "Preparing",
            "detail": "14:30 · Vendor confirmed",
            "state": "done",
        },
        {
            "key": "out",
            "title": "Out for Delivery",
            "detail": "14:50 · On the way",
            "state": "done",
        },
        {
            "key": "delivered",
            "title": "Delivered — Return Window Open",
            "detail": "14:58 · 30-min window closes at 15:28",
            "state": "active",
        },
        {
            "key": "complete",
            "title": "Order Complete",
            "detail": "After return window closes",
            "state": "pending",
        },
    ],
    "bill_lines": [
        {"label": "Masala Dosa", "amount": 120.0},
        {"label": "Filter Coffee", "amount": 40.0},
        {"label": "Medu Vada", "amount": 40.0},
        {"label": "Total Paid", "amount": 200.0, "total": True},
    ],
    "chat": [
        {"kind": "system", "text": "14:22 · Order placed"},
        {"kind": "customer", "label": "You", "text": "Please add extra sambar if possible"},
        {
            "kind": "vendor",
            "label": "Idli Dosa Co.",
            "text": "Sure! Extra sambar noted ✓",
        },
        {"kind": "system", "text": "14:58 · Delivered"},
        {
            "kind": "customer",
            "label": "You",
            "text": "This is Idli not Masala Dosa! I ordered Masala Dosa",
        },
        {
            "kind": "vendor",
            "label": "Idli Dosa Co.",
            "text": "We sent Masala Dosa only ma'am",
        },
    ],
    "meta": {},
}

PAST_SEEDS: tuple[dict, ...] = (
    {
        "order_ref": "#4510",
        "vendor_name": "Idli Dosa Co.",
        "zone": "Airoli",
        "placed_label": "29 Oct",
        "status": "complete",
        "total": _d("160"),
        "summary": "Rava Idli × 2, Filter Coffee — delivered, no issues",
        "is_active": False,
        "window_seconds": None,
        "window_closes_label": "",
        "timeline": [],
        "bill_lines": [
            {"label": "Rava Idli × 2", "amount": 120.0},
            {"label": "Filter Coffee", "amount": 40.0},
            {"label": "Total Paid", "amount": 160.0, "total": True},
        ],
        "chat": [],
        "meta": {"badge": "complete"},
    },
    {
        "order_ref": "#4498",
        "vendor_name": "Idli Dosa Co.",
        "zone": "Airoli",
        "placed_label": "28 Oct",
        "status": "refunded",
        "total": _d("120"),
        "summary": "Masala Dosa — return accepted by vendor. ₹120 refunded to UPI.",
        "is_active": False,
        "window_seconds": None,
        "window_closes_label": "",
        "timeline": [],
        "bill_lines": [
            {"label": "Masala Dosa", "amount": 120.0},
            {"label": "Total Paid", "amount": 120.0, "total": True},
        ],
        "chat": [],
        "meta": {"badge": "refunded"},
    },
)


@dataclass(frozen=True, slots=True)
class OrderView:
    id: str
    order_ref: str
    vendor_name: str
    zone: str
    placed_label: str
    status: str
    total: float
    summary: str
    is_active: bool
    window_seconds: int | None
    window_closes_label: str
    timeline: list = field(default_factory=list)
    bill_lines: list = field(default_factory=list)
    chat: list = field(default_factory=list)
    chat_locked: bool = False
    return_id: str | None = None
    return_status: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReturnView:
    id: str
    order_id: str
    order_ref: str
    category: str
    category_label: str
    description: str
    photo_name: str
    amount_at_stake: float
    status: str
    refund_amount: float | None
    refund_method: str | None
    refund_reference: str | None
    expected_by: str | None
    vendor_name: str


class CustomerOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def hub(self, *, tenant_id: UUID, caller_user_id: UUID) -> dict:
        await self._require_member(tenant_id, caller_user_id)
        await self._ensure_seeded(tenant_id)
        rows = (
            (
                await self._session.execute(
                    select(CustomerHubOrderRow)
                    .where(CustomerHubOrderRow.tenant_id == tenant_id)
                    .order_by(CustomerHubOrderRow.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        returns_by_order = await self._returns_by_order(tenant_id)
        active = [
            asdict(self._order_view(row, returns_by_order.get(row.id)))
            for row in rows
            if row.is_active
        ]
        past = [
            asdict(self._order_view(row, returns_by_order.get(row.id)))
            for row in rows
            if not row.is_active
        ]
        return {
            "customer_name": "Priya S.",
            "active": active,
            "past": past,
            "categories": [
                {"key": key, "label": CATEGORY_LABELS[key]} for key in CATEGORIES
            ],
        }

    async def get_order(
        self, *, tenant_id: UUID, caller_user_id: UUID, order_id: UUID
    ) -> dict:
        await self._require_member(tenant_id, caller_user_id)
        await self._ensure_seeded(tenant_id)
        row = await self._get_order(tenant_id, order_id)
        ret = await self._latest_return(tenant_id, order_id)
        return asdict(self._order_view(row, ret))

    async def submit_return(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        order_id: UUID,
        category: str,
        description: str,
        photo_name: str,
    ) -> dict:
        await self._require_member(tenant_id, caller_user_id)
        await self._ensure_seeded(tenant_id)
        row = await self._get_order(tenant_id, order_id)
        if not row.is_active or row.status not in {"return_window"}:
            if row.status == "window_closed":
                raise ValidationError("return window has closed")
            raise ValidationError("return cannot be raised for this order")
        if (row.window_seconds or 0) <= 0:
            row.status = "window_closed"
            await self._session.commit()
            raise ValidationError("return window has closed")

        category_key = category.strip().lower()
        if category_key not in CATEGORIES:
            raise ValidationError("invalid return category")
        desc = description.strip()
        if len(desc) < 20:
            raise ValidationError("description must be at least 20 characters")
        photo = photo_name.strip()
        if not photo:
            raise ValidationError("photo is required")

        existing = await self._latest_return(tenant_id, order_id)
        if existing is not None and existing.status in {"submitted", "approved"}:
            raise ValidationError("return already submitted for this order")

        ret = CustomerHubReturnRow(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            order_id=row.id,
            order_ref=row.order_ref,
            category=category_key,
            description=desc,
            photo_name=photo,
            amount_at_stake=row.total,
            status="submitted",
            vendor_name=row.vendor_name,
        )
        self._session.add(ret)
        row.status = "return_submitted"
        chat = list(row.chat or [])
        chat.append(
            {
                "kind": "alert",
                "text": "Return raised — chat locked for evidence",
            }
        )
        row.chat = chat
        row.meta = {**dict(row.meta or {}), "return_id": str(ret.id)}
        await audit(
            self._session,
            action="customer_hub.return_submitted",
            actor_user_id=caller_user_id,
            tenant_id=tenant_id,
            payload={
                "order_id": str(row.id),
                "order_ref": row.order_ref,
                "category": category_key,
            },
        )
        await self._session.commit()
        await self._session.refresh(ret)
        return {
            "message": "Return request submitted",
            "item": asdict(self._return_view(ret)),
            "order": asdict(self._order_view(row, ret)),
        }

    async def simulate_vendor_accept(
        self, *, tenant_id: UUID, caller_user_id: UUID, order_id: UUID
    ) -> dict:
        """Demo helper — vendor accepts the open return (matches mock Simulate Accept)."""
        await self._require_member(tenant_id, caller_user_id)
        await self._ensure_seeded(tenant_id)
        row = await self._get_order(tenant_id, order_id)
        ret = await self._latest_return(tenant_id, order_id)
        if ret is None or ret.status != "submitted":
            raise ValidationError("no submitted return to accept")
        now = utcnow()
        ret.status = "approved"
        ret.refund_amount = ret.amount_at_stake
        ret.refund_method = "UPI / original method"
        ret.refund_reference = f"RFD{now.strftime('%y%m%d%H%M%S')}"
        ret.expected_by = "2–5 business days"
        ret.resolved_at = now
        row.status = "refunded"
        row.is_active = False
        row.summary = (
            f"{row.summary.split('—')[0].strip()} — return accepted by vendor. "
            f"₹{float(ret.refund_amount):.0f} refunded to UPI."
            if "—" not in row.summary
            else (
                f"Return accepted by {row.vendor_name}. "
                f"₹{float(ret.refund_amount):.0f} refunded to UPI."
            )
        )
        row.meta = {**dict(row.meta or {}), "badge": "refunded"}
        await audit(
            self._session,
            action="customer_hub.return_approved",
            actor_user_id=caller_user_id,
            tenant_id=tenant_id,
            payload={"order_id": str(row.id), "return_id": str(ret.id)},
        )
        await self._session.commit()
        await self._session.refresh(ret)
        await self._session.refresh(row)
        return {
            "message": "Refund approved",
            "item": asdict(self._return_view(ret)),
            "order": asdict(self._order_view(row, ret)),
        }

    async def close_window(
        self, *, tenant_id: UUID, caller_user_id: UUID, order_id: UUID
    ) -> dict:
        await self._require_member(tenant_id, caller_user_id)
        await self._ensure_seeded(tenant_id)
        row = await self._get_order(tenant_id, order_id)
        if row.status == "return_window":
            row.status = "window_closed"
            row.window_seconds = 0
            row.is_active = False
            row.meta = {**dict(row.meta or {}), "badge": "complete"}
            await self._session.commit()
            await self._session.refresh(row)
        return asdict(self._order_view(row, await self._latest_return(tenant_id, order_id)))

    async def chat(
        self, *, tenant_id: UUID, caller_user_id: UUID, order_id: UUID | None = None
    ) -> dict:
        await self._require_member(tenant_id, caller_user_id)
        await self._ensure_seeded(tenant_id)
        if order_id is None:
            row = (
                await self._session.execute(
                    select(CustomerHubOrderRow)
                    .where(
                        CustomerHubOrderRow.tenant_id == tenant_id,
                        CustomerHubOrderRow.is_active.is_(True),
                    )
                    .order_by(CustomerHubOrderRow.created_at.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                row = (
                    await self._session.execute(
                        select(CustomerHubOrderRow)
                        .where(CustomerHubOrderRow.tenant_id == tenant_id)
                        .order_by(CustomerHubOrderRow.created_at.asc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
        else:
            row = await self._get_order(tenant_id, order_id)
        if row is None:
            return {
                "info": "Messages go through AdanPradan. Your number is never shared.",
                "threads": [],
            }
        ret = await self._latest_return(tenant_id, row.id)
        locked = ret is not None and ret.status in {"submitted", "approved"}
        return {
            "info": "Messages go through AdanPradan. Your number is never shared.",
            "threads": [
                {
                    "order_id": str(row.id),
                    "order_ref": row.order_ref,
                    "vendor_name": row.vendor_name,
                    "online": True,
                    "locked": locked,
                    "lock_label": "Chat locked during return review" if locked else None,
                    "messages": list(row.chat or []),
                }
            ],
        }

    async def payments(self, *, tenant_id: UUID, caller_user_id: UUID) -> dict:
        await self._require_member(tenant_id, caller_user_id)
        await self._ensure_seeded(tenant_id)
        rows = (
            (
                await self._session.execute(
                    select(CustomerHubOrderRow)
                    .where(CustomerHubOrderRow.tenant_id == tenant_id)
                    .order_by(CustomerHubOrderRow.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        returns = (
            (
                await self._session.execute(
                    select(CustomerHubReturnRow).where(
                        CustomerHubReturnRow.tenant_id == tenant_id
                    )
                )
            )
            .scalars()
            .all()
        )
        paid = sum(float(r.total or 0) for r in rows)
        refunded = sum(
            float(r.refund_amount or 0) for r in returns if r.status == "approved"
        )
        return {
            "summary": {
                "orders_paid": paid,
                "refunds": refunded,
                "net": paid - refunded,
            },
            "items": [
                {
                    "order_ref": r.order_ref,
                    "label": r.placed_label,
                    "amount": float(r.total or 0),
                    "status": r.status,
                    "vendor_name": r.vendor_name,
                }
                for r in rows
            ],
        }

    async def _ensure_seeded(self, tenant_id: UUID) -> None:
        count = (
            await self._session.execute(
                select(func.count())
                .select_from(CustomerHubOrderRow)
                .where(CustomerHubOrderRow.tenant_id == tenant_id)
            )
        ).scalar_one()
        if count > 0:
            return
        for seed in (ACTIVE_SEED, *PAST_SEEDS):
            self._session.add(
                CustomerHubOrderRow(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    order_ref=seed["order_ref"],
                    vendor_name=seed["vendor_name"],
                    zone=seed["zone"],
                    placed_label=seed["placed_label"],
                    status=seed["status"],
                    total=seed["total"],
                    summary=seed["summary"],
                    is_active=seed["is_active"],
                    window_seconds=seed["window_seconds"],
                    window_closes_label=seed["window_closes_label"],
                    timeline=list(seed["timeline"]),
                    bill_lines=list(seed["bill_lines"]),
                    chat=list(seed["chat"]),
                    meta=dict(seed["meta"]),
                )
            )
        await self._session.commit()

    async def _require_member(self, tenant_id: UUID, user_id: UUID) -> None:
        tenant = await self._session.get(TenantRow, tenant_id)
        if tenant is None:
            raise NotFoundError("tenant not found")
        membership = (
            await self._session.execute(
                select(TenantMembershipRow.id).where(
                    TenantMembershipRow.tenant_id == tenant_id,
                    TenantMembershipRow.user_id == user_id,
                    TenantMembershipRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ForbiddenError("not a member of the tenant")

    async def _get_order(self, tenant_id: UUID, order_id: UUID) -> CustomerHubOrderRow:
        row = await self._session.get(CustomerHubOrderRow, order_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError("order not found")
        return row

    async def _latest_return(
        self, tenant_id: UUID, order_id: UUID
    ) -> CustomerHubReturnRow | None:
        return (
            await self._session.execute(
                select(CustomerHubReturnRow)
                .where(
                    CustomerHubReturnRow.tenant_id == tenant_id,
                    CustomerHubReturnRow.order_id == order_id,
                )
                .order_by(CustomerHubReturnRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _returns_by_order(
        self, tenant_id: UUID
    ) -> dict[UUID, CustomerHubReturnRow]:
        rows = (
            (
                await self._session.execute(
                    select(CustomerHubReturnRow).where(
                        CustomerHubReturnRow.tenant_id == tenant_id
                    )
                )
            )
            .scalars()
            .all()
        )
        latest: dict[UUID, CustomerHubReturnRow] = {}
        for row in rows:
            current = latest.get(row.order_id)
            if current is None or row.created_at >= current.created_at:
                latest[row.order_id] = row
        return latest

    def _order_view(
        self, row: CustomerHubOrderRow, ret: CustomerHubReturnRow | None
    ) -> OrderView:
        locked = ret is not None and ret.status in {"submitted", "approved"}
        return OrderView(
            id=str(row.id),
            order_ref=row.order_ref,
            vendor_name=row.vendor_name,
            zone=row.zone,
            placed_label=row.placed_label,
            status=row.status,
            total=float(row.total or 0),
            summary=row.summary,
            is_active=row.is_active,
            window_seconds=row.window_seconds,
            window_closes_label=row.window_closes_label,
            timeline=list(row.timeline or []),
            bill_lines=list(row.bill_lines or []),
            chat=list(row.chat or []),
            chat_locked=locked,
            return_id=str(ret.id) if ret else None,
            return_status=ret.status if ret else None,
            meta=dict(row.meta or {}),
        )

    @staticmethod
    def _return_view(row: CustomerHubReturnRow) -> ReturnView:
        return ReturnView(
            id=str(row.id),
            order_id=str(row.order_id),
            order_ref=row.order_ref,
            category=row.category,
            category_label=CATEGORY_LABELS.get(row.category, row.category),
            description=row.description,
            photo_name=row.photo_name,
            amount_at_stake=float(row.amount_at_stake or 0),
            status=row.status,
            refund_amount=float(row.refund_amount) if row.refund_amount is not None else None,
            refund_method=row.refund_method,
            refund_reference=row.refund_reference,
            expected_by=row.expected_by,
            vendor_name=row.vendor_name,
        )
