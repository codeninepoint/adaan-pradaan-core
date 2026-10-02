"""J34 stub provision and J25 artifact scan, driven by the platform outbox."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marketplace.infrastructure.models import InstallationRow, PluginVersionRow, ServiceInstanceRow


async def handle_scan(session: AsyncSession, payload: dict) -> None:
    version_id = payload.get("version_id")
    if not version_id:
        return
    version = await session.get(PluginVersionRow, UUID(str(version_id)))
    if version is None:
        return
    if version.scan_status == "pending":
        version.scan_status = "passed"


async def handle_provision(session: AsyncSession, payload: dict) -> None:
    installation_id = payload.get("installation_id")
    if not installation_id:
        raise ValueError("installation_id required")
    installation = await session.get(InstallationRow, UUID(str(installation_id)))
    if installation is None:
        raise ValueError("installation not found")
    if installation.status == "active":
        return
    if installation.status != "provisioning":
        raise ValueError(f"installation status {installation.status}")

    existing = (
        await session.execute(
            select(ServiceInstanceRow.id).where(ServiceInstanceRow.installation_id == installation.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ServiceInstanceRow(
                id=uuid.uuid4(),
                installation_id=installation.id,
                status="active",
                external_ref=f"stub://install/{installation.id}",
            )
        )
    installation.status = "active"
    await session.flush()
