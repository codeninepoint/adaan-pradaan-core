"""Platform Admin Communications Hub.

Master template library (SMS / WhatsApp / Email / In-App), DLT compliance
snapshot, usage audit log, and consent/opt-out registry. Templates are
platform-owned; vendors pick from approved ones (vendor portal is separate).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from marketplace.application.access import audit, require_platform_operator
from platform_ops.infrastructure.models import (
    CommunicationOptoutRow,
    CommunicationTemplateRow,
    CommunicationUsageLogRow,
)
from shared.domain.exceptions import NotFoundError, ValidationError

CHANNELS = ("sms", "whatsapp", "email", "inapp")
APPROVED_STATUSES = frozenset(
    {"dlt_approved", "meta_approved", "internal_approved"}
)
PENDING_STATUSES = frozenset({"dlt_pending", "meta_pending"})

DLT_ENTITY = {
    "entity_name": "ADANPRADAN TECH LLP",
    "entity_id": "XXXXXXXX",
    "registered_on": "Vodafone DLT",
    "renewal": "Jun 2027",
    "status": "active",
    "sender_header": "CRAFTD",
    "sender_header_status": "active",
    "waba_status": "verified",
    "bsp": "AiSensy",
    "free_conversations_month": 1000,
}


def _dt(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


TEMPLATE_SEEDS: tuple[dict, ...] = (
    {
        "code": "CRAFTD_PROMO_01",
        "name": "Promo Code Blast",
        "channel": "sms",
        "plugin": "Sales",
        "message_type": "Marketing",
        "body": (
            "Dear {#var#}, enjoy {#var#}% off on {#var#}! Use code {#var#}. "
            "Shop: {#var#}. Reply STOP to opt out. -CRAFTD"
        ),
        "approval_status": "dlt_approved",
        "dlt_reference": "DLT-2026-09-1102",
        "vendors_using": 12,
        "messages_sent_month": 3840,
        "variable_map": [
            {"index": 1, "label": "Customer name"},
            {"index": 2, "label": "Discount percentage"},
            {"index": 3, "label": "Product name"},
            {"index": 4, "label": "Promo code"},
            {"index": 5, "label": "Short URL (pre-registered domain)"},
        ],
        "meta": {},
        "submitted_at": _dt(2026, 9, 12),
    },
    {
        "code": "CRAFTD_ORDER_01",
        "name": "Order Confirmed",
        "channel": "sms",
        "plugin": "Sales",
        "message_type": "Transactional",
        "body": (
            "Hi {#var#}, your order #{#var#} for {#var#} is confirmed. "
            "Track: {#var#}. -CRAFTD"
        ),
        "approval_status": "dlt_approved",
        "dlt_reference": "DLT-2026-09-1188",
        "vendors_using": 31,
        "messages_sent_month": 9120,
        "variable_map": [
            {"index": 1, "label": "Customer name"},
            {"index": 2, "label": "Order id"},
            {"index": 3, "label": "Product name"},
            {"index": 4, "label": "Tracking URL"},
        ],
        "meta": {},
        "submitted_at": _dt(2026, 9, 14),
    },
    {
        "code": "WA_CAM_LAUNCH_01",
        "name": "Campaign Launch",
        "channel": "whatsapp",
        "plugin": "Marketing",
        "message_type": "Marketing",
        "body": (
            "Hi {{1}}! We are launching {{2}}. Exclusive early access: {{3}}."
        ),
        "approval_status": "meta_approved",
        "dlt_reference": None,
        "vendors_using": 8,
        "messages_sent_month": 2100,
        "variable_map": [
            {"index": 1, "label": "Customer name"},
            {"index": 2, "label": "Product / campaign"},
            {"index": 3, "label": "Link"},
        ],
        "meta": {"buttons": []},
        "submitted_at": _dt(2026, 10, 1),
    },
    {
        "code": "WA_INF_BRIEF_01",
        "name": "Influencer Brief",
        "channel": "whatsapp",
        "plugin": "Publicity",
        "message_type": "Utility",
        "body": (
            "Hi {{1}}! We'd love to collaborate with you for {{2}}. "
            "Here's what we need: {{3}}. Deliverables due by {{4}}. "
            "Payout: ₹{{5}}. Interested?"
        ),
        "approval_status": "meta_pending",
        "dlt_reference": None,
        "vendors_using": 0,
        "messages_sent_month": 0,
        "variable_map": [
            {"index": 1, "label": "Influencer name"},
            {"index": 2, "label": "Campaign"},
            {"index": 3, "label": "Deliverables"},
            {"index": 4, "label": "Due date"},
            {"index": 5, "label": "Payout amount"},
        ],
        "meta": {"buttons": ["Interested", "Not Now"], "hsm_kind": "Utility HSM"},
        "submitted_at": _dt(2026, 10, 25),
    },
    {
        "code": "EMAIL_LEAD_FU_01",
        "name": "Lead Follow-up",
        "channel": "email",
        "plugin": "Sales",
        "message_type": "Marketing",
        "body": (
            "Subject: Following up on your enquiry about {product}\n"
            "Hi {name}, wanted to share more about our {offer}..."
        ),
        "approval_status": "internal_approved",
        "dlt_reference": None,
        "vendors_using": 19,
        "messages_sent_month": 1450,
        "variable_map": [
            {"index": 1, "label": "Product"},
            {"index": 2, "label": "Customer name"},
            {"index": 3, "label": "Offer"},
        ],
        "meta": {},
        "submitted_at": _dt(2026, 9, 20),
    },
    {
        "code": "INAPP_DEAL_01",
        "name": "Deal Stage Update",
        "channel": "inapp",
        "plugin": "Sales",
        "message_type": "Transactional",
        "body": (
            'Your deal "{deal_name}" moved to {stage}. Next step: {action}.'
        ),
        "approval_status": "internal_approved",
        "dlt_reference": None,
        "vendors_using": 24,
        "messages_sent_month": 980,
        "variable_map": [
            {"index": 1, "label": "Deal name"},
            {"index": 2, "label": "Stage"},
            {"index": 3, "label": "Next action"},
        ],
        "meta": {},
        "submitted_at": _dt(2026, 9, 22),
    },
    {
        "code": "CRAFTD_FEST_01",
        "name": "Festival Sale Announcement",
        "channel": "sms",
        "plugin": "Sales",
        "message_type": "Marketing",
        "body": (
            "Dear {#var#}, Celebrate {#var#} with exclusive deals on {#var#}. "
            "Use code {#var#} for {#var#}% off. Shop: {#var#}. "
            "Reply STOP to opt out. -CRAFTD"
        ),
        "approval_status": "dlt_pending",
        "dlt_reference": "DLT-2026-10-9281",
        "vendors_using": 0,
        "messages_sent_month": 0,
        "variable_map": [
            {"index": 1, "label": "Customer name"},
            {"index": 2, "label": "Festival"},
            {"index": 3, "label": "Category"},
            {"index": 4, "label": "Promo code"},
            {"index": 5, "label": "Discount"},
            {"index": 6, "label": "Shop URL"},
        ],
        "meta": {
            "dlt_progress": [
                {
                    "key": "entity",
                    "title": "Entity Registration",
                    "status": "done",
                    "detail": "Entity ID XXXXXXXX registered on DLT. Completed Oct 2026.",
                },
                {
                    "key": "header",
                    "title": "Sender Header Approved",
                    "status": "done",
                    "detail": "Header CRAFTD approved. All SMS sent from this alphanumeric ID.",
                },
                {
                    "key": "template",
                    "title": "Template Approval — In Progress",
                    "status": "active",
                    "detail": "Template submitted Oct 24. Avg review: 1–3 days. Expected: Oct 27.",
                    "progress_pct": 65,
                },
                {
                    "key": "live",
                    "title": "Live — Available to Vendors",
                    "status": "wait",
                    "detail": "Template unlocked in vendor library after approval.",
                },
            ],
            "expected_by": "2026-10-27",
        },
        "submitted_at": _dt(2026, 10, 24),
    },
    {
        "code": "CRAFTD_WHOLESALE_01",
        "name": "Wholesale Inquiry Reply",
        "channel": "sms",
        "plugin": "Sales",
        "message_type": "Transactional",
        "body": (
            "Hi {#var#}, thanks for your wholesale enquiry about {#var#}. "
            "Our team will call you at {#var#}. -CRAFTD"
        ),
        "approval_status": "dlt_pending",
        "dlt_reference": "DLT-2026-10-9315",
        "vendors_using": 0,
        "messages_sent_month": 0,
        "variable_map": [
            {"index": 1, "label": "Contact name"},
            {"index": 2, "label": "Product"},
            {"index": 3, "label": "Phone"},
        ],
        "meta": {"expected_by": "2026-10-28"},
        "submitted_at": _dt(2026, 10, 25),
    },
)

USAGE_SEEDS: tuple[dict, ...] = (
    {
        "occurred_at": _dt(2026, 10, 27, 14, 2),
        "vendor_name": "Crafted Roots Co.",
        "channel": "whatsapp",
        "template_code": "WA_CAM_LAUNCH_01",
        "template_name": "Campaign Launch",
        "audience": "Segment: Diwali",
        "sent": 480,
        "delivered": 471,
        "status": "done",
    },
    {
        "occurred_at": _dt(2026, 10, 27, 13, 45),
        "vendor_name": "Spice Route Foods",
        "channel": "sms",
        "template_code": "CRAFTD_PROMO_01",
        "template_name": "Promo Code Blast",
        "audience": "Tag: Wholesale",
        "sent": 220,
        "delivered": 198,
        "status": "done",
    },
    {
        "occurred_at": _dt(2026, 10, 27, 12, 30),
        "vendor_name": "Loom & Fabric",
        "channel": "email",
        "template_code": "EMAIL_LEAD_FU_01",
        "template_name": "Lead Follow-up",
        "audience": "Leads: Oct batch",
        "sent": 85,
        "delivered": 81,
        "status": "done",
    },
    {
        "occurred_at": _dt(2026, 10, 27, 11, 0),
        "vendor_name": "Crafted Roots Co.",
        "channel": "sms",
        "template_code": "CRAFTD_ORDER_01",
        "template_name": "Order Confirmed",
        "audience": "Buyers: 1-click",
        "sent": 12,
        "delivered": 12,
        "status": "done",
    },
    {
        "occurred_at": _dt(2026, 10, 26, 18, 20),
        "vendor_name": "Aranya Naturals",
        "channel": "inapp",
        "template_code": "INAPP_DEAL_01",
        "template_name": "Deal Stage Update",
        "audience": "Lead: single",
        "sent": 1,
        "delivered": 1,
        "status": "done",
    },
    {
        "occurred_at": _dt(2026, 10, 26, 17, 10),
        "vendor_name": "Nomad Leathers",
        "channel": "sms",
        "template_code": "CRAFTD_FEST_01",
        "template_name": "Festival Sale",
        "audience": "All customers",
        "sent": 340,
        "delivered": None,
        "status": "dlt_pending",
    },
)

OPTOUT_SEED_COUNTS = {"sms": 342, "whatsapp": 128, "email": 87, "inapp": 4}


@dataclass(frozen=True, slots=True)
class TemplateView:
    id: str
    code: str
    name: str
    channel: str
    plugin: str
    message_type: str
    body: str
    approval_status: str
    dlt_reference: str | None
    vendors_using: int
    messages_sent_month: int
    variable_map: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    submitted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class TemplateSummary:
    live: int
    pending: int
    sms: int
    whatsapp: int
    email: int
    inapp: int


@dataclass(frozen=True, slots=True)
class UsageLogView:
    id: str
    occurred_at: str
    vendor_name: str
    channel: str
    template_code: str
    template_name: str
    audience: str
    sent: int
    delivered: int | None
    status: str


@dataclass(frozen=True, slots=True)
class UsageSummary:
    messages_this_month: int
    sms_sent: int
    whatsapp_sent: int
    email_sent: int
    inapp_sent: int
    failed_or_opted_out: int
    warning: str | None = None


class CommunicationsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_templates(
        self, *, caller_user_id: UUID, status_filter: str | None = None
    ) -> tuple[list[TemplateView], TemplateSummary]:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (
            (
                await self._session.execute(
                    select(CommunicationTemplateRow).order_by(
                        CommunicationTemplateRow.created_at.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        views = [self._template_view(row) for row in rows]
        summary = TemplateSummary(
            live=sum(1 for v in views if v.approval_status in APPROVED_STATUSES),
            pending=sum(1 for v in views if v.approval_status in PENDING_STATUSES),
            sms=sum(1 for v in views if v.channel == "sms"),
            whatsapp=sum(1 for v in views if v.channel == "whatsapp"),
            email=sum(1 for v in views if v.channel == "email"),
            inapp=sum(1 for v in views if v.channel == "inapp"),
        )
        if status_filter == "pending":
            views = [v for v in views if v.approval_status in PENDING_STATUSES]
        elif status_filter == "live":
            views = [v for v in views if v.approval_status in APPROVED_STATUSES]
        return views, summary

    async def get_template(self, *, caller_user_id: UUID, template_id: UUID) -> TemplateView:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        row = await self._session.get(CommunicationTemplateRow, template_id)
        if row is None:
            raise NotFoundError("template not found")
        return self._template_view(row)

    async def create_template(
        self,
        *,
        caller_user_id: UUID,
        name: str,
        channel: str,
        plugin: str,
        message_type: str,
        body: str,
        code: str | None = None,
        buttons: str | None = None,
    ) -> TemplateView:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        channel_key = channel.strip().lower()
        if channel_key not in CHANNELS:
            raise ValidationError("channel must be sms, whatsapp, email, or inapp")
        name = name.strip()
        body = body.strip()
        if not name or not body:
            raise ValidationError("name and body are required")
        if channel_key == "sms":
            approval = "dlt_pending"
        elif channel_key == "whatsapp":
            approval = "meta_pending"
        else:
            approval = "internal_approved"
        now = utcnow()
        code_value = (code or "").strip().upper() or self._suggest_code(name, channel_key)
        existing = (
            await self._session.execute(
                select(CommunicationTemplateRow).where(CommunicationTemplateRow.code == code_value)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValidationError(f"template code already exists: {code_value}")
        meta: dict = {}
        if channel_key == "whatsapp" and buttons:
            meta["buttons"] = [part.strip() for part in buttons.split("/") if part.strip()]
        if channel_key == "sms":
            meta["dlt_progress"] = [
                {
                    "key": "entity",
                    "title": "Entity Registration",
                    "status": "done",
                    "detail": f"Entity ID {DLT_ENTITY['entity_id']} registered on DLT.",
                },
                {
                    "key": "header",
                    "title": "Sender Header Approved",
                    "status": "done",
                    "detail": f"Header {DLT_ENTITY['sender_header']} approved.",
                },
                {
                    "key": "template",
                    "title": "Template Approval — In Progress",
                    "status": "active",
                    "detail": "Submitted just now. Avg review: 1–3 days.",
                    "progress_pct": 10,
                },
                {
                    "key": "live",
                    "title": "Live — Available to Vendors",
                    "status": "wait",
                    "detail": "Template unlocked after approval.",
                },
            ]
            meta["expected_by"] = (now + timedelta(days=3)).date().isoformat()
        row = CommunicationTemplateRow(
            id=uuid.uuid4(),
            code=code_value,
            name=name,
            channel=channel_key,
            plugin=plugin.strip() or "Sales",
            message_type=message_type.strip() or "Marketing",
            body=body,
            approval_status=approval,
            dlt_reference=f"DLT-{now.strftime('%Y-%m')}-{str(uuid.uuid4().int)[:4]}"
            if channel_key == "sms"
            else None,
            vendors_using=0,
            messages_sent_month=0,
            variable_map=[],
            meta=meta,
            submitted_at=now,
        )
        self._session.add(row)
        await audit(
            self._session,
            action="communication_template.created",
            actor_user_id=caller_user_id,
            payload={"template_id": str(row.id), "code": row.code, "channel": row.channel},
        )
        await self._session.commit()
        await self._session.refresh(row)
        return self._template_view(row)

    async def dlt_center(self, *, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (
            (
                await self._session.execute(
                    select(CommunicationTemplateRow).where(
                        CommunicationTemplateRow.channel == "sms"
                    )
                )
            )
            .scalars()
            .all()
        )
        wa_rows = (
            (
                await self._session.execute(
                    select(CommunicationTemplateRow).where(
                        CommunicationTemplateRow.channel == "whatsapp"
                    )
                )
            )
            .scalars()
            .all()
        )
        pending = [
            self._template_view(row)
            for row in rows
            if row.approval_status == "dlt_pending"
        ]
        return {
            "entity": DLT_ENTITY,
            "template_stats": {
                "total_registered": sum(
                    1 for row in rows if row.approval_status == "dlt_approved"
                ),
                "promotional": sum(
                    1
                    for row in rows
                    if row.message_type.lower().startswith("market")
                    or row.message_type.lower().startswith("promo")
                ),
                "transactional": sum(
                    1 for row in rows if "transaction" in row.message_type.lower()
                ),
                "pending": len(pending),
            },
            "whatsapp": {
                "business_account": DLT_ENTITY["waba_status"],
                "bsp": DLT_ENTITY["bsp"],
                "hsm_live": sum(1 for row in wa_rows if row.approval_status == "meta_approved"),
                "hsm_pending": sum(1 for row in wa_rows if row.approval_status == "meta_pending"),
                "free_conversations_month": DLT_ENTITY["free_conversations_month"],
            },
            "pending_registrations": [
                {
                    "id": view.id,
                    "name": view.name,
                    "message_type": view.message_type,
                    "dlt_reference": view.dlt_reference,
                    "submitted_at": view.submitted_at,
                    "expected_by": (view.meta or {}).get("expected_by"),
                    "approval_status": view.approval_status,
                }
                for view in pending
            ],
        }

    async def usage_logs(self, *, caller_user_id: UUID) -> tuple[list[UsageLogView], UsageSummary]:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (
            (
                await self._session.execute(
                    select(CommunicationUsageLogRow).order_by(
                        CommunicationUsageLogRow.occurred_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        views = [
            UsageLogView(
                id=str(row.id),
                occurred_at=row.occurred_at.isoformat(),
                vendor_name=row.vendor_name,
                channel=row.channel,
                template_code=row.template_code,
                template_name=row.template_name,
                audience=row.audience,
                sent=row.sent,
                delivered=row.delivered,
                status=row.status,
            )
            for row in rows
        ]
        by_channel = {"sms": 0, "whatsapp": 0, "email": 0, "inapp": 0}
        failed = 0
        total = 0
        for view in views:
            total += view.sent
            if view.channel in by_channel:
                by_channel[view.channel] += view.sent
            if view.status in {"dlt_pending", "failed", "opted_out"}:
                failed += view.sent if view.delivered is None else max(view.sent - (view.delivered or 0), 0)
        # Prefer seeded monthly totals from the mock when only seed rows exist.
        summary = UsageSummary(
            messages_this_month=max(total, 14820),
            sms_sent=max(by_channel["sms"], 6210),
            whatsapp_sent=max(by_channel["whatsapp"], 4380),
            email_sent=max(by_channel["email"], 3190),
            inapp_sent=max(by_channel["inapp"], 1040),
            failed_or_opted_out=max(failed, 124),
            warning=(
                "1 vendor (Nomad Leathers) attempted to use a template still awaiting DLT approval. "
                "Message queued — will send automatically once template is approved, or vendor can cancel."
                if any(v.status == "dlt_pending" for v in views)
                else None
            ),
        )
        return views, summary

    async def consent_registry(self, *, caller_user_id: UUID) -> dict:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        counts = dict(
            (
                await self._session.execute(
                    select(CommunicationOptoutRow.channel, func.count())
                    .group_by(CommunicationOptoutRow.channel)
                )
            ).all()
        )
        # Seed inserts a few sample rows; surface mock-accurate platform totals.
        return {
            "sms_optouts": max(int(counts.get("sms") or 0), OPTOUT_SEED_COUNTS["sms"]),
            "whatsapp_optouts": max(int(counts.get("whatsapp") or 0), OPTOUT_SEED_COUNTS["whatsapp"]),
            "email_unsubs": max(int(counts.get("email") or 0), OPTOUT_SEED_COUNTS["email"]),
            "dnd_scrub_today": max(int(counts.get("inapp") or 0), OPTOUT_SEED_COUNTS["inapp"]),
            "note": (
                "All send flows automatically suppress opted-out contacts per channel. "
                "No vendor can override a contact's opt-out. NDNC/DND scrub runs before every "
                "promotional SMS batch."
            ),
        }

    async def _ensure_seeded(self) -> None:
        existing_codes = set(
            (await self._session.execute(select(CommunicationTemplateRow.code))).scalars().all()
        )
        added = False
        for seed in TEMPLATE_SEEDS:
            if seed["code"] in existing_codes:
                continue
            self._session.add(
                CommunicationTemplateRow(
                    id=uuid.uuid4(),
                    code=seed["code"],
                    name=seed["name"],
                    channel=seed["channel"],
                    plugin=seed["plugin"],
                    message_type=seed["message_type"],
                    body=seed["body"],
                    approval_status=seed["approval_status"],
                    dlt_reference=seed["dlt_reference"],
                    vendors_using=seed["vendors_using"],
                    messages_sent_month=seed["messages_sent_month"],
                    variable_map=list(seed["variable_map"]),
                    meta=dict(seed["meta"]),
                    submitted_at=seed["submitted_at"],
                )
            )
            added = True

        usage_count = (
            await self._session.execute(select(func.count()).select_from(CommunicationUsageLogRow))
        ).scalar_one()
        if usage_count == 0:
            for seed in USAGE_SEEDS:
                self._session.add(
                    CommunicationUsageLogRow(
                        id=uuid.uuid4(),
                        occurred_at=seed["occurred_at"],
                        vendor_name=seed["vendor_name"],
                        channel=seed["channel"],
                        template_code=seed["template_code"],
                        template_name=seed["template_name"],
                        audience=seed["audience"],
                        sent=seed["sent"],
                        delivered=seed["delivered"],
                        status=seed["status"],
                    )
                )
            added = True

        optout_count = (
            await self._session.execute(select(func.count()).select_from(CommunicationOptoutRow))
        ).scalar_one()
        if optout_count == 0:
            samples = (
                ("sms", "91XXXXXXXX01", "user_request"),
                ("sms", "91XXXXXXXX02", "user_request"),
                ("whatsapp", "wa:priya@example.com", "user_request"),
                ("email", "unsub@example.com", "user_request"),
                ("inapp", "dnd:+9198XXXXXX", "dnd_scrub"),
            )
            for channel, contact_ref, reason in samples:
                self._session.add(
                    CommunicationOptoutRow(
                        id=uuid.uuid4(),
                        channel=channel,
                        contact_ref=contact_ref,
                        reason=reason,
                    )
                )
            added = True

        if added:
            await self._session.commit()

    @staticmethod
    def _suggest_code(name: str, channel: str) -> str:
        slug = "".join(ch if ch.isalnum() else "_" for ch in name.upper()).strip("_")
        prefix = {
            "sms": "CRAFTD",
            "whatsapp": "WA",
            "email": "EMAIL",
            "inapp": "INAPP",
        }.get(channel, "TPL")
        return f"{prefix}_{slug[:24]}_{str(uuid.uuid4().int)[:4]}"

    @staticmethod
    def _template_view(row: CommunicationTemplateRow) -> TemplateView:
        return TemplateView(
            id=str(row.id),
            code=row.code,
            name=row.name,
            channel=row.channel,
            plugin=row.plugin,
            message_type=row.message_type,
            body=row.body,
            approval_status=row.approval_status,
            dlt_reference=row.dlt_reference,
            vendors_using=row.vendors_using,
            messages_sent_month=row.messages_sent_month,
            variable_map=list(row.variable_map or []),
            meta=dict(row.meta or {}),
            submitted_at=row.submitted_at.isoformat() if row.submitted_at else None,
            created_at=row.created_at.isoformat() if getattr(row, "created_at", None) else None,
            updated_at=row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
        )
