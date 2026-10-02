from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from marketplace.application.access import audit, require_platform_operator, require_vendor_owner
from marketplace.infrastructure.models import (
    InstallationRow,
    OfferingRow,
    PluginCapabilityRow,
    PluginRow,
    PluginVersionRow,
    ProductRow,
)
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shared.infrastructure.models import OutboxEventRow
from vendor.infrastructure.models import VendorProfileRow

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class PortalSummary:
    vendor_id: UUID
    status: str
    product_count: int
    offering_count: int
    active_installs: int
    pending_plugin_reviews: int


@dataclass(frozen=True, slots=True)
class PluginCreated:
    plugin_id: UUID
    slug: str
    status: str
    vendor_id: UUID


@dataclass(frozen=True, slots=True)
class PluginListItem:
    plugin_id: UUID
    name: str
    slug: str
    status: str
    latest_version: str | None
    latest_version_status: str | None


@dataclass(frozen=True, slots=True)
class VersionCreated:
    version_id: UUID
    plugin_id: UUID
    version: str
    status: str


@dataclass(frozen=True, slots=True)
class VersionView:
    version_id: UUID
    version: str
    status: str
    scan_status: str
    submitted_at: str
    decided_at: str | None
    artifact_url: str
    changelog: str
    sbom_url: str


@dataclass(frozen=True, slots=True)
class PendingReview:
    version_id: UUID
    plugin_id: UUID
    plugin_slug: str
    version: str
    status: str
    vendor_id: UUID
    vendor_name: str
    claimed_by: UUID | None
    submitted_at: str


@dataclass(frozen=True, slots=True)
class ReviewDetail:
    version_id: UUID
    plugin_slug: str
    version: str
    status: str
    scan_status: str
    sbom_url: str
    changelog: str
    artifact_url: str
    requested_capabilities: list[str]
    claimed_by: UUID | None
    review_notes: str


@dataclass(frozen=True, slots=True)
class ClaimResult:
    version_id: UUID
    claimed_by: UUID
    claimed_at: str


@dataclass(frozen=True, slots=True)
class DecisionResult:
    version_id: UUID
    status: str
    decided_by: UUID
    decided_at: str


