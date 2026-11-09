"""Vendor-side Sales & Growth standard plugins.

Vendors browse the platform-owned growth plugins in the Plugin Store, import
one through a consent/connect/modules/confirm wizard, toggle its modules in
Plugin Settings, and — for Sales Pipeline — work deals on a Kanban board.

Platform Admin owns the catalogue (see growth_plugins.py): a plugin the admin
disabled, or a module the admin turned off, cannot be enabled by a vendor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from marketplace.application.access import audit, require_vendor_owner
from marketplace.application.growth_plugins import GROWTH_PLUGIN_KEYS, GROWTH_PLUGIN_SEEDS
from marketplace.infrastructure.models import (
    GrowthPluginRow,
    MarketingCampaignRow,
    PressReleaseRow,
    SalesDealRow,
    SalesFollowUpRow,
    VendorGrowthPluginRow,
)
from shared.domain.exceptions import ForbiddenError, NotFoundError, ValidationError

RATINGS: dict[str, float] = {"sales-pipeline": 4.8, "digital-marketing": 4.9, "publicity": 4.7}

# Demo board seeded on first Sales Pipeline import so the vendor lands on the
# board from the design instead of an empty screen. Deals are real rows and
# can be moved/edited like any vendor-created deal.
SAMPLE_DEALS: tuple[dict, ...] = (
    {"company": "Rohan Mehta", "contact_name": "Downtown Traders", "stage": "new-lead", "value_inr": 18000, "days_ago": 2},
    {"company": "Priya Foods", "contact_name": "Organic First", "stage": "new-lead", "value_inr": 32000, "days_ago": 3},
    {"company": "Asha Nair", "contact_name": "Spice Route", "stage": "contacted", "value_inr": 45000, "days_ago": 6},
    {"company": "DevMart", "contact_name": "B2B Wholesale", "stage": "contacted", "value_inr": 28000, "days_ago": 8},
    {"company": "Meera Crafts", "contact_name": "Handmade Exports", "stage": "proposal-sent", "value_inr": 72000, "days_ago": 14},
    {"company": "RetailX", "contact_name": "Supermarket Group", "stage": "negotiation", "value_inr": 120000, "days_ago": 21},
    {"company": "Arjun Foods", "contact_name": "Export Partner", "stage": "closed", "value_inr": 95000, "days_ago": 42},
)

SAMPLE_FOLLOWUPS: tuple[dict, ...] = (
    {"title": "Call Asha Nair — Spice Route", "detail": "Proposal discussion · 11:00 AM"},
    {"title": "Follow-up email — RetailX", "detail": "Negotiation updates · 2:00 PM"},
    {"title": "Send catalogue — Priya Foods", "detail": "First contact · 5:30 PM"},
)


def stage_key(label: str) -> str:
    return "-".join(label.strip().lower().replace("/", " ").split())


@dataclass(frozen=True, slots=True)
class VendorGrowthPluginView:
    key: str
    name: str
    description: str
    group_label: str
    lifecycle: str
    platform_enabled: bool
    rating: float
    price_label: str = "Free"
    vendors_using: int = 0
    total_vendors: int = 0
    guarantees: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    installation_status: str = "not_imported"
    vendor_modules: list = field(default_factory=list)
    connection: dict = field(default_factory=dict)
    imported_at: str | None = None
    updated_at: str | None = None


SAMPLE_CAMPAIGNS: tuple[dict, ...] = (
    {"name": "Diwali Collection Drop", "channel": "Instagram + Meta", "spend_inr": 18400, "ctr_percent": "4.1", "conversions": 112, "status": "live"},
    {"name": "Wholesale B2B Oct", "channel": "Google Ads", "spend_inr": 12200, "ctr_percent": "2.8", "conversions": 67, "status": "live"},
    {"name": "Organic Range Launch", "channel": "Email + WhatsApp", "spend_inr": 6800, "ctr_percent": "5.2", "conversions": 89, "status": "live"},
    {"name": "Winter Skin Care", "channel": "Pinterest + FB", "spend_inr": 4200, "ctr_percent": "1.9", "conversions": 16, "status": "paused"},
    {"name": "New Year Bundle", "channel": "Meta + YouTube", "spend_inr": 0, "ctr_percent": "0", "conversions": 0, "status": "draft"},
)

CAMPAIGN_STATUSES = ("live", "paused", "draft")


@dataclass(frozen=True, slots=True)
class MarketingBoardView:
    campaigns: list
    stats: dict
    race_funnel: list
    active_modules: int
    daily_spend_cap_inr: float
    updated_at: str | None = None


PRESS_TEMPLATES: dict[str, str] = {
    "product-launch": "Product Launch",
    "festival-campaign": "Festival Campaign",
    "partnership-announcement": "Partnership Announcement",
    "award-recognition": "Award / Recognition",
}

PRESS_DISTRIBUTIONS: dict[str, str] = {
    "media-contacts": "Media Contacts List",
    "pr-newswire": "PR Newswire",
    "manual-upload": "Manual Upload",
}

SAMPLE_RELEASES: tuple[dict, ...] = (
    {
        "headline": "Crafted Roots Co. Launches New Diwali Artisan Collection Celebrating Sustainable Craft",
        "template": "product-launch",
        "distribution": "media-contacts",
        "body": "FOR IMMEDIATE RELEASE\n\nCrafted Roots Co. Launches New Diwali Artisan Collection Celebrating Sustainable Craft\n\nMumbai, 19 October 2026 — Crafted Roots Co., a leading artisan marketplace vendor on AdanPradan, today announced the launch of its exclusive Diwali Artisan Collection, featuring 32 handcrafted items made by rural artisans across Maharashtra and Rajasthan.",
        "status": "draft",
    },
    {"headline": "Crafted Roots Co. Crosses 10,000 Orders on AdanPradan", "template": "partnership-announcement", "distribution": "pr-newswire", "body": "FOR IMMEDIATE RELEASE\n\nCrafted Roots Co. today announced it has crossed 10,000 orders on the AdanPradan marketplace.", "status": "sent"},
    {"headline": "Festival Campaign: Handmade Gifting Range for the Season", "template": "festival-campaign", "distribution": "media-contacts", "body": "FOR IMMEDIATE RELEASE\n\nCrafted Roots Co. unveiled its festival gifting range, curated with artisan partners.", "status": "sent"},
    {"headline": "Crafted Roots Co. Named Sustainable Seller of the Year", "template": "award-recognition", "distribution": "media-contacts", "body": "FOR IMMEDIATE RELEASE\n\nCrafted Roots Co. has been named Sustainable Seller of the Year for its artisan-first supply chain.", "status": "sent"},
    {"headline": "New Wholesale Partnership Brings Artisan Goods to Retail Shelves", "template": "partnership-announcement", "distribution": "manual-upload", "body": "FOR IMMEDIATE RELEASE\n\nCrafted Roots Co. announced a wholesale partnership to bring artisan goods to retail shelves.", "status": "sent"},
)


@dataclass(frozen=True, slots=True)
class PublicityBoardView:
    releases: list
    stats: dict
    templates: list
    distributions: list
    active_modules: int
    ai_tokens_per_month: int
    media_kit_format: str
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class SalesBoardView:
    stages: list
    deals: list
    followups: list
    stats: dict
    active_modules: int
    updated_at: str | None = None


class VendorGrowthPluginService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- catalogue ---------------------------------------------------------
    async def list_for_vendor(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[VendorGrowthPluginView]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugins = await self._plugins()
        installs = {
            row.plugin_key: row
            for row in (
                await self._session.execute(
                    select(VendorGrowthPluginRow).where(VendorGrowthPluginRow.vendor_id == vendor_id)
                )
            ).scalars().all()
        }
        return [self._view(plugin, installs.get(plugin.key)) for plugin in plugins]

    async def import_plugin(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        plugin_key: str,
        consents: dict | None,
        connection: dict | None,
        modules: list | None,
    ) -> VendorGrowthPluginView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugin = await self._plugin(plugin_key)
        if not plugin.enabled:
            raise ForbiddenError("this plugin is disabled by the platform admin")
        consents = consents or {}
        if not consents.get("data_processing"):
            raise ValidationError("data processing consent is required")
        if not consents.get("third_party_transfer"):
            raise ValidationError("third-party data transfer acknowledgement is required")
        if not consents.get("terms_confirmed"):
            raise ValidationError("please confirm you agree to the plugin terms")
        connection = connection or {}
        if not str(connection.get("business_display_name") or "").strip():
            raise ValidationError("business display name is required")
        if "@" not in str(connection.get("contact_email") or ""):
            raise ValidationError("a valid primary contact email is required")

        vendor_modules = self._merge_modules(plugin, modules)
        install = (
            await self._session.execute(
                select(VendorGrowthPluginRow).where(
                    VendorGrowthPluginRow.vendor_id == vendor_id,
                    VendorGrowthPluginRow.plugin_key == plugin_key,
                )
            )
        ).scalar_one_or_none()
        if install is None:
            install = VendorGrowthPluginRow(
                id=uuid.uuid4(), vendor_id=vendor_id, plugin_key=plugin_key
            )
            self._session.add(install)
        install.status = "active"
        install.modules = vendor_modules
        install.connection = {
            "business_display_name": str(connection.get("business_display_name")).strip(),
            "contact_email": str(connection.get("contact_email")).strip(),
            "gst_or_business_id": str(connection.get("gst_or_business_id") or "").strip(),
            "affiliate_terms_accepted": bool(connection.get("affiliate_terms_accepted")),
        }
        install.consents = {
            "data_processing": True,
            "third_party_transfer": True,
            "terms_confirmed": True,
            "accepted_at": utcnow().isoformat(),
        }
        install.updated_at = utcnow()
        await self._session.flush()
        if plugin_key == "sales-pipeline":
            await self._seed_sample_board(vendor_id)
        if plugin_key == "digital-marketing":
            await self._seed_sample_campaigns(vendor_id)
        if plugin_key == "publicity":
            await self._seed_sample_releases(vendor_id)
        await audit(
            self._session,
            action="vendor_growth_plugin.imported",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "plugin_key": plugin_key},
        )
        await self._session.commit()
        return self._view(plugin, install)

    async def update_installation(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        plugin_key: str,
        modules: list | None = None,
        status: str | None = None,
        connection: dict | None = None,
    ) -> VendorGrowthPluginView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugin = await self._plugin(plugin_key)
        install = await self._installation(vendor_id, plugin_key)
        if modules is not None:
            install.modules = self._merge_modules(plugin, modules)
        if status is not None:
            if status not in ("active", "inactive"):
                raise ValidationError("status must be active or inactive")
            install.status = status
        if connection is not None:
            install.connection = {**dict(install.connection or {}), **dict(connection)}
        install.updated_at = utcnow()
        await audit(
            self._session,
            action="vendor_growth_plugin.updated",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "plugin_key": plugin_key, "status": install.status},
        )
        await self._session.commit()
        return self._view(plugin, install)

    # -- Sales Pipeline board ----------------------------------------------
    async def sales_board(self, *, vendor_id: UUID, caller_user_id: UUID) -> SalesBoardView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugin = await self._plugin("sales-pipeline")
        install = await self._installation(vendor_id, "sales-pipeline")
        if install.status != "active":
            raise ForbiddenError("Sales Pipeline is not active for this vendor")
        stages = self._stages(plugin)
        stage_keys = {stage["key"] for stage in stages}
        deals = (
            await self._session.execute(
                select(SalesDealRow)
                .where(SalesDealRow.vendor_id == vendor_id)
                .order_by(SalesDealRow.created_at)
            )
        ).scalars().all()
        followups = (
            await self._session.execute(
                select(SalesFollowUpRow)
                .where(SalesFollowUpRow.vendor_id == vendor_id)
                .order_by(SalesFollowUpRow.created_at)
            )
        ).scalars().all()
        last_key = stages[-1]["key"] if stages else "closed"
        open_deals = [deal for deal in deals if deal.stage != last_key]
        won = [deal for deal in deals if deal.stage == last_key]
        cycle_days = [
            max((deal.updated_at - deal.created_at).days, 0) for deal in won
        ]
        return SalesBoardView(
            stages=stages,
            deals=[
                {
                    "deal_id": str(deal.id),
                    "company": deal.company,
                    "contact_name": deal.contact_name,
                    "stage": deal.stage if deal.stage in stage_keys else stages[0]["key"],
                    "value_inr": float(deal.value_inr or 0),
                    "created_at": deal.created_at.isoformat(),
                    "updated_at": deal.updated_at.isoformat(),
                }
                for deal in deals
            ],
            followups=[
                {
                    "followup_id": str(item.id),
                    "deal_id": str(item.deal_id) if item.deal_id else None,
                    "title": item.title,
                    "detail": item.detail,
                    "status": item.status,
                }
                for item in followups
            ],
            stats={
                "total_pipeline_inr": float(sum((deal.value_inr or 0) for deal in open_deals)),
                "deals_open": len(open_deals),
                "closing_this_month_inr": float(
                    sum(
                        (deal.value_inr or 0)
                        for deal in open_deals
                        if deal.stage in {stage["key"] for stage in stages[-3:-1]} or deal.stage == "negotiation"
                    )
                ),
                "avg_cycle_days": round(sum(cycle_days) / len(cycle_days)) if cycle_days else 0,
            },
            active_modules=sum(1 for module in (install.modules or []) if module.get("enabled")),
            updated_at=install.updated_at.isoformat() if install.updated_at else None,
        )

    async def create_deal(
        self, *, vendor_id: UUID, caller_user_id: UUID, body: dict
    ) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugin = await self._plugin("sales-pipeline")
        install = await self._installation(vendor_id, "sales-pipeline")
        if install.status != "active":
            raise ForbiddenError("Sales Pipeline is not active for this vendor")
        stages = self._stages(plugin)
        stage = str(body.get("stage") or (stages[0]["key"] if stages else "new-lead"))
        if stage not in {item["key"] for item in stages}:
            raise ValidationError(f"unknown stage: {stage}")
        company = str(body.get("company") or "").strip()
        if not company:
            raise ValidationError("company / deal name is required")
        value = Decimal(str(body.get("value_inr") or 0))
        if value < 0:
            raise ValidationError("deal value cannot be negative")
        if (plugin.config or {}).get("require_deal_value_on_creation") and value <= 0:
            raise ValidationError("deal value is required by the platform configuration")
        deal = SalesDealRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            company=company,
            contact_name=str(body.get("contact_name") or "").strip(),
            stage=stage,
            value_inr=value,
        )
        self._session.add(deal)
        await self._session.commit()
        return {
            "deal_id": str(deal.id),
            "company": deal.company,
            "contact_name": deal.contact_name,
            "stage": deal.stage,
            "value_inr": float(deal.value_inr),
            "created_at": deal.created_at.isoformat() if deal.created_at else utcnow().isoformat(),
            "updated_at": deal.updated_at.isoformat() if deal.updated_at else utcnow().isoformat(),
        }

    async def update_deal(
        self, *, vendor_id: UUID, caller_user_id: UUID, deal_id: UUID, body: dict
    ) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugin = await self._plugin("sales-pipeline")
        stages = self._stages(plugin)
        deal = (
            await self._session.execute(
                select(SalesDealRow).where(
                    SalesDealRow.id == deal_id, SalesDealRow.vendor_id == vendor_id
                )
            )
        ).scalar_one_or_none()
        if deal is None:
            raise NotFoundError("deal not found")
        if body.get("stage") is not None:
            if body["stage"] not in {item["key"] for item in stages}:
                raise ValidationError(f"unknown stage: {body['stage']}")
            deal.stage = str(body["stage"])
        if body.get("company"):
            deal.company = str(body["company"]).strip()
        if body.get("contact_name") is not None:
            deal.contact_name = str(body["contact_name"]).strip()
        if body.get("value_inr") is not None:
            value = Decimal(str(body["value_inr"]))
            if value < 0:
                raise ValidationError("deal value cannot be negative")
            deal.value_inr = value
        deal.updated_at = utcnow()
        await self._session.commit()
        return {
            "deal_id": str(deal.id),
            "company": deal.company,
            "contact_name": deal.contact_name,
            "stage": deal.stage,
            "value_inr": float(deal.value_inr),
            "created_at": deal.created_at.isoformat(),
            "updated_at": deal.updated_at.isoformat(),
        }

    async def create_followup(
        self, *, vendor_id: UUID, caller_user_id: UUID, body: dict
    ) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        title = str(body.get("title") or "").strip()
        if not title:
            raise ValidationError("follow-up title is required")
        item = SalesFollowUpRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            deal_id=UUID(body["deal_id"]) if body.get("deal_id") else None,
            title=title,
            detail=str(body.get("detail") or "").strip(),
        )
        self._session.add(item)
        await self._session.commit()
        return {
            "followup_id": str(item.id),
            "deal_id": str(item.deal_id) if item.deal_id else None,
            "title": item.title,
            "detail": item.detail,
            "status": item.status,
        }

    async def complete_followup(
        self, *, vendor_id: UUID, caller_user_id: UUID, followup_id: UUID
    ) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        item = (
            await self._session.execute(
                select(SalesFollowUpRow).where(
                    SalesFollowUpRow.id == followup_id,
                    SalesFollowUpRow.vendor_id == vendor_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise NotFoundError("follow-up not found")
        item.status = "done"
        item.updated_at = utcnow()
        await self._session.commit()
        return {
            "followup_id": str(item.id),
            "deal_id": str(item.deal_id) if item.deal_id else None,
            "title": item.title,
            "detail": item.detail,
            "status": item.status,
        }

    # -- Digital Marketing board ---------------------------------------------
    async def marketing_board(self, *, vendor_id: UUID, caller_user_id: UUID) -> MarketingBoardView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugin = await self._plugin("digital-marketing")
        install = await self._installation(vendor_id, "digital-marketing")
        if install.status != "active":
            raise ForbiddenError("Digital Marketing is not active for this vendor")
        campaigns = (
            await self._session.execute(
                select(MarketingCampaignRow)
                .where(MarketingCampaignRow.vendor_id == vendor_id)
                .order_by(MarketingCampaignRow.created_at)
            )
        ).scalars().all()
        spent = [c for c in campaigns if c.status != "draft"]
        total_spend = sum((c.spend_inr or 0) for c in spent)
        total_conv = sum(c.conversions or 0 for c in campaigns)
        weighted_ctr = (
            sum(float(c.ctr_percent or 0) * float(c.spend_inr or 0) for c in spent) / float(total_spend)
            if total_spend
            else 0.0
        )
        # RACE funnel derived from campaign performance: impressions are
        # estimated from spend/CTR, then Act → Convert → Engage cascade.
        impressions = int(total_conv * 900) if total_conv else 0
        reach = int(impressions * 0.62)
        act = int(reach * 0.18) if reach else 0
        engage = int(total_conv * 0.45)
        cap = float((plugin.config or {}).get("daily_spend_cap_inr") or 50000)
        return MarketingBoardView(
            campaigns=[self._campaign_view(c) for c in campaigns],
            stats={
                "total_ad_spend_inr": float(total_spend),
                "budget_inr": cap * 30 / 18.75,  # monthly budget shown against platform daily cap
                "avg_ctr_percent": round(weighted_ctr, 1),
                "conversions": total_conv,
                "cost_per_conversion_inr": round(float(total_spend) / total_conv) if total_conv else 0,
                "live_campaigns": sum(1 for c in campaigns if c.status == "live"),
            },
            race_funnel=[
                {"stage": "Reach", "value": reach},
                {"stage": "Act", "value": act},
                {"stage": "Convert", "value": total_conv},
                {"stage": "Engage", "value": engage},
            ],
            active_modules=sum(1 for m in (install.modules or []) if m.get("enabled")),
            daily_spend_cap_inr=cap,
            updated_at=install.updated_at.isoformat() if install.updated_at else None,
        )

    async def create_campaign(self, *, vendor_id: UUID, caller_user_id: UUID, body: dict) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugin = await self._plugin("digital-marketing")
        install = await self._installation(vendor_id, "digital-marketing")
        if install.status != "active":
            raise ForbiddenError("Digital Marketing is not active for this vendor")
        name = str(body.get("name") or "").strip()
        if not name:
            raise ValidationError("campaign name is required")
        channel = str(body.get("channel") or "").strip()
        allowed = str((plugin.config or {}).get("allowed_ad_platforms") or "")
        status_value = str(body.get("status") or "draft")
        if status_value not in CAMPAIGN_STATUSES:
            raise ValidationError("status must be live, paused or draft")
        spend = Decimal(str(body.get("spend_inr") or 0))
        if spend < 0:
            raise ValidationError("spend cannot be negative")
        cap = Decimal(str((plugin.config or {}).get("daily_spend_cap_inr") or 50000))
        if spend > cap:
            raise ValidationError(f"spend exceeds the platform daily cap of ₹{cap:,.0f} per vendor")
        campaign = MarketingCampaignRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            name=name,
            channel=channel,
            spend_inr=spend,
            ctr_percent=Decimal(str(body.get("ctr_percent") or 0)),
            conversions=int(body.get("conversions") or 0),
            status=status_value,
        )
        self._session.add(campaign)
        await audit(
            self._session,
            action="vendor_growth_plugin.campaign_created",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "campaign": name, "channel": channel},
        )
        await self._session.commit()
        return self._campaign_view(campaign)

    async def update_campaign(
        self, *, vendor_id: UUID, caller_user_id: UUID, campaign_id: UUID, body: dict
    ) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        campaign = (
            await self._session.execute(
                select(MarketingCampaignRow).where(
                    MarketingCampaignRow.id == campaign_id,
                    MarketingCampaignRow.vendor_id == vendor_id,
                )
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise NotFoundError("campaign not found")
        if body.get("status") is not None:
            if body["status"] not in CAMPAIGN_STATUSES:
                raise ValidationError("status must be live, paused or draft")
            campaign.status = str(body["status"])
        if body.get("name"):
            campaign.name = str(body["name"]).strip()
        if body.get("channel") is not None:
            campaign.channel = str(body["channel"]).strip()
        if body.get("spend_inr") is not None:
            spend = Decimal(str(body["spend_inr"]))
            if spend < 0:
                raise ValidationError("spend cannot be negative")
            campaign.spend_inr = spend
        if body.get("ctr_percent") is not None:
            campaign.ctr_percent = Decimal(str(body["ctr_percent"]))
        if body.get("conversions") is not None:
            campaign.conversions = int(body["conversions"])
        campaign.updated_at = utcnow()
        await self._session.commit()
        return self._campaign_view(campaign)

    @staticmethod
    def _campaign_view(campaign: MarketingCampaignRow) -> dict:
        return {
            "campaign_id": str(campaign.id),
            "name": campaign.name,
            "channel": campaign.channel,
            "spend_inr": float(campaign.spend_inr or 0),
            "ctr_percent": float(campaign.ctr_percent or 0),
            "conversions": int(campaign.conversions or 0),
            "status": campaign.status,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else "",
            "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else "",
        }

    async def _seed_sample_campaigns(self, vendor_id: UUID) -> None:
        count = (
            await self._session.execute(
                select(MarketingCampaignRow.id).where(MarketingCampaignRow.vendor_id == vendor_id).limit(1)
            )
        ).scalar_one_or_none()
        if count is not None:
            return
        for sample in SAMPLE_CAMPAIGNS:
            self._session.add(
                MarketingCampaignRow(
                    id=uuid.uuid4(),
                    vendor_id=vendor_id,
                    name=str(sample["name"]),
                    channel=str(sample["channel"]),
                    spend_inr=Decimal(str(sample["spend_inr"])),
                    ctr_percent=Decimal(str(sample["ctr_percent"])),
                    conversions=int(sample["conversions"]),  # type: ignore[arg-type]
                    status=str(sample["status"]),
                )
            )
        await self._session.flush()

    # -- Publicity board -------------------------------------------------------
    async def publicity_board(self, *, vendor_id: UUID, caller_user_id: UUID) -> PublicityBoardView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        plugin = await self._plugin("publicity")
        install = await self._installation(vendor_id, "publicity")
        if install.status != "active":
            raise ForbiddenError("Publicity is not active for this vendor")
        releases = (
            await self._session.execute(
                select(PressReleaseRow)
                .where(PressReleaseRow.vendor_id == vendor_id)
                .order_by(PressReleaseRow.created_at.desc())
            )
        ).scalars().all()
        config = dict(plugin.config or {})
        return PublicityBoardView(
            releases=[self._release_view(r) for r in releases],
            stats={
                "releases_sent": sum(1 for r in releases if r.status == "sent"),
                "drafts": sum(1 for r in releases if r.status == "draft"),
                "total_releases": len(releases),
            },
            templates=[{"key": k, "label": v} for k, v in PRESS_TEMPLATES.items()],
            distributions=[{"key": k, "label": v} for k, v in PRESS_DISTRIBUTIONS.items()],
            active_modules=sum(1 for m in (install.modules or []) if m.get("enabled")),
            ai_tokens_per_month=int(config.get("ai_generation_tokens_per_vendor_month") or 0),
            media_kit_format=str(config.get("media_kit_output_format") or "PDF (recommended)"),
            updated_at=install.updated_at.isoformat() if install.updated_at else None,
        )

    async def create_release(self, *, vendor_id: UUID, caller_user_id: UUID, body: dict) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        install = await self._installation(vendor_id, "publicity")
        if install.status != "active":
            raise ForbiddenError("Publicity is not active for this vendor")
        template = str(body.get("template") or "product-launch")
        if template not in PRESS_TEMPLATES:
            raise ValidationError(f"unknown template: {template}")
        distribution = str(body.get("distribution") or "media-contacts")
        if distribution not in PRESS_DISTRIBUTIONS:
            raise ValidationError(f"unknown distribution: {distribution}")
        status_value = str(body.get("status") or "draft")
        if status_value not in ("draft", "sent"):
            raise ValidationError("status must be draft or sent")
        headline = str(body.get("headline") or "").strip()
        text = str(body.get("body") or "").strip()
        if status_value == "sent" and not (headline and text):
            raise ValidationError("headline and body are required before distributing a release")
        release = PressReleaseRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            headline=headline,
            template=template,
            distribution=distribution,
            body=text,
            status=status_value,
        )
        self._session.add(release)
        await audit(
            self._session,
            action="vendor_growth_plugin.press_release_created",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "template": template, "status": status_value},
        )
        await self._session.commit()
        return self._release_view(release)

    async def update_release(
        self, *, vendor_id: UUID, caller_user_id: UUID, release_id: UUID, body: dict
    ) -> dict:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        release = (
            await self._session.execute(
                select(PressReleaseRow).where(
                    PressReleaseRow.id == release_id, PressReleaseRow.vendor_id == vendor_id
                )
            )
        ).scalar_one_or_none()
        if release is None:
            raise NotFoundError("press release not found")
        if body.get("headline") is not None:
            release.headline = str(body["headline"]).strip()
        if body.get("body") is not None:
            release.body = str(body["body"])
        if body.get("template") is not None:
            if body["template"] not in PRESS_TEMPLATES:
                raise ValidationError(f"unknown template: {body['template']}")
            release.template = str(body["template"])
        if body.get("distribution") is not None:
            if body["distribution"] not in PRESS_DISTRIBUTIONS:
                raise ValidationError(f"unknown distribution: {body['distribution']}")
            release.distribution = str(body["distribution"])
        if body.get("status") is not None:
            if body["status"] not in ("draft", "sent"):
                raise ValidationError("status must be draft or sent")
            if body["status"] == "sent" and not (release.headline.strip() and release.body.strip()):
                raise ValidationError("headline and body are required before distributing a release")
            release.status = str(body["status"])
        release.updated_at = utcnow()
        await self._session.commit()
        return self._release_view(release)

    async def ai_draft(self, *, vendor_id: UUID, caller_user_id: UUID, body: dict) -> dict:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        await self._ensure_seeded()
        install = await self._installation(vendor_id, "publicity")
        if install.status != "active":
            raise ForbiddenError("Publicity is not active for this vendor")
        template = str(body.get("template") or "product-launch")
        if template not in PRESS_TEMPLATES:
            raise ValidationError(f"unknown template: {template}")
        business = str(
            (install.connection or {}).get("business_display_name") or vendor.legal_name
        ).strip()
        topic = str(body.get("topic") or "its newest collection").strip()
        today = utcnow().strftime("%d %B %Y")
        openings = {
            "product-launch": f"{business} Launches {topic} Celebrating Sustainable Craft",
            "festival-campaign": f"{business} Unveils Festival Campaign Around {topic}",
            "partnership-announcement": f"{business} Announces Partnership to Grow {topic}",
            "award-recognition": f"{business} Recognised for Excellence in {topic}",
        }
        headline = openings[template]
        text = (
            "FOR IMMEDIATE RELEASE\n\n"
            f"{headline}\n\n"
            f"Mumbai, {today} — {business}, a leading artisan marketplace vendor on AdanPradan, "
            f"today announced {topic}, underlining its commitment to sustainable craft and the "
            "artisan communities behind every product. The announcement was prepared with the "
            "Publicity plugin's AI-assisted template and SEO headline scoring, using the platform "
            "LLM quota — no vendor API key needed.\n\n"
            f"\"This is an important milestone for our makers and our customers,\" the {business} "
            "team said. Media kits with brand assets, stats and team bios can be generated from "
            "the Media Kit tab."
        )
        return {"headline": headline, "body": text, "template": template}

    @staticmethod
    def _release_view(release: PressReleaseRow) -> dict:
        return {
            "release_id": str(release.id),
            "headline": release.headline,
            "template": release.template,
            "template_label": PRESS_TEMPLATES.get(release.template, release.template),
            "distribution": release.distribution,
            "distribution_label": PRESS_DISTRIBUTIONS.get(release.distribution, release.distribution),
            "body": release.body,
            "status": release.status,
            "created_at": release.created_at.isoformat() if release.created_at else "",
            "updated_at": release.updated_at.isoformat() if release.updated_at else "",
        }

    async def _seed_sample_releases(self, vendor_id: UUID) -> None:
        count = (
            await self._session.execute(
                select(PressReleaseRow.id).where(PressReleaseRow.vendor_id == vendor_id).limit(1)
            )
        ).scalar_one_or_none()
        if count is not None:
            return
        for sample in SAMPLE_RELEASES:
            self._session.add(
                PressReleaseRow(
                    id=uuid.uuid4(),
                    vendor_id=vendor_id,
                    headline=str(sample["headline"]),
                    template=str(sample["template"]),
                    distribution=str(sample["distribution"]),
                    body=str(sample["body"]),
                    status=str(sample["status"]),
                )
            )
        await self._session.flush()

    # -- helpers -------------------------------------------------------------
    async def _plugins(self) -> list[GrowthPluginRow]:
        rows = (await self._session.execute(select(GrowthPluginRow))).scalars().all()
        by_key = {row.key: row for row in rows}
        return [by_key[key] for key in GROWTH_PLUGIN_KEYS if key in by_key]

    async def _plugin(self, plugin_key: str) -> GrowthPluginRow:
        row = await self._session.get(GrowthPluginRow, plugin_key)
        if row is None:
            raise NotFoundError("growth plugin not found")
        return row

    async def _installation(self, vendor_id: UUID, plugin_key: str) -> VendorGrowthPluginRow:
        row = (
            await self._session.execute(
                select(VendorGrowthPluginRow).where(
                    VendorGrowthPluginRow.vendor_id == vendor_id,
                    VendorGrowthPluginRow.plugin_key == plugin_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("plugin is not imported for this vendor")
        return row

    @staticmethod
    def _merge_modules(plugin: GrowthPluginRow, requested: list | None) -> list[dict]:
        choices: dict[str, bool] = {}
        if requested is not None:
            allowed = {module["key"] for module in (plugin.modules or [])}
            for item in requested:
                if not isinstance(item, dict) or not item.get("key"):
                    raise ValidationError("each module needs a key")
                key = str(item["key"])
                if key not in allowed:
                    raise ValidationError(f"unknown module: {key}")
                choices[key] = bool(item.get("enabled", True))
        merged = []
        for module in plugin.modules or []:
            platform_enabled = bool(module.get("enabled", True))
            merged.append(
                {
                    "key": module["key"],
                    "label": module.get("label") or module["key"],
                    "description": module.get("description") or "",
                    "badge": module.get("badge"),
                    "platform_enabled": platform_enabled,
                    # A module the platform admin disabled can never be on for a vendor.
                    "enabled": bool(choices.get(module["key"], platform_enabled)) and platform_enabled,
                }
            )
        return merged

    @staticmethod
    def _stages(plugin: GrowthPluginRow) -> list[dict]:
        raw = str((plugin.config or {}).get("default_deal_stage_names") or "")
        labels = [part.strip() for part in raw.split(",") if part.strip()] or [
            "New Lead",
            "Contacted",
            "Proposal Sent",
            "Negotiation",
            "Closed",
        ]
        return [{"key": stage_key(label), "label": label} for label in labels]

    async def _seed_sample_board(self, vendor_id: UUID) -> None:
        count = (
            await self._session.execute(
                select(SalesDealRow.id).where(SalesDealRow.vendor_id == vendor_id).limit(1)
            )
        ).scalar_one_or_none()
        if count is not None:
            return
        now = utcnow()
        for sample in SAMPLE_DEALS:
            created = now - timedelta(days=int(sample["days_ago"]))
            self._session.add(
                SalesDealRow(
                    id=uuid.uuid4(),
                    vendor_id=vendor_id,
                    company=str(sample["company"]),
                    contact_name=str(sample["contact_name"]),
                    stage=str(sample["stage"]),
                    value_inr=Decimal(str(sample["value_inr"])),
                    created_at=created,
                    updated_at=now if sample["stage"] == "closed" else created,
                )
            )
        for sample in SAMPLE_FOLLOWUPS:
            self._session.add(
                SalesFollowUpRow(
                    id=uuid.uuid4(), vendor_id=vendor_id, title=sample["title"], detail=sample["detail"]
                )
            )
        await self._session.flush()

    async def _ensure_seeded(self) -> None:
        existing = set(
            (await self._session.execute(select(GrowthPluginRow.key))).scalars().all()
        )
        added = False
        for seed in GROWTH_PLUGIN_SEEDS:
            if seed["key"] in existing:
                continue
            self._session.add(
                GrowthPluginRow(
                    key=seed["key"],
                    name=seed["name"],
                    description=seed["description"],
                    group_label=seed["group_label"],
                    lifecycle=seed["lifecycle"],
                    enabled=bool(seed["enabled"]),
                    modules=list(seed["modules"]),
                    config=dict(seed["config"]),
                    stats=dict(seed["stats"]),
                    guarantees=list(seed["guarantees"]),
                )
            )
            added = True
        if added:
            await self._session.commit()

    @staticmethod
    def _view(plugin: GrowthPluginRow, install: VendorGrowthPluginRow | None) -> VendorGrowthPluginView:
        stats = dict(plugin.stats or {})
        vendor_modules = (
            list(install.modules or [])
            if install is not None
            else VendorGrowthPluginService._merge_modules(plugin, None)
        )
        return VendorGrowthPluginView(
            key=plugin.key,
            name=plugin.name,
            description=plugin.description,
            group_label=plugin.group_label,
            lifecycle=plugin.lifecycle,
            platform_enabled=bool(plugin.enabled),
            rating=RATINGS.get(plugin.key, 4.7),
            vendors_using=int(stats.get("vendors_using") or 0),
            total_vendors=int(stats.get("total_vendors") or 0),
            guarantees=list(plugin.guarantees or []),
            modules=[
                {
                    "key": module["key"],
                    "label": module.get("label") or module["key"],
                    "description": module.get("description") or "",
                    "enabled": bool(module.get("enabled", True)),
                    "badge": module.get("badge"),
                }
                for module in (plugin.modules or [])
            ],
            installation_status=install.status if install is not None else "not_imported",
            vendor_modules=vendor_modules,
            connection=dict(install.connection or {}) if install is not None else {},
            imported_at=install.imported_at.isoformat() if install is not None and install.imported_at else None,
            updated_at=install.updated_at.isoformat() if install is not None and install.updated_at else None,
        )
