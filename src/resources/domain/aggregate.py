from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from shared.domain.base import AggregateRoot, utcnow
from shared.domain.exceptions import ValidationError


@dataclass
class Resource(AggregateRoot):
    """Tenant-owned resource instance (logical registry entry)."""

    tenant_id: UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    resource_type: str = ""
    status: str = "active"
    external_ref: str | None = None
    created_by_principal_id: UUID | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: UUID,
        name: str,
        resource_type: str,
        created_by_principal_id: UUID,
        external_ref: str | None = None,
        resource_id: UUID | None = None,
    ) -> Resource:
        cleaned_name = (name or "").strip()
        cleaned_type = (resource_type or "").strip()
        if not cleaned_name:
            raise ValidationError("name is required")
        if len(cleaned_name) > 255:
            raise ValidationError("name is too long")
        if not cleaned_type:
            raise ValidationError("resource_type is required")
        if len(cleaned_type) > 128:
            raise ValidationError("resource_type is too long")

        resource = cls(
            id=resource_id or uuid.uuid4(),
            tenant_id=tenant_id,
            name=cleaned_name,
            resource_type=cleaned_type,
            status="active",
            external_ref=(external_ref.strip() if external_ref else None) or None,
            created_by_principal_id=created_by_principal_id,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        resource.record_event(
            "resource.created",
            {
                "resource_id": str(resource.id),
                "tenant_id": str(tenant_id),
                "resource_type": cleaned_type,
                "name": cleaned_name,
            },
        )
        return resource
