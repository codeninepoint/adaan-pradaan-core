"""Platform Admin growth standard plugins: Sales Pipeline, Digital Marketing, Publicity.

These are the built-in Sales & Growth suite from the Platform Admin screenshots.
They are platform-owned configuration records, not vendor fulfilment plugins:
module toggles and limits live here, and every change is audited.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from marketplace.application.access import audit, require_platform_operator
from marketplace.infrastructure.models import GrowthPluginRow
from shared.domain.exceptions import NotFoundError, ValidationError

GROWTH_PLUGIN_KEYS: tuple[str, ...] = ("sales-pipeline", "digital-marketing", "publicity")


def _module(key: str, label: str, description: str, enabled: bool = True, badge: str | None = None) -> dict:
    return {
        "key": key,
        "label": label,
        "description": description,
        "enabled": enabled,
        "badge": badge,
    }


def _stat(key: str, label: str, value: str) -> dict:
    return {"key": key, "label": label, "value": value}


GROWTH_PLUGIN_SEEDS: tuple[dict, ...] = (
    {
        "key": "sales-pipeline",
        "name": "Sales Pipeline",
        "description": "End-to-end lead tracking, deal stages, and revenue forecasting for every vendor.",
        "group_label": "Sales",
        "lifecycle": "live",
        "enabled": True,
        "modules": [
            _module("lead-capture", "Lead Capture & Scoring", "Embeds lead forms, auto-scores by source & engagement"),
            _module("deal-stage-board", "Deal Stage Board", "Kanban view; vendors can customise stage names"),
            _module("revenue-forecasting", "Revenue Forecasting", "ML model on close probability × deal value"),
            _module("follow-up-reminders", "Follow-up Reminders", "Push + email alerts; vendor sets cadence"),
            _module("win-loss-analytics", "Win/Loss Analytics", "Reason tagging, trend charts, export to CSV"),
            _module(
                "crm-export",
                "CRM Export",
                "Push deals to HubSpot / Salesforce via webhook",
                enabled=False,
                badge="Beta",
            ),
        ],
        "config": {
            "max_leads_per_vendor_month": 5000,
            "default_deal_stage_names": "New Lead, Contacted, Proposal Sent, Negotiation, Closed",
            "forecasting_model": "Platform ML (recommended)",
            "crm_webhook_endpoint": "https://hooks.example.com/crm",
            "vendor_can_customise_stages": True,
            "require_deal_value_on_creation": False,
        },
        "stats": {
            "vendors_using": 412,
            "total_vendors": 1418,
            "items": [
                _stat("leads_this_month", "Leads this month", "2,840"),
                _stat("pipeline_value", "Pipeline value", "₹4.2 Cr"),
                _stat("avg_win_rate", "Avg win rate", "34%"),
                _stat("avg_deal_cycle", "Avg deal cycle", "8.4 days"),
            ],
        },
        "guarantees": [
            "Pre-installed for all tenants — no custom code needed",
            "Manifest-declared permissions — sandboxed V8 execution",
            "Module Federation UI — loads as a separate chunk in vendor dashboard",
            "Platform controls enable/disable globally; vendors can toggle modules individually",
            "Versioned releases — admins approve before rollout via Approve Versions screen",
        ],
    },
    {
        "key": "digital-marketing",
        "name": "Digital Marketing",
        "description": "Campaigns, promo codes, listing boosts, deep links, influencers, push and RACE funnel.",
        "group_label": "Marketing",
        "lifecycle": "live",
        "enabled": True,
        "modules": [
            _module("campaigns", "Campaigns (Meta / Google / TikTok)", "OAuth to ad accounts; create & pause from dashboard"),
            _module("promo-codes", "Promo Codes", "Generate flat / % / BOGO codes, set expiry & limits"),
            _module("listing-boosts", "Listing Boosts", "Pay-to-rank within platform search results"),
            _module("deep-links", "Deep Links", "Auto-generate branch.io / Firebase links for SKUs"),
            _module("affiliates-influencers", "Affiliates & Influencers", "Tracking links, tier commissions, payout dashboard"),
            _module("push-notifications", "Push / In-App Notifications", "Segment-targeted push via FCM; opt-out respected"),
            _module("race-funnel-analytics", "RACE Funnel Analytics", "Reach→Act→Convert→Engage chart per campaign"),
        ],
        "config": {
            "daily_spend_cap_inr": 50000,
            "max_promo_codes_per_vendor": 200,
            "allowed_ad_platforms": "Meta + Google + TikTok",
            "require_admin_approval_listing_boosts": False,
            "allow_influencer_self_onboarding": True,
            "export_race_data": False,
        },
        "stats": {
            "vendors_using": 847,
            "total_vendors": 1418,
            "items": [
                _stat("active_campaigns", "Active campaigns", "3,210"),
                _stat("monthly_ad_spend", "Monthly ad spend", "₹8.7 Cr"),
                _stat("avg_ctr", "Avg CTR", "4.2%"),
                _stat("active_promo_codes", "Active promo codes", "1,890"),
            ],
        },
        "guarantees": [
            "Pre-installed, zero vendor setup — plug in ad credentials and go",
            "Platform controls daily spend caps and prevents runaway budgets",
            "Module Federation — each sub-module (Campaigns, Promo, Boosts) loads independently",
            "RACE funnel data stays in platform data lake — no third-party export by default",
            "Versioned — all ad integration updates go through Approve Versions before rollout",
        ],
    },
    {
        "key": "publicity",
        "name": "Publicity",
        "description": "Press releases, media kits, brand story, influencer brief templates, PR analytics.",
        "group_label": "Publicity",
        "lifecycle": "beta",
        "enabled": True,
        "modules": [
            _module("press-release-builder", "Press Release Builder", "AI-assisted template with SEO headline scoring"),
            _module("media-kit-generator", "Media Kit Generator", "Auto-pulls brand assets, stats, team bio into PDF kit"),
            _module("brand-story-editor", "Brand Story Editor", "Long-form narrative editor with tone controls"),
            _module(
                "influencer-brief-templates",
                "Influencer Brief Templates",
                "Structured briefs for UGC, review, unboxing campaigns",
            ),
            _module(
                "pr-mention-tracker",
                "PR Mention Tracker",
                "Web scraping + Google Alerts integration for brand mentions",
                enabled=False,
                badge="Soon",
            ),
        ],
        "config": {
            "ai_generation_tokens_per_vendor_month": 100000,
            "default_press_release_distribution_list": "",
            "media_kit_output_format": "PDF (recommended)",
            "collect_beta_feedback": True,
            "allow_white_label_media_kits": False,
        },
        "stats": {
            "vendors_using": 203,
            "total_vendors": 1418,
            "items": [
                _stat("press_releases", "Press releases", "541"),
                _stat("media_kits", "Media kits", "318"),
                _stat("influencer_briefs", "Influencer briefs", "92"),
                _stat("beta_rating", "Beta rating", "4.6★"),
            ],
        },
        "guarantees": [
            "Pre-installed for all tenants in beta — opt-in required (no silent rollout)",
            "All generated content (press releases, kits) stored in platform media library",
            "AI generation uses platform LLM quota — no vendor API key needed",
            "Beta flag shown on vendor dashboard with feedback prompt after each use",
            "PR Mention Tracker ships in next version — going through Approve Versions now",
        ],
    },
)


@dataclass(frozen=True, slots=True)
class GrowthPluginView:
    key: str
    name: str
    description: str
    group_label: str
    lifecycle: str
    enabled: bool
    modules: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    guarantees: list = field(default_factory=list)
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class GrowthPluginSummary:
    total_plugins: int
    total_modules: int
    enabled_plugins: int
    vendors_using: int


class GrowthPluginService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_plugins(self, *, caller_user_id: UUID) -> tuple[list[GrowthPluginView], GrowthPluginSummary]:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        rows = (await self._session.execute(select(GrowthPluginRow))).scalars().all()
        by_key = {row.key: row for row in rows}
        views = [self._view(by_key[key]) for key in GROWTH_PLUGIN_KEYS if key in by_key]
        summary = GrowthPluginSummary(
            total_plugins=len(views),
            total_modules=sum(len(view.modules) for view in views),
            enabled_plugins=sum(1 for view in views if view.enabled),
            vendors_using=sum(int((view.stats or {}).get("vendors_using") or 0) for view in views),
        )
        return views, summary

    async def update_plugin(
        self,
        *,
        plugin_key: str,
        caller_user_id: UUID,
        enabled: bool | None = None,
        modules: list | None = None,
        config: dict | None = None,
    ) -> GrowthPluginView:
        await require_platform_operator(self._session, caller_user_id)
        await self._ensure_seeded()
        row = await self._session.get(GrowthPluginRow, plugin_key)
        if row is None:
            raise NotFoundError("growth plugin not found")
        seed = next((item for item in GROWTH_PLUGIN_SEEDS if item["key"] == plugin_key), None)
        if modules is not None:
            allowed = {module["key"] for module in (seed["modules"] if seed else [])}
            seen: set[str] = set()
            cleaned: list[dict] = []
            for module in modules:
                if not isinstance(module, dict) or not module.get("key"):
                    raise ValidationError("each module needs a key")
                key = str(module["key"])
                if allowed and key not in allowed:
                    raise ValidationError(f"unknown module: {key}")
                if key in seen:
                    raise ValidationError(f"duplicate module: {key}")
                seen.add(key)
                cleaned.append(
                    {
                        "key": key,
                        "label": str(module.get("label") or key),
                        "description": str(module.get("description") or ""),
                        "enabled": bool(module.get("enabled", True)),
                        "badge": module.get("badge"),
                    }
                )
            row.modules = cleaned
        if config is not None:
            if not isinstance(config, dict):
                raise ValidationError("config must be an object")
            row.config = dict(config)
        if enabled is not None:
            row.enabled = bool(enabled)
        row.updated_at = utcnow()
        await audit(
            self._session,
            action="growth_plugin.updated" if enabled is None else ("growth_plugin.enabled" if enabled else "growth_plugin.disabled"),
            actor_user_id=caller_user_id,
            payload={
                "plugin_key": plugin_key,
                "enabled": row.enabled,
                "module_count": len(row.modules or []),
            },
        )
        await self._session.commit()
        return self._view(row)

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
    def _view(row: GrowthPluginRow) -> GrowthPluginView:
        return GrowthPluginView(
            key=row.key,
            name=row.name,
            description=row.description,
            group_label=row.group_label,
            lifecycle=row.lifecycle,
            enabled=bool(row.enabled),
            modules=list(row.modules or []),
            config=dict(row.config or {}),
            stats=dict(row.stats or {}),
            guarantees=list(row.guarantees or []),
            updated_at=row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
        )
