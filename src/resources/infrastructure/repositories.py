from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resources.domain.aggregate import Resource
from resources.infrastructure.models import ResourceRow


class SqlAlchemyResourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, resource: Resource) -> None:
        self._session.add(
            ResourceRow(
                id=resource.id,
                tenant_id=resource.tenant_id,
                name=resource.name,
                resource_type=resource.resource_type,
                status=resource.status,
                external_ref=resource.external_ref,
                created_by_principal_id=resource.created_by_principal_id,
                created_at=resource.created_at,
                updated_at=resource.updated_at,
            )
        )
        await self._session.flush()

    async def get_by_id(self, *, tenant_id: UUID, resource_id: UUID) -> Resource | None:
        result = await self._session.execute(
            select(ResourceRow).where(
                ResourceRow.tenant_id == tenant_id,
                ResourceRow.id == resource_id,
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def exists_by_name(self, *, tenant_id: UUID, name: str) -> bool:
        result = await self._session.execute(
            select(ResourceRow.id).where(
                ResourceRow.tenant_id == tenant_id,
                ResourceRow.name == name.strip(),
            )
        )
        return result.scalar_one_or_none() is not None


def _to_domain(row: ResourceRow) -> Resource:
    return Resource(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        resource_type=row.resource_type,
        status=row.status,
        external_ref=row.external_ref,
        created_by_principal_id=row.created_by_principal_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
