"""Vendor Settlement Portal.

Live earnings, return alerts (accept/contest), today's orders, settlement
history, customer chat evidence, and IMPS bank account — seeded from the
Vendor Settlement mock for local demos.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from marketplace.application.access import audit, require_vendor_owner
from platform_ops.infrastructure.models import (
    SettlementReturnCaseRow,
    VendorSettlementBankRow,
    VendorSettlementHistoryRow,
    VendorSettlementOrderRow,
    VendorSettlementReturnRow,
)
from shared.domain.exceptions import NotFoundError, ValidationError

CALCULATION_EXAMPLE = {
    "title": "How Your Settlement Is Calculated — Example Order ₹200",
    "lines": [
        {"label": "Customer paid", "amount": 200.0, "tone": "neutral"},
        {"label": "Platform commission (10%)", "amount": -20.0, "tone": "deduction"},
        {"label": "GST on commission (18%)", "amount": -3.6, "tone": "deduction"},
        {"label": "Payment gateway fee (2%)", "amount": -4.0, "tone": "deduction"},
        {"label": "TDS @ 1% (Sec 194-O)", "amount": -2.0, "tone": "deduction"},
        {"label": "You receive", "amount": 170.4, "tone": "net"},
    ],
}

HISTORY_SUMMARY = {
    "period": "Oct 2026",
    "gross": 42100.0,
    "total_deductions": 6234.0,
    "net_received": 35866.0,
    "tds_deducted": 421.0,
    "refund_adjustments": 860.0,
    "form_16a_next": "Jan 2027",
}


def _d(value: str | float | int) -> Decimal:
    return Decimal(str(value))


ORDER_SEEDS: tuple[dict, ...] = (
    {
        "order_ref": "#4524",
        "order_time": "15:28",
        "items": "Rava Idli × 2, Coffee",
        "gross": _d("200"),
        "net": _d("170.40"),
        "status": "window_open",
        "window_label": "18:32 left",
        "settlement_label": "Window open",
        "return_label": "",
        "in_tracker": True,
        "in_today": True,
    },
    {
        "order_ref": "#4523",
        "order_time": "15:10",
        "items": "Masala Dosa, Sambar",
        "gross": _d("160"),
        "net": _d("136.32"),
        "status": "window_open",
        "window_label": "24:11 left",
        "settlement_label": "Window open",
        "return_label": "",
        "in_tracker": True,
        "in_today": False,
    },
    {
        "order_ref": "#4521",
        "order_time": "14:22",
        "items": "Masala Dosa, Coffee, Vada",
        "gross": _d("200"),
        "net": _d("170.40"),
        "status": "on_hold",
        "window_label": "Pending decision",
        "settlement_label": "On Hold",
        "return_label": "Contested",
        "in_tracker": True,
        "in_today": True,
    },
    {
        "order_ref": "#4520",
        "order_time": "15:10",
        "items": "Vada × 3, Coffee",
        "gross": _d("200"),
        "net": _d("170.40"),
        "status": "settled",
        "window_label": "15:10 — done",
        "settlement_label": "Settled",
        "return_label": "",
        "in_tracker": True,
        "in_today": False,
    },
    {
        "order_ref": "#4518",
        "order_time": "13:50",
        "items": "Idli × 3, Vada",
        "gross": _d("200"),
        "net": _d("0"),
        "status": "refunded",
        "window_label": "",
        "settlement_label": "₹0 — Refund",
        "return_label": "Vendor accepted",
        "in_tracker": False,
        "in_today": True,
    },
    {
        "order_ref": "#4512",
        "order_time": "13:40",
        "items": "Rava Idli, Coffee",
        "gross": _d("160"),
        "net": _d("136.32"),
        "status": "settled",
        "window_label": "",
        "settlement_label": "₹136.32 settled",
        "return_label": "",
        "in_tracker": False,
        "in_today": True,
    },
    {
        "order_ref": "#4508",
        "order_time": "12:55",
        "items": "Dosa, Sambar, Coffee",
        "gross": _d("240"),
        "net": _d("204.48"),
        "status": "settled",
        "window_label": "",
        "settlement_label": "₹204.48 settled",
        "return_label": "",
        "in_tracker": False,
        "in_today": True,
    },
)

RETURN_SEED = {
    "order_ref": "#4521",
    "customer_name": "Priya S.",
    "complaint": (
        "Received plain Idli instead of Masala Dosa. Completely wrong item delivered."
    ),
    "reason_code": "wrong_item",
    "refund_requested": _d("200"),
    "amount_on_hold": _d("170.40"),
    "order_items": "Masala Dosa ₹120 · Filter Coffee ₹40 · Medu Vada ₹40",
    "timeline": "Placed 14:22 · Delivered 14:58 · Return raised 15:04",
    "deadline_seconds": 272,
    "status": "open",
    "contest_reason": "",
    "chat": [
        {"kind": "system", "text": "14:22 · Order #4521 placed"},
        {"kind": "customer", "label": "Priya S.", "text": "Please add extra sambar if possible"},
        {
            "kind": "vendor",
            "label": "You (Idli Dosa Co.)",
            "text": "Sure! Extra sambar noted ✓",
        },
        {"kind": "system", "text": "14:58 · Delivered"},
        {
            "kind": "customer",
            "label": "Priya S.",
            "text": "This is Idli not Masala Dosa! I ordered Masala Dosa",
        },
        {"kind": "vendor", "label": "You", "text": "We sent Masala Dosa only, ma'am"},
        {
            "kind": "alert",
            "text": "15:04 · Customer raised return — chat locked for evidence",
        },
    ],
    "meta": {},
}

HISTORY_SEEDS: tuple[dict, ...] = (
    {
        "settle_date": "30 Oct",
        "orders": 17,
        "gross": _d("3200"),
        "deductions": _d("474"),
        "refund_adj": _d("340"),
        "net": _d("2386"),
        "utr": "In progress",
    },
    {
        "settle_date": "29 Oct",
        "orders": 24,
        "gross": _d("4800"),
        "deductions": _d("710"),
        "refund_adj": _d("0"),
        "net": _d("4090"),
        "utr": "RAZR2610291622",
    },
    {
        "settle_date": "28 Oct",
        "orders": 19,
        "gross": _d("3800"),
        "deductions": _d("562"),
        "refund_adj": _d("200"),
        "net": _d("3038"),
        "utr": "RAZR2610281847",
    },
    {
        "settle_date": "27 Oct",
        "orders": 31,
        "gross": _d("6200"),
        "deductions": _d("918"),
        "refund_adj": _d("0"),
        "net": _d("5282"),
        "utr": "RAZR2610271209",
    },
)

BANK_SEED = {
    "bank_name": "State Bank of India",
    "account_mask": "•••• •••• •••• 4521",
    "ifsc": "SBIN0001234",
    "branch": "Airoli Branch",
    "verified": True,
}


@dataclass(frozen=True, slots=True)
class OrderView:
    id: str
    order_ref: str
    order_time: str
    items: str
    gross: float
    net: float
    status: str
    window_label: str
    settlement_label: str
    return_label: str
    in_tracker: bool
    in_today: bool


@dataclass(frozen=True, slots=True)
class ReturnView:
    id: str
    order_ref: str
    customer_name: str
    complaint: str
    reason_code: str
    refund_requested: float
    amount_on_hold: float
    order_items: str
    timeline: str
    deadline_seconds: int | None
    status: str
    contest_reason: str
    chat: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HistoryView:
    id: str
    settle_date: str
    orders: int
    gross: float
    deductions: float
    refund_adj: float
    net: float
    utr: str | None


class VendorSettlementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def earnings(self, *, vendor_id: UUID, caller_user_id: UUID) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded(vendor_id)
        open_returns = await self._open_return_count(vendor_id)
        hold_amount = await self._open_hold_amount(vendor_id)
        tracker = await self._orders(vendor_id, tracker_only=True)
        on_hold_sub = (
            f"{open_returns} return{'s' if open_returns != 1 else ''} under review"
            if open_returns
            else "No returns on hold"
        )
        return {
            "as_of": "30 Oct 2026",
            "zone": "Airoli",
            "live": True,
            "open_return_alerts": open_returns,
            "kpis": {
                "settled_today": 2385.0,
                "settled_today_sub": "14 orders · via IMPS",
                "pending_window": 510.0,
                "pending_window_sub": "3 orders out for delivery",
                "on_hold": hold_amount if open_returns else 0.0,
                "on_hold_sub": on_hold_sub,
                "next_transfer_minutes": 12,
                "next_transfer_sub": "Hourly batch · 16:00",
            },
            "tracker": [asdict(item) for item in tracker],
            "calculation": CALCULATION_EXAMPLE,
        }

    async def returns(self, *, vendor_id: UUID, caller_user_id: UUID) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded(vendor_id)
        rows = (
            (
                await self._session.execute(
                    select(VendorSettlementReturnRow)
                    .where(VendorSettlementReturnRow.vendor_id == vendor_id)
                    .order_by(VendorSettlementReturnRow.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return {
            "open_count": sum(1 for row in rows if row.status == "open"),
            "items": [asdict(self._return_view(row)) for row in rows],
        }

    async def respond_return(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        return_id: UUID,
        action: str,
        reason: str | None = None,
    ) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded(vendor_id)
        row = await self._session.get(VendorSettlementReturnRow, return_id)
        if row is None or row.vendor_id != vendor_id:
            raise NotFoundError("return alert not found")
        if row.status != "open":
            raise ValidationError("return alert is already resolved")
        action_key = action.strip().lower()
        if action_key not in {"accept", "contest", "timeout"}:
            raise ValidationError("action must be accept, contest, or timeout")

        now = utcnow()
        toast = ""
        if action_key == "accept":
            row.status = "accepted"
            row.resolved_at = now
            message = (
                "✅ Accepted — customer will be refunded. Settlement adjusted. "
                "Thank you for resolving quickly."
            )
            toast = f"Return accepted — {self._inr(row.amount_on_hold)} adjusted from settlement"
            await self._mark_order_refunded(vendor_id, row.order_ref)
        elif action_key == "timeout":
            row.status = "timed_out"
            row.resolved_at = now
            message = (
                f"⏰ Time expired — return auto-accepted. "
                f"{self._inr(row.amount_on_hold)} adjusted. Customer refunded."
            )
            toast = message
            await self._mark_order_refunded(vendor_id, row.order_ref)
        else:
            contest_reason = (reason or "").strip()
            if not contest_reason:
                raise ValidationError("contest reason is required")
            row.status = "contested"
            row.contest_reason = contest_reason
            row.resolved_at = now
            message = (
                "⏳ Escalated to platform admin. Decision expected within 5 minutes. "
                "You will be notified."
            )
            toast = "Contest submitted — admin reviewing now"
            await self._mark_order_contested(vendor_id, row.order_ref)
            await self._escalate_to_admin(row)

        row.meta = {
            **dict(row.meta or {}),
            "action": action_key,
            "responded_by": str(caller_user_id),
            "toast": toast,
        }
        await audit(
            self._session,
            action="vendor_settlement.return_response",
            actor_user_id=caller_user_id,
            payload={
                "vendor_id": str(vendor_id),
                "return_id": str(row.id),
                "order_ref": row.order_ref,
                "action": action_key,
            },
        )
        await self._session.commit()
        await self._session.refresh(row)
        return {
            "message": message,
            "toast": toast,
            "item": asdict(self._return_view(row)),
        }

    async def orders(self, *, vendor_id: UUID, caller_user_id: UUID) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded(vendor_id)
        items = await self._orders(vendor_id, today_only=True)
        return {
            "total": 17,
            "items": [asdict(item) for item in items],
        }

    async def history(self, *, vendor_id: UUID, caller_user_id: UUID) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded(vendor_id)
        rows = (
            (
                await self._session.execute(
                    select(VendorSettlementHistoryRow)
                    .where(VendorSettlementHistoryRow.vendor_id == vendor_id)
                    .order_by(VendorSettlementHistoryRow.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return {
            "summary": dict(HISTORY_SUMMARY),
            "items": [asdict(self._history_view(row)) for row in rows],
        }

    async def chat(self, *, vendor_id: UUID, caller_user_id: UUID) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded(vendor_id)
        row = (
            await self._session.execute(
                select(VendorSettlementReturnRow)
                .where(VendorSettlementReturnRow.vendor_id == vendor_id)
                .order_by(VendorSettlementReturnRow.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return {
                "info": (
                    "All customer messages are through this platform chat only. "
                    "Sharing personal contact details is a policy violation."
                ),
                "threads": [],
            }
        locked = row.status in {"open", "contested"}
        return {
            "info": (
                "All customer messages are through this platform chat only. "
                "Sharing personal contact details is a policy violation."
            ),
            "threads": [
                {
                    "id": str(row.id),
                    "customer_name": row.customer_name,
                    "order_ref": row.order_ref,
                    "locked": locked,
                    "lock_label": "Chat locked — return open" if locked else "Chat unlocked",
                    "messages": list(row.chat or []),
                }
            ],
        }

    async def bank(self, *, vendor_id: UUID, caller_user_id: UUID) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded(vendor_id)
        row = (
            await self._session.execute(
                select(VendorSettlementBankRow).where(
                    VendorSettlementBankRow.vendor_id == vendor_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("bank account not found")
        return {
            "bank_name": row.bank_name,
            "account_mask": row.account_mask,
            "ifsc": row.ifsc,
            "branch": row.branch,
            "verified": row.verified,
            "note": (
                "Settlement transfers via IMPS — instant, 24×7. Each hourly batch creates "
                "one transfer. Average credit time: under 30 seconds after batch fires."
            ),
        }

    async def update_bank(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        bank_name: str,
        account_number: str,
        ifsc: str,
        branch: str | None = None,
    ) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded(vendor_id)
        name = bank_name.strip()
        number = account_number.strip().replace(" ", "")
        ifsc_code = ifsc.strip().upper()
        if not name or len(number) < 4 or len(ifsc_code) < 4:
            raise ValidationError("bank_name, account_number, and ifsc are required")
        row = (
            await self._session.execute(
                select(VendorSettlementBankRow).where(
                    VendorSettlementBankRow.vendor_id == vendor_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = VendorSettlementBankRow(id=uuid.uuid4(), vendor_id=vendor_id)
            self._session.add(row)
        row.bank_name = name
        row.account_mask = f"•••• •••• •••• {number[-4:]}"
        row.ifsc = ifsc_code
        if branch is not None:
            row.branch = branch.strip()
        row.verified = False
        row.updated_at = utcnow()
        await audit(
            self._session,
            action="vendor_settlement.bank_updated",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "ifsc": row.ifsc},
        )
        await self._session.commit()
        await self._session.refresh(row)
        return {
            "message": "Bank account update submitted for verification.",
            "bank_name": row.bank_name,
            "account_mask": row.account_mask,
            "ifsc": row.ifsc,
            "branch": row.branch,
            "verified": row.verified,
            "note": (
                "Settlement transfers via IMPS — instant, 24×7. Each hourly batch creates "
                "one transfer. Average credit time: under 30 seconds after batch fires."
            ),
        }

    async def _orders(
        self,
        vendor_id: UUID,
        *,
        tracker_only: bool = False,
        today_only: bool = False,
    ) -> list[OrderView]:
        stmt = select(VendorSettlementOrderRow).where(
            VendorSettlementOrderRow.vendor_id == vendor_id
        )
        if tracker_only:
            stmt = stmt.where(VendorSettlementOrderRow.in_tracker.is_(True))
        if today_only:
            stmt = stmt.where(VendorSettlementOrderRow.in_today.is_(True))
        rows = (
            (await self._session.execute(stmt.order_by(VendorSettlementOrderRow.order_time.desc())))
            .scalars()
            .all()
        )
        return [self._order_view(row) for row in rows]

    async def _open_return_count(self, vendor_id: UUID) -> int:
        return int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(VendorSettlementReturnRow)
                    .where(
                        VendorSettlementReturnRow.vendor_id == vendor_id,
                        VendorSettlementReturnRow.status == "open",
                    )
                )
            ).scalar_one()
        )

    async def _open_hold_amount(self, vendor_id: UUID) -> float:
        total = (
            await self._session.execute(
                select(func.coalesce(func.sum(VendorSettlementReturnRow.amount_on_hold), 0)).where(
                    VendorSettlementReturnRow.vendor_id == vendor_id,
                    VendorSettlementReturnRow.status == "open",
                )
            )
        ).scalar_one()
        return float(total or 0)

    async def _escalate_to_admin(self, row: VendorSettlementReturnRow) -> None:
        """Mirror a vendor contest into the platform admin return queue."""
        existing = (
            await self._session.execute(
                select(SettlementReturnCaseRow).where(
                    SettlementReturnCaseRow.order_ref == row.order_ref,
                    SettlementReturnCaseRow.case_type == "contested",
                    SettlementReturnCaseRow.status == "open",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.vendor_claim = row.contest_reason
            existing.customer_claim = row.complaint
            existing.amount_at_stake = row.amount_on_hold
            existing.deadline_seconds = 300
            existing.chat = list(row.chat or [])
            existing.meta = {
                **dict(existing.meta or {}),
                "vendor_return_id": str(row.id),
                "escalated_from": "vendor_settlement",
            }
            return
        self._session.add(
            SettlementReturnCaseRow(
                id=uuid.uuid4(),
                order_ref=row.order_ref,
                vendor_name="Idli Dosa Co.",
                case_type="contested",
                status="open",
                customer_claim=row.complaint,
                vendor_claim=row.contest_reason,
                reason_code=row.reason_code,
                amount_at_stake=row.amount_on_hold,
                refund_amount=None,
                summary="",
                timeline=row.timeline,
                deadline_seconds=300,
                chat=list(row.chat or []),
                meta={
                    "vendor_return_id": str(row.id),
                    "escalated_from": "vendor_settlement",
                    "customer_name": row.customer_name,
                },
            )
        )

    @staticmethod
    def _inr(value: Decimal | float | int | None) -> str:
        amount = float(value or 0)
        formatted = f"{amount:,.2f}".rstrip("0").rstrip(".")
        return f"₹{formatted}"

    async def _mark_order_refunded(self, vendor_id: UUID, order_ref: str) -> None:
        row = (
            await self._session.execute(
                select(VendorSettlementOrderRow).where(
                    VendorSettlementOrderRow.vendor_id == vendor_id,
                    VendorSettlementOrderRow.order_ref == order_ref,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = "refunded"
        row.settlement_label = "₹0 — Refund"
        row.return_label = "Vendor accepted"
        row.window_label = ""
        row.net = _d("0")

    async def _mark_order_contested(self, vendor_id: UUID, order_ref: str) -> None:
        row = (
            await self._session.execute(
                select(VendorSettlementOrderRow).where(
                    VendorSettlementOrderRow.vendor_id == vendor_id,
                    VendorSettlementOrderRow.order_ref == order_ref,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = "on_hold"
        row.settlement_label = "On Hold"
        row.return_label = "Contested"
        row.window_label = "Pending decision"

    async def _ensure_seeded(self, vendor_id: UUID) -> None:
        order_count = (
            await self._session.execute(
                select(func.count())
                .select_from(VendorSettlementOrderRow)
                .where(VendorSettlementOrderRow.vendor_id == vendor_id)
            )
        ).scalar_one()
        added = False
        if order_count == 0:
            for seed in ORDER_SEEDS:
                self._session.add(
                    VendorSettlementOrderRow(
                        id=uuid.uuid4(),
                        vendor_id=vendor_id,
                        order_ref=seed["order_ref"],
                        order_time=seed["order_time"],
                        items=seed["items"],
                        gross=seed["gross"],
                        net=seed["net"],
                        status=seed["status"],
                        window_label=seed["window_label"],
                        settlement_label=seed["settlement_label"],
                        return_label=seed["return_label"],
                        in_tracker=seed["in_tracker"],
                        in_today=seed["in_today"],
                    )
                )
            added = True

        return_count = (
            await self._session.execute(
                select(func.count())
                .select_from(VendorSettlementReturnRow)
                .where(VendorSettlementReturnRow.vendor_id == vendor_id)
            )
        ).scalar_one()
        if return_count == 0:
            seed = RETURN_SEED
            self._session.add(
                VendorSettlementReturnRow(
                    id=uuid.uuid4(),
                    vendor_id=vendor_id,
                    order_ref=seed["order_ref"],
                    customer_name=seed["customer_name"],
                    complaint=seed["complaint"],
                    reason_code=seed["reason_code"],
                    refund_requested=seed["refund_requested"],
                    amount_on_hold=seed["amount_on_hold"],
                    order_items=seed["order_items"],
                    timeline=seed["timeline"],
                    deadline_seconds=seed["deadline_seconds"],
                    status=seed["status"],
                    contest_reason=seed["contest_reason"],
                    chat=list(seed["chat"]),
                    meta=dict(seed["meta"]),
                )
            )
            added = True

        history_count = (
            await self._session.execute(
                select(func.count())
                .select_from(VendorSettlementHistoryRow)
                .where(VendorSettlementHistoryRow.vendor_id == vendor_id)
            )
        ).scalar_one()
        if history_count == 0:
            for seed in HISTORY_SEEDS:
                self._session.add(
                    VendorSettlementHistoryRow(
                        id=uuid.uuid4(),
                        vendor_id=vendor_id,
                        settle_date=seed["settle_date"],
                        orders=seed["orders"],
                        gross=seed["gross"],
                        deductions=seed["deductions"],
                        refund_adj=seed["refund_adj"],
                        net=seed["net"],
                        utr=seed["utr"],
                    )
                )
            added = True

        bank = (
            await self._session.execute(
                select(VendorSettlementBankRow).where(
                    VendorSettlementBankRow.vendor_id == vendor_id
                )
            )
        ).scalar_one_or_none()
        if bank is None:
            self._session.add(
                VendorSettlementBankRow(
                    id=uuid.uuid4(),
                    vendor_id=vendor_id,
                    bank_name=BANK_SEED["bank_name"],
                    account_mask=BANK_SEED["account_mask"],
                    ifsc=BANK_SEED["ifsc"],
                    branch=BANK_SEED["branch"],
                    verified=BANK_SEED["verified"],
                )
            )
            added = True

        if added:
            await self._session.commit()

    @staticmethod
    def _order_view(row: VendorSettlementOrderRow) -> OrderView:
        return OrderView(
            id=str(row.id),
            order_ref=row.order_ref,
            order_time=row.order_time,
            items=row.items,
            gross=float(row.gross or 0),
            net=float(row.net or 0),
            status=row.status,
            window_label=row.window_label,
            settlement_label=row.settlement_label,
            return_label=row.return_label,
            in_tracker=row.in_tracker,
            in_today=row.in_today,
        )

    @staticmethod
    def _return_view(row: VendorSettlementReturnRow) -> ReturnView:
        return ReturnView(
            id=str(row.id),
            order_ref=row.order_ref,
            customer_name=row.customer_name,
            complaint=row.complaint,
            reason_code=row.reason_code,
            refund_requested=float(row.refund_requested or 0),
            amount_on_hold=float(row.amount_on_hold or 0),
            order_items=row.order_items,
            timeline=row.timeline,
            deadline_seconds=row.deadline_seconds,
            status=row.status,
            contest_reason=row.contest_reason,
            chat=list(row.chat or []),
            meta=dict(row.meta or {}),
        )

    @staticmethod
    def _history_view(row: VendorSettlementHistoryRow) -> HistoryView:
        return HistoryView(
            id=str(row.id),
            settle_date=row.settle_date,
            orders=row.orders,
            gross=float(row.gross or 0),
            deductions=float(row.deductions or 0),
            refund_adj=float(row.refund_adj or 0),
            net=float(row.net or 0),
            utr=row.utr,
        )
