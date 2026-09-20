from __future__ import annotations

from typing import Protocol
from uuid import UUID

from resources.domain.aggregate import Resource


class ResourceRepository(Protocol):
    """All reads/writes are tenant-scoped — tenant_id is mandatory on every method."""

    async def add(self, resource: Resource) -> None:
        """Persist a new resource. Caller must set tenant_id on the aggregate."""

    async def get_by_id(self, *, tenant_id: UUID, resource_id: UUID) -> Resource | None:
        """Load by id within tenant; never returns another tenant's row."""

    async def exists_by_name(self, *, tenant_id: UUID, name: str) -> bool:
        """Name uniqueness check scoped to tenant."""