class PluginService:
    """J23–J28 plugin shell, versions, capabilities, and the J36 decision publish depends on."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def portal(self, *, vendor_id: UUID, caller_user_id: UUID) -> PortalSummary:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        product_count = await self._count(ProductRow.id, ProductRow.vendor_id == vendor_id)
        offering_count = (
            await self._session.execute(
                select(func.count(OfferingRow.id))
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(ProductRow.vendor_id == vendor_id)
            )
        ).scalar_one()
        active_installs = (
            await self._session.execute(
                select(func.count(InstallationRow.id))
                .join(OfferingRow, OfferingRow.id == InstallationRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(ProductRow.vendor_id == vendor_id, InstallationRow.status == "active")
            )
        ).scalar_one()
        pending = (
            await self._session.execute(
                select(func.count(PluginVersionRow.id))
                .join(PluginRow, PluginRow.id == PluginVersionRow.plugin_id)
                .where(PluginRow.vendor_id == vendor_id, PluginVersionRow.status == "pending_review")
            )
        ).scalar_one()
        return PortalSummary(
            vendor_id=vendor.id,
            status=vendor.status,
            product_count=int(product_count),
            offering_count=int(offering_count),
            active_installs=int(active_installs),
            pending_plugin_reviews=int(pending),
        )

    async def register_plugin(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        name: str,
        slug: str,
        category: str,
        short_description: str,
    ) -> PluginCreated:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        if vendor.status != "verified":
            raise ForbiddenError("vendor not verified")
        name = name.strip()
        slug = slug.strip().lower()
        category = category.strip()
        if not name or not category:
            raise ValidationError("name and category are required")
        if not _SLUG.match(slug):
            raise ValidationError("slug must be lowercase letters, numbers, and hyphens")
        taken = (
            await self._session.execute(select(PluginRow.id).where(PluginRow.slug == slug))
        ).scalar_one_or_none()
        if taken is not None:
            raise ConflictError("slug taken")

        plugin = PluginRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            name=name,
            slug=slug,
            category=category,
            short_description=short_description.strip(),
            status="draft",
        )
        self._session.add(plugin)
        await audit(
            self._session,
            action="plugin.registered",
            actor_user_id=caller_user_id,
            payload={"plugin_id": str(plugin.id), "vendor_id": str(vendor_id), "slug": slug},
        )
        await self._session.commit()
        return PluginCreated(plugin_id=plugin.id, slug=slug, status="draft", vendor_id=vendor_id)

    async def submit_version(
        self,
        *,
        plugin_id: UUID,
        caller_user_id: UUID,
        version: str,
        artifact_url: str,
        changelog: str,
        sbom_url: str,
    ) -> VersionCreated:
        plugin = await self._session.get(PluginRow, plugin_id)
        if plugin is None:
            raise NotFoundError("plugin not found")
        await require_vendor_owner(self._session, plugin.vendor_id, caller_user_id)
        version = version.strip()
        artifact_url = artifact_url.strip()
        sbom_url = sbom_url.strip()
        if not version or not artifact_url:
            raise ValidationError("version and artifact_url are required")
        if not sbom_url:
            raise ValidationError("missing SBOM")
        exists = (
            await self._session.execute(
                select(PluginVersionRow.id).where(
                    PluginVersionRow.plugin_id == plugin_id,
                    PluginVersionRow.version == version,
                )
            )
        ).scalar_one_or_none()
        if exists is not None:
            raise ConflictError("version already submitted")

        row = PluginVersionRow(
            id=uuid.uuid4(),
            plugin_id=plugin_id,
            version=version,
            artifact_url=artifact_url,
            changelog=changelog.strip(),
            sbom_url=sbom_url,
            status="pending_review",
            scan_status="pending",
        )
        self._session.add(row)
        self._session.add(
            OutboxEventRow(
                id=uuid.uuid4(),
                type="scan_plugin_artifact",
                payload_json={"version_id": str(row.id), "plugin_id": str(plugin_id)},
                status="pending",
            )
        )
        await audit(
            self._session,
            action="plugin_version.submitted",
            actor_user_id=caller_user_id,
            payload={"version_id": str(row.id), "plugin_id": str(plugin_id), "version": version},
        )
        await self._session.commit()
        return VersionCreated(
            version_id=row.id, plugin_id=plugin_id, version=version, status="pending_review"
        )

    async def declare_capabilities(
        self,
        *,
        version_id: UUID,
        caller_user_id: UUID,
        capabilities: list[tuple[str, str]],
    ) -> int:
        version = await self._session.get(PluginVersionRow, version_id)
        if version is None:
            raise NotFoundError("plugin version not found")
        plugin = await self._session.get(PluginRow, version.plugin_id)
        if plugin is None:
            raise NotFoundError("plugin not found")
        await require_vendor_owner(self._session, plugin.vendor_id, caller_user_id)
        if version.status in ("approved", "rejected"):
            raise ConflictError("capabilities are frozen after a decision")
        if not capabilities:
            raise ValidationError("at least one capability is required")
        scopes: list[str] = []
        for scope, _justification in capabilities:
            cleaned = scope.strip()
            if not cleaned:
                raise ValidationError("capability scope is required")
            if cleaned in scopes:
                raise ValidationError("duplicate capability scope")
            scopes.append(cleaned)

        existing = (
            await self._session.execute(
                select(PluginCapabilityRow).where(PluginCapabilityRow.version_id == version_id)
            )
        ).scalars().all()
        for row in existing:
            await self._session.delete(row)
        await self._session.flush()
        for scope, justification in capabilities:
            self._session.add(
                PluginCapabilityRow(
                    id=uuid.uuid4(),
                    version_id=version_id,
                    scope=scope.strip(),
                    justification=justification.strip(),
                )
            )
        await audit(
            self._session,
            action="plugin_capabilities.declared",
            actor_user_id=caller_user_id,
            payload={"version_id": str(version_id), "capability_count": len(scopes)},
        )
        await self._session.commit()
        return len(scopes)

    async def list_plugins(self, *, vendor_id: UUID, caller_user_id: UUID) -> list[PluginListItem]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        plugins = (
            await self._session.execute(
                select(PluginRow)
                .where(PluginRow.vendor_id == vendor_id)
                .order_by(PluginRow.created_at.desc())
            )
        ).scalars().all()
        if not plugins:
            return []
        versions = (
            await self._session.execute(
                select(PluginVersionRow)
                .where(PluginVersionRow.plugin_id.in_([plugin.id for plugin in plugins]))
                .order_by(PluginVersionRow.created_at.desc())
            )
        ).scalars().all()
        latest: dict[UUID, PluginVersionRow] = {}
        for version in versions:
            latest.setdefault(version.plugin_id, version)
        return [
            PluginListItem(
                plugin_id=plugin.id,
                name=plugin.name,
                slug=plugin.slug,
                status=plugin.status,
                latest_version=latest[plugin.id].version if plugin.id in latest else None,
                latest_version_status=latest[plugin.id].status if plugin.id in latest else None,
            )
            for plugin in plugins
        ]

    async def list_versions(
        self, *, plugin_id: UUID, caller_user_id: UUID
    ) -> tuple[UUID, list[VersionView]]:
        plugin = await self._session.get(PluginRow, plugin_id)
        if plugin is None:
            raise NotFoundError("plugin not found")
        vendor = await self._session.get(VendorProfileRow, plugin.vendor_id)
        if vendor is None:
            raise NotFoundError("vendor not found")
        try:
            await require_vendor_owner(self._session, plugin.vendor_id, caller_user_id)
        except ForbiddenError:
            await require_platform_operator(self._session, caller_user_id)
        rows = (
            await self._session.execute(
                select(PluginVersionRow)
                .where(PluginVersionRow.plugin_id == plugin_id)
                .order_by(PluginVersionRow.created_at.desc())
            )
        ).scalars().all()
        return plugin_id, [
            VersionView(
                version_id=row.id,
                version=row.version,
                status=row.status,
                scan_status=row.scan_status,
                submitted_at=row.created_at.isoformat() if row.created_at else "",
                decided_at=row.decided_at.isoformat() if row.decided_at else None,
                artifact_url=row.artifact_url,
                changelog=row.changelog,
                sbom_url=row.sbom_url,
            )
            for row in rows
        ]

    async def list_pending_reviews(
        self, *, caller_user_id: UUID, status: str | None = None
    ) -> list[PendingReview]:
        await require_platform_operator(self._session, caller_user_id)
        if status is not None and status not in ("pending_review", "changes_requested"):
            raise ValidationError("status must be pending_review or changes_requested")
        statuses = (status,) if status else ("pending_review", "changes_requested")
        rows = (
            await self._session.execute(
                select(PluginVersionRow, PluginRow, VendorProfileRow)
                .join(PluginRow, PluginRow.id == PluginVersionRow.plugin_id)
                .join(VendorProfileRow, VendorProfileRow.id == PluginRow.vendor_id)
                .where(PluginVersionRow.status.in_(statuses))
                .order_by(PluginVersionRow.created_at.asc())
            )
        ).all()
        return [
            PendingReview(
                version_id=version.id,
                plugin_id=plugin.id,
                plugin_slug=plugin.slug,
                version=version.version,
                status=version.status,
                vendor_id=vendor.id,
                vendor_name=vendor.legal_name,
                claimed_by=version.claimed_by,
                submitted_at=version.created_at.isoformat() if version.created_at else "",
            )
            for version, plugin, vendor in rows
        ]

    async def review_detail(self, *, version_id: UUID, caller_user_id: UUID) -> ReviewDetail:
        await require_platform_operator(self._session, caller_user_id)
        version = await self._session.get(PluginVersionRow, version_id)
        if version is None:
            raise NotFoundError("plugin version not found")
        plugin = await self._session.get(PluginRow, version.plugin_id)
        if plugin is None:
            raise NotFoundError("plugin not found")
        capabilities = (
            await self._session.execute(
                select(PluginCapabilityRow.scope).where(PluginCapabilityRow.version_id == version.id)
            )
        ).scalars().all()
        return ReviewDetail(
            version_id=version.id,
            plugin_slug=plugin.slug,
            version=version.version,
            status=version.status,
            scan_status=version.scan_status,
            sbom_url=version.sbom_url,
            changelog=version.changelog,
            artifact_url=version.artifact_url,
            requested_capabilities=list(capabilities),
            claimed_by=version.claimed_by,
            review_notes=version.review_notes,
        )

    async def claim_version(self, *, version_id: UUID, caller_user_id: UUID) -> ClaimResult:
        await require_platform_operator(self._session, caller_user_id)
        version = await self._session.get(PluginVersionRow, version_id)
        if version is None:
            raise NotFoundError("plugin version not found")
        if version.status not in ("pending_review", "changes_requested"):
            raise ConflictError("version is not awaiting review")
        if version.claimed_by is not None and version.claimed_by != caller_user_id:
            raise ConflictError("already claimed by another reviewer")
        now = utcnow()
        version.claimed_by = caller_user_id
        version.claimed_at = now
        await audit(
            self._session,
            action="plugin_version.claimed",
            actor_user_id=caller_user_id,
            payload={"version_id": str(version_id)},
        )
        await self._session.commit()
        return ClaimResult(version_id=version.id, claimed_by=caller_user_id, claimed_at=now.isoformat())

    async def request_changes(
        self, *, version_id: UUID, caller_user_id: UUID, notes: str
    ) -> DecisionResult:
        await require_platform_operator(self._session, caller_user_id)
        notes = notes.strip()
        if not notes:
            raise ValidationError("notes are required")
        version = await self._session.get(PluginVersionRow, version_id)
        if version is None:
            raise NotFoundError("plugin version not found")
        if version.status != "pending_review":
            raise ConflictError("version is not pending review")
        self._require_claim(version, caller_user_id)
        now = utcnow()
        version.status = "changes_requested"
        version.review_notes = notes
        await audit(
            self._session,
            action="plugin_version.changes_requested",
            actor_user_id=caller_user_id,
            payload={"version_id": str(version_id), "notes": notes},
        )
        await self._session.commit()
        return DecisionResult(
            version_id=version.id,
            status=version.status,
            decided_by=caller_user_id,
            decided_at=now.isoformat(),
        )

    def _require_claim(self, version: PluginVersionRow, caller_user_id: UUID) -> None:
        if version.claimed_by is not None and version.claimed_by != caller_user_id:
            raise ConflictError("version is claimed by another reviewer")

    async def decide_version(
        self,
        *,
        version_id: UUID,
        caller_user_id: UUID,
        decision: str,
        notes: str | None,
    ) -> DecisionResult:
        await require_platform_operator(self._session, caller_user_id)
        if decision not in ("approved", "rejected"):
            raise ValidationError("decision must be approved or rejected")
        version = await self._session.get(PluginVersionRow, version_id)
        if version is None:
            raise NotFoundError("plugin version not found")
        if version.status not in ("pending_review", "changes_requested"):
            raise ConflictError("version is not awaiting review")
        self._require_claim(version, caller_user_id)
        plugin = await self._session.get(PluginRow, version.plugin_id)
        if plugin is None:
            raise NotFoundError("plugin not found")
        now = utcnow()
        version.status = decision
        version.decided_by = caller_user_id
        version.decided_at = now
        if decision == "approved" and plugin.status == "draft":
            plugin.status = "active"
        await audit(
            self._session,
            action=f"plugin_version.{decision}",
            actor_user_id=caller_user_id,
            payload={
                "version_id": str(version_id),
                "plugin_id": str(plugin.id),
                "decision": decision,
                "notes": notes or "",
            },
        )
        await self._session.commit()
        return DecisionResult(
            version_id=version.id,
            status=decision,
            decided_by=caller_user_id,
            decided_at=now.isoformat(),
        )

    async def _count(self, column, criterion) -> int:
        value = (await self._session.execute(select(func.count(column)).where(criterion))).scalar_one()
        return int(value)
