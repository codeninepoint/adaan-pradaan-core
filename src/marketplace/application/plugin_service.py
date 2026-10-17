from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
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
    VendorPluginActivationRow,
)
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shared.infrastructure.models import OutboxEventRow
from vendor.infrastructure.models import VendorProfileRow

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HIGH_RISK_TOKENS = ("payment", "payments", "webhook", "webhooks", "oauth", "oauth2")
_MEDIUM_RISK_TOKENS = ("pii", "identity", "network", "storage", "secret", "secrets")

STANDARD_PLUGIN_CATEGORIES: tuple[str, ...] = (
    "SHIP_PHYSICAL",
    "DELIVER_DIGITAL",
    "LICENSE_SOFTWARE",
    "PROVISION_SOFTWARE",
    "PROVISION_CLOUD",
    "STREAM_LMS_COURSE",
    "DELIVER_MULTIMEDIA",
    "DISPATCH_SERVICE",
    "BOOK_APPOINTMENT",
)


def risk_level_for_scopes(scopes: list[str]) -> str:
    lowered = [scope.lower() for scope in scopes]
    if any(token in scope for scope in lowered for token in _HIGH_RISK_TOKENS):
        return "high"
    if any(token in scope for scope in lowered for token in _MEDIUM_RISK_TOKENS):
        return "medium"
    return "low"


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
    category: str = ""
    short_description: str = ""
    review_notes: str = ""
    submitted_at: str = ""
    changelog: str = ""


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
    review_notes: str = ""


@dataclass(frozen=True, slots=True)
class VendorStandardPluginView:
    plugin_id: UUID
    name: str
    slug: str
    category: str
    short_description: str
    version: str | None
    tags: list[str]
    vendor_count: int
    activation_status: str  # active | inactive


@dataclass(frozen=True, slots=True)
class PluginSubmitResult:
    plugin_id: UUID
    version_id: UUID
    slug: str
    version: str
    status: str


@dataclass(frozen=True, slots=True)
class PendingReview:
    version_id: UUID
    plugin_id: UUID
    plugin_slug: str
    version: str
    status: str
    vendor_id: UUID | None
    vendor_name: str
    claimed_by: UUID | None
    submitted_at: str
    risk_level: str
    decided_by: UUID | None = None
    decided_at: str | None = None
    review_notes: str = ""


@dataclass(frozen=True, slots=True)
class ReviewStats:
    pending: int
    in_review: int
    published: int
    rejected: int
    standard_plugins: int


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
    risk_level: str


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


@dataclass(frozen=True, slots=True)
class StandardPluginView:
    plugin_id: UUID | None
    category: str
    name: str | None
    slug: str | None
    status: str | None
    short_description: str | None
    version: str | None
    requirements: list
    updated_at: str | None


