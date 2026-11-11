"""Platform Admin Settlement Hub.

IMPS settlement batches, contested return queue, vendor ledger, TDS/GST,
escrow monitor, platform faults, and fraud signals — seeded from the Admin
Settlement mock for local demos.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from marketplace.application.access import audit, require_platform_operator
from platform_ops.infrastructure.models import (
    SettlementBatchRow,
    SettlementEscrowOrderRow,
    SettlementFaultRow,
    SettlementFraudSignalRow,
    SettlementLedgerLineRow,
    SettlementReturnCaseRow,
    SettlementTdsRow,
)
from shared.domain.exceptions import NotFoundError, ValidationError

BATCH_DATE = date(2026, 10, 30)
DEFAULT_VENDOR = "Idli Dosa Co."


def _d(value: str | float | int) -> Decimal:
    return Decimal(str(value))


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


BATCH_SEEDS: tuple[dict, ...] = (
    {
        "batch_time": "15:00",
        "vendors": 8,
        "orders": 42,
        "gross": _d("8240"),
        "deductions": _d("1648"),
        "net": _d("6592"),
        "status": "done",
        "utr": "RAZR2610291847",
    },
    {
        "batch_time": "14:00",
        "vendors": 11,
        "orders": 58,
        "gross": _d("11600"),
        "deductions": _d("2320"),
        "net": _d("9280"),
        "status": "done",
        "utr": "RAZR2610291622",
    },
    {
        "batch_time": "13:00",
        "vendors": 9,
        "orders": 47,
        "gross": _d("9400"),
        "deductions": _d("1880"),
        "net": _d("7520"),
        "status": "done",
        "utr": None,
    },
    {
        "batch_time": "12:00",
        "vendors": 7,
        "orders": 31,
        "gross": _d("6200"),
        "deductions": _d("1240"),
        "net": _d("4960"),
        "status": "failed_retry",
        "utr": None,
    },
    {
        "batch_time": "16:00",
        "vendors": None,
        "orders": None,
        "gross": None,
        "deductions": None,
        "net": None,
        "status": "pending",
        "utr": None,
    },
)

RETURN_SEEDS: tuple[dict, ...] = (
    {
        "order_ref": "#4521",
        "vendor_name": "Idli Dosa Co.",
        "case_type": "contested",
        "status": "open",
        "customer_claim": (
            "Received plain Idli instead of Masala Dosa. Completely wrong item delivered."
        ),
        "vendor_claim": (
            "We sent the correct Masala Dosa. Customer is lying. Photo is from another order."
        ),
        "reason_code": "wrong_item",
        "amount_at_stake": _d("120"),
        "refund_amount": None,
        "summary": "",
        "timeline": (
            "Order placed 14:22 · Delivered 14:58 · Return raised 15:04 · Vendor contested 15:07"
        ),
        "deadline_seconds": 222,
        "chat": [
            {"kind": "system", "text": "14:22 · Order placed"},
            {
                "kind": "customer",
                "text": "Please add extra chutney if possible",
            },
            {"kind": "vendor", "text": "Sure! Extra chutney noted ✓"},
            {"kind": "system", "text": "14:58 · Delivered"},
            {"kind": "customer", "text": "This is Idli not Masala Dosa!"},
            {"kind": "vendor", "text": "We sent Masala Dosa only"},
            {"kind": "alert", "text": "Return raised 15:04 — chat locked"},
        ],
        "meta": {},
    },
    {
        "order_ref": "#4518",
        "vendor_name": "Idli Dosa Co.",
        "case_type": "vendor_accepted",
        "status": "resolved",
        "customer_claim": "",
        "vendor_claim": "",
        "reason_code": "missing_item",
        "amount_at_stake": _d("200"),
        "refund_amount": _d("200"),
        "summary": (
            "Vendor accepted fault — Missing item (Medu Vada ₹40). Full refund ₹200 processed. "
            "Vendor settlement adjusted: ₹130.40. No admin action needed."
        ),
        "timeline": "2 min ago",
        "deadline_seconds": None,
        "chat": [],
        "meta": {},
    },
    {
        "order_ref": "#4510",
        "vendor_name": "",
        "case_type": "platform_fault",
        "status": "resolved",
        "customer_claim": "",
        "vendor_claim": "",
        "reason_code": "double_charge",
        "amount_at_stake": _d("180"),
        "refund_amount": _d("180"),
        "summary": (
            "Payment gateway double-charged customer ₹180. Second charge auto-refunded in 28 "
            "seconds. Vendor settlement not touched. Platform absorbed ₹180. Razorpay webhook "
            "confirmed."
        ),
        "timeline": "11:02 AM",
        "deadline_seconds": None,
        "chat": [],
        "meta": {},
    },
    {
        "order_ref": "#4505",
        "vendor_name": "Sagar Udupi",
        "case_type": "timed_out",
        "status": "resolved",
        "customer_claim": "",
        "vendor_claim": "",
        "reason_code": "timeout",
        "amount_at_stake": _d("160"),
        "refund_amount": _d("160"),
        "summary": (
            "Vendor did not respond within 5 minutes. Return auto-accepted as vendor fault. "
            "Refund ₹160 processed. Settlement adjusted. Vendor warned (2nd timeout this week)."
        ),
        "timeline": "9:45 AM",
        "deadline_seconds": None,
        "chat": [],
        "meta": {},
    },
)

LEDGER_SEEDS: tuple[dict, ...] = (
    {
        "vendor_name": "Idli Dosa Co.",
        "order_ref": "#4521",
        "order_time": "15:04",
        "items": "Masala Dosa, Coffee",
        "gross": _d("200"),
        "deductions": _d("29.60"),
        "net_label": "HOLD",
        "status": "return_contested",
        "utr": None,
    },
    {
        "vendor_name": "Idli Dosa Co.",
        "order_ref": "#4518",
        "order_time": "14:22",
        "items": "3× Idli, Vada",
        "gross": _d("200"),
        "deductions": _d("69.60"),
        "net_label": "₹0",
        "status": "vendor_fault",
        "utr": "Adjusted",
    },
    {
        "vendor_name": "Idli Dosa Co.",
        "order_ref": "#4512",
        "order_time": "13:40",
        "items": "Rava Idli, Coffee",
        "gross": _d("160"),
        "deductions": _d("23.68"),
        "net_label": "₹136.32",
        "status": "settled",
        "utr": "RAZR261029..91",
    },
    {
        "vendor_name": "Idli Dosa Co.",
        "order_ref": "#4508",
        "order_time": "12:55",
        "items": "Dosa, Sambar, Coffee",
        "gross": _d("240"),
        "deductions": _d("35.52"),
        "net_label": "₹204.48",
        "status": "settled",
        "utr": "RAZR261029..84",
    },
)

TDS_SEEDS: tuple[dict, ...] = (
    {
        "vendor_name": "Idli Dosa Co.",
        "period": "Oct 2026",
        "gross_paid": _d("42100"),
        "tds_amount": _d("421"),
        "net_paid": _d("41679"),
    },
    {
        "vendor_name": "Sagar Udupi",
        "period": "Oct 2026",
        "gross_paid": _d("38600"),
        "tds_amount": _d("386"),
        "net_paid": _d("38214"),
    },
    {
        "vendor_name": "Chennai Express",
        "period": "Oct 2026",
        "gross_paid": _d("28400"),
        "tds_amount": _d("284"),
        "net_paid": _d("28116"),
    },
)

ESCROW_SEEDS: tuple[dict, ...] = (
    {
        "order_ref": "#4523",
        "vendor_name": "Idli Dosa Co.",
        "delivered_at": "15:28",
        "window_closes_at": "15:58",
        "minutes_left": 8,
        "amount": _d("170.40"),
        "status": "window_open",
    },
    {
        "order_ref": "#4522",
        "vendor_name": "Sagar Udupi",
        "delivered_at": "15:24",
        "window_closes_at": "15:54",
        "minutes_left": 4,
        "amount": _d("204.48"),
        "status": "window_open",
    },
    {
        "order_ref": "#4520",
        "vendor_name": "Idli Dosa Co.",
        "delivered_at": "15:10",
        "window_closes_at": "15:40",
        "minutes_left": None,
        "amount": _d("136.32"),
        "status": "released",
    },
)

FAULT_SEEDS: tuple[dict, ...] = (
    {
        "order_ref": "#4510",
        "fault_type": "Double charge",
        "customer_name": "Priya S.",
        "refund_amount": _d("180"),
        "resolved_in": "28 sec",
        "vendor_impact": "not_touched",
    },
    {
        "order_ref": "#4498",
        "fault_type": "Order not created after payment",
        "customer_name": "Rahul V.",
        "refund_amount": _d("120"),
        "resolved_in": "14 sec",
        "vendor_impact": "not_touched",
    },
    {
        "order_ref": "#4481",
        "fault_type": "App showed wrong price",
        "customer_name": "Ananya I.",
        "refund_amount": _d("40"),
        "resolved_in": "45 sec",
        "vendor_impact": "full_settled",
    },
)

FRAUD_SEEDS: tuple[dict, ...] = (
    {
        "party_name": "Sunita R. (Customer)",
        "party_type": "customer",
        "signal": '5 returns in 7 days, all "wrong item"',
        "returns_label": "5/6 orders",
        "action_label": "Flag Account",
        "status": "open",
    },
    {
        "party_name": "Quick Dosa Hub (Vendor)",
        "party_type": "vendor",
        "signal": "3 timeout auto-accepts this week",
        "returns_label": "—",
        "action_label": "Send Warning",
        "status": "open",
    },
)

LEDGER_SUMMARY = {
    "gross_orders": 14200.0,
    "platform_commission": -1420.0,
    "gst_on_commission": -255.0,
    "gateway_fee": -284.0,
    "tds": -142.0,
    "refund_adjustments": -340.0,
    "net_settled": 11759.0,
}

ESCROW_BREAKDOWN = {
    "total": 84320.0,
    "settled_queue": 32041.0,
    "in_window": 22766.0,
    "on_hold": 10118.0,
    "platform_float": 19395.0,
}


@dataclass(frozen=True, slots=True)
class BatchView:
    id: str
    batch_time: str
    vendors: int | None
    orders: int | None
    gross: float | None
    deductions: float | None
    net: float | None
    status: str
    utr: str | None
    batch_date: str


@dataclass(frozen=True, slots=True)
class ReturnCaseView:
    id: str
    order_ref: str
    vendor_name: str
    case_type: str
    status: str
    customer_claim: str
    vendor_claim: str
    reason_code: str
    amount_at_stake: float
    refund_amount: float | None
    summary: str
    timeline: str
    deadline_seconds: int | None
    chat: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LedgerLineView:
    id: str
    vendor_name: str
    order_ref: str
    order_time: str
    items: str
    gross: float
    deductions: float
    net_label: str
    status: str
    utr: str | None


@dataclass(frozen=True, slots=True)
class TdsRowView:
    id: str
    vendor_name: str
    period: str
    gross_paid: float
    tds_amount: float
    net_paid: float


@dataclass(frozen=True, slots=True)
class EscrowOrderView:
    id: str
    order_ref: str
    vendor_name: str
    delivered_at: str
    window_closes_at: str
    minutes_left: int | None
    amount: float
    status: str


@dataclass(frozen=True, slots=True)
class FaultView:
    id: str
    order_ref: str
    fault_type: str
    customer_name: str
    refund_amount: float
    resolved_in: str
    vendor_impact: str


@dataclass(frozen=True, slots=True)
class FraudSignalView:
    id: str
    party_name: str
    party_type: str
    signal: str
    returns_label: str
    action_label: str
    status: str


class SettlementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def dashboard(self, *, caller_user_id: UUID, period: str = "today") -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        period_key = (period or "today").strip().lower()
        if period_key not in {"today", "week", "month"}:
            raise ValidationError("period must be today, week, or month")

        batches = (
            (
                await self._session.execute(
                    select(SettlementBatchRow)
                    .where(SettlementBatchRow.batch_date == BATCH_DATE)
                    .order_by(SettlementBatchRow.batch_time.desc())
                )
            )
            .scalars()
            .all()
        )
        open_returns = (
            await self._session.execute(
                select(func.count())
                .select_from(SettlementReturnCaseRow)
                .where(SettlementReturnCaseRow.status == "open")
            )
        ).scalar_one()
        window_orders = (
            await self._session.execute(
                select(func.count())
                .select_from(SettlementEscrowOrderRow)
                .where(SettlementEscrowOrderRow.status == "window_open")
            )
        ).scalar_one()
        failed = sum(1 for b in batches if b.status == "failed_retry")

        common = {
            "zone": "Airoli Zone",
            "as_of": "30 Oct 2026",
            "live": True,
            "batches": [asdict(self._batch_view(row)) for row in batches],
            "escrow": dict(ESCROW_BREAKDOWN),
            "open_returns": int(open_returns),
            "in_return_window": int(window_orders) + 21,
            "failed_imps": failed,
        }

        if period_key == "week":
            return {
                **common,
                "period": "week",
                "kpis": {
                    "week_settled": 214800.0,
                    "orders_processed": 1243,
                    "returns_this_week": 18,
                    "return_rate_pct": 1.4,
                },
            }
        if period_key == "month":
            return {
                **common,
                "period": "month",
                "kpis": {
                    "month_settled": 842300.0,
                    "platform_commission": 84230.0,
                    "tds_accumulated": 4210.0,
                    "gst_on_commission": 15160.0,
                },
            }
        return {
            **common,
            "period": "today",
            "kpis": {
                "live_escrow": ESCROW_BREAKDOWN["total"],
                "escrow_vendors": 12,
                "auto_settlements": 187,
                "auto_settlements_amount": 31840.0,
                "in_return_window": int(window_orders) + 21,
                "returns_under_review": int(open_returns),
                "returns_contested_by_vendor": 2,
                "tds_accumulated": 4210.0,
                "tds_deposit_by": "7 Nov",
                "failed_imps": failed,
            },
        }

    async def return_queue(self, *, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (
            (
                await self._session.execute(
                    select(SettlementReturnCaseRow).order_by(
                        SettlementReturnCaseRow.created_at.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        open_count = sum(1 for row in rows if row.status == "open")
        return {
            "info": (
                "These are contested returns — vendor rejected the customer's claim. "
                "Auto-accepted returns don't appear here for action. Decide within 5 minutes."
            ),
            "open_count": open_count,
            "items": [asdict(self._return_view(row)) for row in rows],
        }

    async def resolve_return(
        self,
        *,
        caller_user_id: UUID,
        case_id: UUID,
        outcome: str,
        amount: float | None = None,
        reason: str | None = None,
    ) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        row = await self._session.get(SettlementReturnCaseRow, case_id)
        if row is None:
            raise NotFoundError("return case not found")
        if row.status != "open":
            raise ValidationError("return case is already resolved")
        outcome_key = outcome.strip().lower()
        if outcome_key not in {"refund", "support_vendor", "partial"}:
            raise ValidationError("outcome must be refund, support_vendor, or partial")

        now = utcnow()
        if outcome_key == "refund":
            row.status = "resolved"
            row.refund_amount = row.amount_at_stake
            row.summary = (
                f"Refund approved — vendor settlement adjusted. Order {row.order_ref}."
            )
            message = f"Refund approved — vendor settlement adjusted · Order {row.order_ref}"
        elif outcome_key == "support_vendor":
            row.status = "resolved"
            row.refund_amount = _d("0")
            row.summary = (
                f"Vendor supported — customer refund rejected. Order {row.order_ref}."
            )
            message = f"Vendor supported — customer refund rejected · Order {row.order_ref}"
        else:
            if amount is None or amount <= 0:
                raise ValidationError("partial refund requires a positive amount")
            row.status = "resolved"
            row.refund_amount = _d(amount)
            note = (reason or "").strip() or "Partial refund processed"
            row.summary = f"{note}. Partial refund ₹{amount:.2f} for {row.order_ref}."
            message = f"Partial refund processed · Order {row.order_ref}"

        row.resolved_at = now
        row.meta = {
            **dict(row.meta or {}),
            "outcome": outcome_key,
            "resolved_by": str(caller_user_id),
            "reason": (reason or "").strip() or None,
        }
        await audit(
            self._session,
            action="settlement.return_resolved",
            actor_user_id=caller_user_id,
            payload={
                "case_id": str(row.id),
                "order_ref": row.order_ref,
                "outcome": outcome_key,
                "refund_amount": _money(row.refund_amount),
            },
        )
        await self._session.commit()
        await self._session.refresh(row)
        return {"message": message, "item": asdict(self._return_view(row))}

    async def vendor_ledger(
        self, *, caller_user_id: UUID, vendor_name: str | None = None
    ) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        vendor = (vendor_name or DEFAULT_VENDOR).strip() or DEFAULT_VENDOR
        rows = (
            (
                await self._session.execute(
                    select(SettlementLedgerLineRow)
                    .where(SettlementLedgerLineRow.vendor_name == vendor)
                    .order_by(SettlementLedgerLineRow.order_time.desc())
                )
            )
            .scalars()
            .all()
        )
        vendors = (
            (
                await self._session.execute(
                    select(SettlementLedgerLineRow.vendor_name).distinct()
                )
            )
            .scalars()
            .all()
        )
        return {
            "vendor_name": vendor,
            "vendors": sorted(vendors),
            "summary": dict(LEDGER_SUMMARY),
            "items": [asdict(self._ledger_view(row)) for row in rows],
        }

    async def tds_gst(self, *, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (
            (
                await self._session.execute(
                    select(SettlementTdsRow).order_by(SettlementTdsRow.vendor_name.asc())
                )
            )
            .scalars()
            .all()
        )
        return {
            "period": "Oct 2026",
            "kpis": {
                "tds_this_month": 4210.0,
                "tds_deposit_by": "7 Nov",
                "gst_on_commission": 15160.0,
                "gst_file_by": "20 Nov",
                "total_commission": 84230.0,
            },
            "items": [asdict(self._tds_view(row)) for row in rows],
        }

    async def escrow(self, *, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (
            (
                await self._session.execute(
                    select(SettlementEscrowOrderRow).order_by(
                        SettlementEscrowOrderRow.delivered_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            "info": (
                "Razorpay Route escrow. Funds shown are held in Razorpay — not in the "
                "platform's bank account. Releases happen automatically via Route Transfer "
                "API on settlement trigger."
            ),
            "kpis": {
                "total_escrow": ESCROW_BREAKDOWN["total"],
                "queued_for_release": ESCROW_BREAKDOWN["settled_queue"],
                "in_return_window": ESCROW_BREAKDOWN["in_window"],
                "on_hold": ESCROW_BREAKDOWN["on_hold"],
            },
            "items": [asdict(self._escrow_view(row)) for row in rows],
        }

    async def faults(self, *, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (
            (
                await self._session.execute(
                    select(SettlementFaultRow).order_by(SettlementFaultRow.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        absorbed = sum(float(row.refund_amount) for row in rows)
        return {
            "kpis": {
                "faults_today": len(rows),
                "platform_absorbed": absorbed,
                "auto_resolved_pct": 100.0,
            },
            "items": [asdict(self._fault_view(row)) for row in rows],
        }

    async def fraud_signals(self, *, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (
            (
                await self._session.execute(
                    select(SettlementFraudSignalRow).order_by(
                        SettlementFraudSignalRow.created_at.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            "info": (
                "Customers or vendors flagged by the system for abnormal return/complaint "
                "patterns."
            ),
            "items": [asdict(self._fraud_view(row)) for row in rows],
        }

    async def act_on_fraud(
        self, *, caller_user_id: UUID, signal_id: UUID, action: str
    ) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        row = await self._session.get(SettlementFraudSignalRow, signal_id)
        if row is None:
            raise NotFoundError("fraud signal not found")
        action_key = action.strip().lower()
        if action_key not in {"flag", "warn", "dismiss"}:
            raise ValidationError("action must be flag, warn, or dismiss")
        if action_key == "flag":
            row.status = "flagged"
            message = f"Account flagged · {row.party_name}"
        elif action_key == "warn":
            row.status = "warned"
            message = f"Warning sent · {row.party_name}"
        else:
            row.status = "dismissed"
            message = f"Signal dismissed · {row.party_name}"
        await audit(
            self._session,
            action="settlement.fraud_action",
            actor_user_id=caller_user_id,
            payload={
                "signal_id": str(row.id),
                "party_name": row.party_name,
                "action": action_key,
            },
        )
        await self._session.commit()
        await self._session.refresh(row)
        return {"message": message, "item": asdict(self._fraud_view(row))}

    async def _ensure_seeded(self) -> None:
        added = False
        batch_count = (
            await self._session.execute(select(func.count()).select_from(SettlementBatchRow))
        ).scalar_one()
        if batch_count == 0:
            for seed in BATCH_SEEDS:
                self._session.add(
                    SettlementBatchRow(
                        id=uuid.uuid4(),
                        batch_time=seed["batch_time"],
                        vendors=seed["vendors"],
                        orders=seed["orders"],
                        gross=seed["gross"],
                        deductions=seed["deductions"],
                        net=seed["net"],
                        status=seed["status"],
                        utr=seed["utr"],
                        batch_date=BATCH_DATE,
                    )
                )
            added = True

        return_count = (
            await self._session.execute(
                select(func.count()).select_from(SettlementReturnCaseRow)
            )
        ).scalar_one()
        if return_count == 0:
            for seed in RETURN_SEEDS:
                self._session.add(
                    SettlementReturnCaseRow(
                        id=uuid.uuid4(),
                        order_ref=seed["order_ref"],
                        vendor_name=seed["vendor_name"],
                        case_type=seed["case_type"],
                        status=seed["status"],
                        customer_claim=seed["customer_claim"],
                        vendor_claim=seed["vendor_claim"],
                        reason_code=seed["reason_code"],
                        amount_at_stake=seed["amount_at_stake"],
                        refund_amount=seed["refund_amount"],
                        summary=seed["summary"],
                        timeline=seed["timeline"],
                        deadline_seconds=seed["deadline_seconds"],
                        chat=list(seed["chat"]),
                        meta=dict(seed["meta"]),
                        resolved_at=None if seed["status"] == "open" else utcnow(),
                    )
                )
            added = True

        ledger_count = (
            await self._session.execute(
                select(func.count()).select_from(SettlementLedgerLineRow)
            )
        ).scalar_one()
        if ledger_count == 0:
            for seed in LEDGER_SEEDS:
                self._session.add(
                    SettlementLedgerLineRow(
                        id=uuid.uuid4(),
                        vendor_name=seed["vendor_name"],
                        order_ref=seed["order_ref"],
                        order_time=seed["order_time"],
                        items=seed["items"],
                        gross=seed["gross"],
                        deductions=seed["deductions"],
                        net_label=seed["net_label"],
                        status=seed["status"],
                        utr=seed["utr"],
                    )
                )
            added = True

        tds_count = (
            await self._session.execute(select(func.count()).select_from(SettlementTdsRow))
        ).scalar_one()
        if tds_count == 0:
            for seed in TDS_SEEDS:
                self._session.add(
                    SettlementTdsRow(
                        id=uuid.uuid4(),
                        vendor_name=seed["vendor_name"],
                        period=seed["period"],
                        gross_paid=seed["gross_paid"],
                        tds_amount=seed["tds_amount"],
                        net_paid=seed["net_paid"],
                    )
                )
            added = True

        escrow_count = (
            await self._session.execute(
                select(func.count()).select_from(SettlementEscrowOrderRow)
            )
        ).scalar_one()
        if escrow_count == 0:
            for seed in ESCROW_SEEDS:
                self._session.add(
                    SettlementEscrowOrderRow(
                        id=uuid.uuid4(),
                        order_ref=seed["order_ref"],
                        vendor_name=seed["vendor_name"],
                        delivered_at=seed["delivered_at"],
                        window_closes_at=seed["window_closes_at"],
                        minutes_left=seed["minutes_left"],
                        amount=seed["amount"],
                        status=seed["status"],
                    )
                )
            added = True

        fault_count = (
            await self._session.execute(select(func.count()).select_from(SettlementFaultRow))
        ).scalar_one()
        if fault_count == 0:
            for seed in FAULT_SEEDS:
                self._session.add(
                    SettlementFaultRow(
                        id=uuid.uuid4(),
                        order_ref=seed["order_ref"],
                        fault_type=seed["fault_type"],
                        customer_name=seed["customer_name"],
                        refund_amount=seed["refund_amount"],
                        resolved_in=seed["resolved_in"],
                        vendor_impact=seed["vendor_impact"],
                    )
                )
            added = True

        fraud_count = (
            await self._session.execute(
                select(func.count()).select_from(SettlementFraudSignalRow)
            )
        ).scalar_one()
        if fraud_count == 0:
            for seed in FRAUD_SEEDS:
                self._session.add(
                    SettlementFraudSignalRow(
                        id=uuid.uuid4(),
                        party_name=seed["party_name"],
                        party_type=seed["party_type"],
                        signal=seed["signal"],
                        returns_label=seed["returns_label"],
                        action_label=seed["action_label"],
                        status=seed["status"],
                    )
                )
            added = True

        if added:
            await self._session.commit()

    @staticmethod
    def _batch_view(row: SettlementBatchRow) -> BatchView:
        return BatchView(
            id=str(row.id),
            batch_time=row.batch_time,
            vendors=row.vendors,
            orders=row.orders,
            gross=_money(row.gross),
            deductions=_money(row.deductions),
            net=_money(row.net),
            status=row.status,
            utr=row.utr,
            batch_date=row.batch_date.isoformat(),
        )

    @staticmethod
    def _return_view(row: SettlementReturnCaseRow) -> ReturnCaseView:
        return ReturnCaseView(
            id=str(row.id),
            order_ref=row.order_ref,
            vendor_name=row.vendor_name,
            case_type=row.case_type,
            status=row.status,
            customer_claim=row.customer_claim,
            vendor_claim=row.vendor_claim,
            reason_code=row.reason_code,
            amount_at_stake=float(row.amount_at_stake or 0),
            refund_amount=_money(row.refund_amount),
            summary=row.summary,
            timeline=row.timeline,
            deadline_seconds=row.deadline_seconds,
            chat=list(row.chat or []),
            meta=dict(row.meta or {}),
        )

    @staticmethod
    def _ledger_view(row: SettlementLedgerLineRow) -> LedgerLineView:
        return LedgerLineView(
            id=str(row.id),
            vendor_name=row.vendor_name,
            order_ref=row.order_ref,
            order_time=row.order_time,
            items=row.items,
            gross=float(row.gross or 0),
            deductions=float(row.deductions or 0),
            net_label=row.net_label,
            status=row.status,
            utr=row.utr,
        )

    @staticmethod
    def _tds_view(row: SettlementTdsRow) -> TdsRowView:
        return TdsRowView(
            id=str(row.id),
            vendor_name=row.vendor_name,
            period=row.period,
            gross_paid=float(row.gross_paid or 0),
            tds_amount=float(row.tds_amount or 0),
            net_paid=float(row.net_paid or 0),
        )

    @staticmethod
    def _escrow_view(row: SettlementEscrowOrderRow) -> EscrowOrderView:
        return EscrowOrderView(
            id=str(row.id),
            order_ref=row.order_ref,
            vendor_name=row.vendor_name,
            delivered_at=row.delivered_at,
            window_closes_at=row.window_closes_at,
            minutes_left=row.minutes_left,
            amount=float(row.amount or 0),
            status=row.status,
        )

    @staticmethod
    def _fault_view(row: SettlementFaultRow) -> FaultView:
        return FaultView(
            id=str(row.id),
            order_ref=row.order_ref,
            fault_type=row.fault_type,
            customer_name=row.customer_name,
            refund_amount=float(row.refund_amount or 0),
            resolved_in=row.resolved_in,
            vendor_impact=row.vendor_impact,
        )

    @staticmethod
    def _fraud_view(row: SettlementFraudSignalRow) -> FraudSignalView:
        return FraudSignalView(
            id=str(row.id),
            party_name=row.party_name,
            party_type=row.party_type,
            signal=row.signal,
            returns_label=row.returns_label,
            action_label=row.action_label,
            status=row.status,
        )