@dataclass(frozen=True, slots=True)
class StandardPluginCreated:
    plugin_id: UUID
    slug: str
    category: str
    status: str
    version: str


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
            owner_kind="vendor",
            name=name,
            slug=slug,
            category=category,
            short_description=short_description.strip(),
            status="draft",
            requirements=[],
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
        if plugin.owner_kind == "platform" or plugin.vendor_id is None:
            raise ForbiddenError("use standard plugin APIs for platform-owned plugins")
        await require_vendor_owner(self._session, plugin.vendor_id, caller_user_id)
        version = version.strip()
        artifact_url = artifact_url.strip()
        sbom_url = sbom_url.strip()
        if not version or not artifact_url:
            raise ValidationError("version and artifact_url are required")
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
            sbom_url=sbom_url or "",
            status="pending_review",
            scan_status="pending",
            risk_level="low",
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

    async def submit_plugin_bundle(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        name: str,
        version: str,
        category: str,
        description: str,
        artifact_url: str,
        sbom_url: str = "",
        plugin_id: UUID | None = None,
        slug: str | None = None,
    ) -> PluginSubmitResult:
        """Register (or reuse) a vendor plugin and submit a version in one call."""
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        if vendor.status != "verified":
            raise ForbiddenError("vendor not verified")
        name = name.strip()
        category = category.strip()
        version = version.strip().lstrip("v")
        artifact_url = artifact_url.strip()
        if not name or not category or not version or not artifact_url:
            raise ValidationError("name, category, version, and artifact_url are required")

        if plugin_id is not None:
            plugin = await self._session.get(PluginRow, plugin_id)
            if plugin is None or plugin.vendor_id != vendor_id or plugin.owner_kind != "vendor":
                raise NotFoundError("plugin not found")
            if description.strip():
                plugin.short_description = description.strip()
            if category:
                plugin.category = category
            await self._session.flush()
        else:
            base_slug = (slug or name).strip().lower()
            base_slug = re.sub(r"[^a-z0-9]+", "-", base_slug).strip("-")
            if not base_slug:
                raise ValidationError("could not derive slug from name")
            candidate = base_slug
            suffix = 0
            while True:
                taken = (
                    await self._session.execute(select(PluginRow.id).where(PluginRow.slug == candidate))
                ).scalar_one_or_none()
                if taken is None:
                    break
                suffix += 1
                candidate = f"{base_slug}-{suffix}"
            plugin = PluginRow(
                id=uuid.uuid4(),
                vendor_id=vendor_id,
                owner_kind="vendor",
                name=name,
                slug=candidate,
                category=category,
                short_description=description.strip(),
                status="draft",
                requirements=[],
            )
            self._session.add(plugin)
            await self._session.flush()
            await audit(
                self._session,
                action="plugin.registered",
                actor_user_id=caller_user_id,
                payload={"plugin_id": str(plugin.id), "vendor_id": str(vendor_id), "slug": plugin.slug},
            )

        exists = (
            await self._session.execute(
                select(PluginVersionRow.id).where(
                    PluginVersionRow.plugin_id == plugin.id,
                    PluginVersionRow.version == version,
                )
            )
        ).scalar_one_or_none()
        if exists is not None:
            raise ConflictError("version already submitted")

        row = PluginVersionRow(
            id=uuid.uuid4(),
            plugin_id=plugin.id,
            version=version,
            artifact_url=artifact_url,
            changelog=description.strip(),
            sbom_url=sbom_url.strip(),
            status="pending_review",
            scan_status="pending",
            risk_level="low",
        )
        self._session.add(row)
        self._session.add(
            OutboxEventRow(
                id=uuid.uuid4(),
                type="scan_plugin_artifact",
                payload_json={"version_id": str(row.id), "plugin_id": str(plugin.id)},
                status="pending",
            )
        )
        await audit(
            self._session,
            action="plugin_version.submitted",
            actor_user_id=caller_user_id,
            payload={"version_id": str(row.id), "plugin_id": str(plugin.id), "version": version},
        )
        await self._session.commit()
        return PluginSubmitResult(
            plugin_id=plugin.id,
            version_id=row.id,
            slug=plugin.slug,
            version=version,
            status="pending_review",
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
        if plugin.vendor_id is None:
            raise ForbiddenError("vendor admin required")
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
        version.risk_level = risk_level_for_scopes(scopes)
        await audit(
            self._session,
            action="plugin_capabilities.declared",
            actor_user_id=caller_user_id,
            payload={
                "version_id": str(version_id),
                "capability_count": len(scopes),
                "risk_level": version.risk_level,
            },
        )
        await self._session.commit()
        return len(scopes)

    async def list_vendor_standard_plugins(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        q: str | None = None,
        category: str | None = None,
    ) -> list[VendorStandardPluginView]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        stmt = (
            select(PluginRow)
            .where(PluginRow.owner_kind == "platform", PluginRow.status == "active")
            .order_by(PluginRow.name.asc())
        )
        if category and category.strip():
            stmt = stmt.where(PluginRow.category == category.strip())
        if q and q.strip():
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(PluginRow.name).like(pattern),
                    func.lower(PluginRow.slug).like(pattern),
                    func.lower(PluginRow.short_description).like(pattern),
                    func.lower(PluginRow.category).like(pattern),
                )
            )
        plugins = (await self._session.execute(stmt)).scalars().all()
        if not plugins:
            return []
        plugin_ids = [p.id for p in plugins]
        versions = (
            await self._session.execute(
                select(PluginVersionRow)
                .where(
                    PluginVersionRow.plugin_id.in_(plugin_ids),
                    PluginVersionRow.status == "approved",
                )
                .order_by(PluginVersionRow.created_at.desc())
            )
        ).scalars().all()
        latest_version: dict[UUID, str] = {}
        for version in versions:
            latest_version.setdefault(version.plugin_id, version.version)
        activations = (
            await self._session.execute(
                select(VendorPluginActivationRow).where(
                    VendorPluginActivationRow.vendor_id == vendor_id,
                    VendorPluginActivationRow.plugin_id.in_(plugin_ids),
                )
            )
        ).scalars().all()
        activation_map = {row.plugin_id: row.status for row in activations}
        counts = dict(
            (
                await self._session.execute(
                    select(
                        VendorPluginActivationRow.plugin_id,
                        func.count(VendorPluginActivationRow.id),
                    )
                    .where(
                        VendorPluginActivationRow.plugin_id.in_(plugin_ids),
                        VendorPluginActivationRow.status == "active",
                    )
                    .group_by(VendorPluginActivationRow.plugin_id)
                )
            ).all()
        )
        result: list[VendorStandardPluginView] = []
        for plugin in plugins:
            tags = [plugin.category.lower().replace("_", "-")]
            if plugin.slug:
                tags.append(plugin.slug.split("-")[0])
            result.append(
                VendorStandardPluginView(
                    plugin_id=plugin.id,
                    name=plugin.name,
                    slug=plugin.slug,
                    category=plugin.category,
                    short_description=plugin.short_description or "",
                    version=latest_version.get(plugin.id),
                    tags=tags,
                    vendor_count=int(counts.get(plugin.id, 0)),
                    activation_status=activation_map.get(plugin.id, "inactive"),
                )
            )
        return result

    async def activate_standard_plugin(
        self, *, vendor_id: UUID, caller_user_id: UUID, plugin_id: UUID
    ) -> VendorStandardPluginView:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        if vendor.status != "verified":
            raise ForbiddenError("vendor not verified")
        plugin = await self._session.get(PluginRow, plugin_id)
        if plugin is None or plugin.owner_kind != "platform" or plugin.status != "active":
            raise NotFoundError("standard plugin not found")
        row = (
            await self._session.execute(
                select(VendorPluginActivationRow).where(
                    VendorPluginActivationRow.vendor_id == vendor_id,
                    VendorPluginActivationRow.plugin_id == plugin_id,
                )
            )
        ).scalar_one_or_none()
        now = utcnow()
        if row is None:
            self._session.add(
                VendorPluginActivationRow(
                    id=uuid.uuid4(),
                    vendor_id=vendor_id,
                    plugin_id=plugin_id,
                    status="active",
                    activated_at=now,
                    updated_at=now,
                )
            )
        else:
            row.status = "active"
            row.activated_at = now
            row.updated_at = now
        await audit(
            self._session,
            action="standard_plugin.activated",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "plugin_id": str(plugin_id)},
        )
        await self._session.commit()
        items = await self.list_vendor_standard_plugins(
            vendor_id=vendor_id, caller_user_id=caller_user_id
        )
        for item in items:
            if item.plugin_id == plugin_id:
                return item
        raise NotFoundError("standard plugin not found")

    async def deactivate_standard_plugin(
        self, *, vendor_id: UUID, caller_user_id: UUID, plugin_id: UUID
    ) -> VendorStandardPluginView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        plugin = await self._session.get(PluginRow, plugin_id)
        if plugin is None or plugin.owner_kind != "platform":
            raise NotFoundError("standard plugin not found")
        row = (
            await self._session.execute(
                select(VendorPluginActivationRow).where(
                    VendorPluginActivationRow.vendor_id == vendor_id,
                    VendorPluginActivationRow.plugin_id == plugin_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise ConflictError("plugin is not activated")
        row.status = "inactive"
        row.updated_at = utcnow()
        await audit(
            self._session,
            action="standard_plugin.deactivated",
            actor_user_id=caller_user_id,
            payload={"vendor_id": str(vendor_id), "plugin_id": str(plugin_id)},
        )
        await self._session.commit()
        items = await self.list_vendor_standard_plugins(
            vendor_id=vendor_id, caller_user_id=caller_user_id
        )
        for item in items:
            if item.plugin_id == plugin_id:
                return item
        raise NotFoundError("standard plugin not found")

    async def list_plugins(self, *, vendor_id: UUID, caller_user_id: UUID) -> list[PluginListItem]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        plugins = (
            await self._session.execute(
                select(PluginRow)
                .where(PluginRow.vendor_id == vendor_id, PluginRow.owner_kind == "vendor")
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
                category=plugin.category,
                short_description=plugin.short_description or "",
                review_notes=(latest[plugin.id].review_notes or "") if plugin.id in latest else "",
                submitted_at=(
                    latest[plugin.id].created_at.isoformat()
                    if plugin.id in latest and latest[plugin.id].created_at
                    else ""
                ),
                changelog=(latest[plugin.id].changelog or "") if plugin.id in latest else "",
            )
            for plugin in plugins
        ]

    async def list_versions(
        self, *, plugin_id: UUID, caller_user_id: UUID
    ) -> tuple[UUID, list[VersionView]]:
        plugin = await self._session.get(PluginRow, plugin_id)
        if plugin is None:
            raise NotFoundError("plugin not found")
        if plugin.owner_kind == "platform" or plugin.vendor_id is None:
            await require_platform_operator(self._session, caller_user_id)
        else:
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
                review_notes=row.review_notes or "",
            )
            for row in rows
        ]

    async def list_pending_reviews(
        self,
        *,
        caller_user_id: UUID,
        status: str | None = None,
        claimed: bool | None = None,
        risk: str | None = None,
        q: str | None = None,
    ) -> list[PendingReview]:
        await require_platform_operator(self._session, caller_user_id)
        allowed = (
            "pending_review",
            "changes_requested",
            "approved",
            "rejected",
            "published",
        )
        if status is not None and status not in allowed:
            raise ValidationError(f"status must be one of {', '.join(allowed)}")
        if risk is not None and risk not in ("low", "medium", "high"):
            raise ValidationError("risk must be low, medium, or high")
        if status == "published":
            statuses: tuple[str, ...] = ("approved",)
        elif status is None:
            statuses = ("pending_review", "changes_requested")
        else:
            statuses = (status,)

        stmt = (
            select(PluginVersionRow, PluginRow, VendorProfileRow)
            .join(PluginRow, PluginRow.id == PluginVersionRow.plugin_id)
            .outerjoin(VendorProfileRow, VendorProfileRow.id == PluginRow.vendor_id)
            .where(
                PluginVersionRow.status.in_(statuses),
                PluginRow.owner_kind == "vendor",
            )
        )
        if claimed is True:
            stmt = stmt.where(PluginVersionRow.claimed_by.is_not(None))
        elif claimed is False:
            stmt = stmt.where(PluginVersionRow.claimed_by.is_(None))
        if risk is not None:
            stmt = stmt.where(PluginVersionRow.risk_level == risk)
        if q:
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(PluginRow.slug).like(pattern),
                    func.lower(PluginRow.name).like(pattern),
                    func.lower(func.coalesce(VendorProfileRow.legal_name, "")).like(pattern),
                    func.lower(PluginVersionRow.version).like(pattern),
                )
            )
        if status in ("approved", "rejected", "published"):
            stmt = stmt.order_by(PluginVersionRow.decided_at.desc().nullslast())
        else:
            stmt = stmt.order_by(PluginVersionRow.created_at.asc())

        rows = (await self._session.execute(stmt)).all()
        return [
            PendingReview(
                version_id=version.id,
                plugin_id=plugin.id,
                plugin_slug=plugin.slug,
                version=version.version,
                status="published" if status == "published" and version.status == "approved" else version.status,
                vendor_id=vendor.id if vendor is not None else None,
                vendor_name=vendor.legal_name if vendor is not None else "Platform",
                claimed_by=version.claimed_by,
                submitted_at=version.created_at.isoformat() if version.created_at else "",
                risk_level=version.risk_level or "low",
                decided_by=version.decided_by,
                decided_at=version.decided_at.isoformat() if version.decided_at else None,
                review_notes=version.review_notes or "",
            )
            for version, plugin, vendor in rows
        ]

    async def review_stats(self, *, caller_user_id: UUID) -> ReviewStats:
        await require_platform_operator(self._session, caller_user_id)

        async def _vendor_version_count(*criteria) -> int:
            value = (
                await self._session.execute(
                    select(func.count(PluginVersionRow.id))
                    .join(PluginRow, PluginRow.id == PluginVersionRow.plugin_id)
                    .where(PluginRow.owner_kind == "vendor", *criteria)
                )
            ).scalar_one()
            return int(value)

        pending_rows = await _vendor_version_count(
            PluginVersionRow.status.in_(("pending_review", "changes_requested")),
            PluginVersionRow.claimed_by.is_(None),
        )
        in_review = await _vendor_version_count(
            PluginVersionRow.status.in_(("pending_review", "changes_requested")),
            PluginVersionRow.claimed_by.is_not(None),
        )
        published = await _vendor_version_count(PluginVersionRow.status == "approved")
        rejected = await _vendor_version_count(PluginVersionRow.status == "rejected")
        standard = (
            await self._session.execute(
                select(func.count(PluginRow.id)).where(PluginRow.owner_kind == "platform")
            )
        ).scalar_one()
        return ReviewStats(
            pending=pending_rows,
            in_review=in_review,
            published=published,
            rejected=rejected,
            standard_plugins=int(standard),
        )

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
            risk_level=version.risk_level or "low",
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
        version.review_notes = (notes or "").strip()
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

    async def list_standard_plugins(self, *, caller_user_id: UUID) -> list[StandardPluginView]:
        await require_platform_operator(self._session, caller_user_id)
        plugins = (
            await self._session.execute(
                select(PluginRow).where(PluginRow.owner_kind == "platform")
            )
        ).scalars().all()
        by_category = {plugin.category: plugin for plugin in plugins}
        versions = (
            await self._session.execute(
                select(PluginVersionRow)
                .where(PluginVersionRow.plugin_id.in_([p.id for p in plugins]))
                .order_by(PluginVersionRow.created_at.desc())
            )
        ).scalars().all() if plugins else []
        latest: dict[UUID, PluginVersionRow] = {}
        for version in versions:
            latest.setdefault(version.plugin_id, version)

        views: list[StandardPluginView] = []
        for category in STANDARD_PLUGIN_CATEGORIES:
            plugin = by_category.get(category)
            if plugin is None:
                views.append(
                    StandardPluginView(
                        plugin_id=None,
                        category=category,
                        name=None,
                        slug=None,
                        status=None,
                        short_description=None,
                        version=None,
                        requirements=[],
                        updated_at=None,
                    )
                )
                continue
            ver = latest.get(plugin.id)
            views.append(
                StandardPluginView(
                    plugin_id=plugin.id,
                    category=plugin.category,
                    name=plugin.name,
                    slug=plugin.slug,
                    status=plugin.status,
                    short_description=plugin.short_description,
                    version=ver.version if ver else None,
                    requirements=list(plugin.requirements or []),
                    updated_at=plugin.updated_at.isoformat() if plugin.updated_at else None,
                )
            )
        return views

    async def create_standard_plugin(
        self,
        *,
        caller_user_id: UUID,
        name: str,
        slug: str,
        category: str,
        short_description: str,
        version: str,
        artifact_url: str,
        changelog: str,
        requirements: list | None,
        publish: bool = True,
    ) -> StandardPluginCreated:
        await require_platform_operator(self._session, caller_user_id)
        name = name.strip()
        slug = slug.strip().lower()
        category = category.strip()
        version = version.strip()
        artifact_url = artifact_url.strip()
        if category not in STANDARD_PLUGIN_CATEGORIES:
            raise ValidationError("unsupported standard plugin category")
        if not name or not version or not artifact_url:
            raise ValidationError("name, version, and artifact_url are required")
        if not _SLUG.match(slug):
            raise ValidationError("slug must be lowercase letters, numbers, and hyphens")
        existing_cat = (
            await self._session.execute(
                select(PluginRow.id).where(
                    PluginRow.owner_kind == "platform", PluginRow.category == category
                )
            )
        ).scalar_one_or_none()
        if existing_cat is not None:
            raise ConflictError("standard plugin already exists for category")
        taken = (
            await self._session.execute(select(PluginRow.id).where(PluginRow.slug == slug))
        ).scalar_one_or_none()
        if taken is not None:
            raise ConflictError("slug taken")

        plugin_status = "active" if publish else "draft"
        plugin = PluginRow(
            id=uuid.uuid4(),
            vendor_id=None,
            owner_kind="platform",
            name=name,
            slug=slug,
            category=category,
            short_description=short_description.strip(),
            status=plugin_status,
            requirements=list(requirements or []),
        )
        self._session.add(plugin)
        ver = PluginVersionRow(
            id=uuid.uuid4(),
            plugin_id=plugin.id,
            version=version,
            artifact_url=artifact_url,
            changelog=changelog.strip(),
            sbom_url="platform://standard-plugin",
            status="approved",
            scan_status="passed",
            risk_level="low",
            decided_by=caller_user_id,
            decided_at=utcnow(),
            review_notes="platform standard plugin",
        )
        self._session.add(ver)
        await audit(
            self._session,
            action="standard_plugin.created",
            actor_user_id=caller_user_id,
            payload={
                "plugin_id": str(plugin.id),
                "category": category,
                "slug": slug,
                "status": plugin_status,
            },
        )
        await self._session.commit()
        return StandardPluginCreated(
            plugin_id=plugin.id,
            slug=slug,
            category=category,
            status=plugin_status,
            version=version,
        )

    async def update_standard_plugin(
        self,
        *,
        plugin_id: UUID,
        caller_user_id: UUID,
        name: str | None = None,
        short_description: str | None = None,
        requirements: list | None = None,
    ) -> StandardPluginView:
        plugin = await self._require_standard_plugin(plugin_id, caller_user_id)
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise ValidationError("name is required")
            plugin.name = cleaned
        if short_description is not None:
            plugin.short_description = short_description.strip()
        if requirements is not None:
            plugin.requirements = list(requirements)
        await audit(
            self._session,
            action="standard_plugin.updated",
            actor_user_id=caller_user_id,
            payload={"plugin_id": str(plugin.id)},
        )
        await self._session.commit()
        views = await self.list_standard_plugins(caller_user_id=caller_user_id)
        for view in views:
            if view.plugin_id == plugin.id:
                return view
        raise NotFoundError("plugin not found")

    async def set_standard_plugin_status(
        self, *, plugin_id: UUID, caller_user_id: UUID, status: str
    ) -> StandardPluginView:
        if status not in ("active", "unpublished", "deprecated", "draft"):
            raise ValidationError("invalid status")
        plugin = await self._require_standard_plugin(plugin_id, caller_user_id)
        plugin.status = status
        await audit(
            self._session,
            action=f"standard_plugin.{status}",
            actor_user_id=caller_user_id,
            payload={"plugin_id": str(plugin.id), "status": status},
        )
        await self._session.commit()
        views = await self.list_standard_plugins(caller_user_id=caller_user_id)
        for view in views:
            if view.plugin_id == plugin.id:
                return view
        raise NotFoundError("plugin not found")

    async def delete_standard_plugin(self, *, plugin_id: UUID, caller_user_id: UUID) -> None:
        plugin = await self._require_standard_plugin(plugin_id, caller_user_id)
        product_count = await self._count(ProductRow.id, ProductRow.plugin_id == plugin_id)
        if product_count > 0:
            raise ConflictError("standard plugin is in use; deprecate instead")
        install_count = (
            await self._session.execute(
                select(func.count(InstallationRow.id))
                .join(OfferingRow, OfferingRow.id == InstallationRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(ProductRow.plugin_id == plugin_id)
            )
        ).scalar_one()
        if int(install_count) > 0:
            raise ConflictError("standard plugin is in use; deprecate instead")
        versions = (
            await self._session.execute(
                select(PluginVersionRow).where(PluginVersionRow.plugin_id == plugin_id)
            )
        ).scalars().all()
        for version in versions:
            caps = (
                await self._session.execute(
                    select(PluginCapabilityRow).where(PluginCapabilityRow.version_id == version.id)
                )
            ).scalars().all()
            for cap in caps:
                await self._session.delete(cap)
            await self._session.delete(version)
        await self._session.delete(plugin)
        await audit(
            self._session,
            action="standard_plugin.deleted",
            actor_user_id=caller_user_id,
            payload={"plugin_id": str(plugin_id)},
        )
        await self._session.commit()

    async def _require_standard_plugin(self, plugin_id: UUID, caller_user_id: UUID) -> PluginRow:
        await require_platform_operator(self._session, caller_user_id)
        plugin = await self._session.get(PluginRow, plugin_id)
        if plugin is None or plugin.owner_kind != "platform":
            raise NotFoundError("standard plugin not found")
        return plugin

    async def _count(self, column, criterion) -> int:
        value = (await self._session.execute(select(func.count(column)).where(criterion))).scalar_one()
        return int(value)
