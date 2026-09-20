from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreateResourceCommand:
    tenant_id: UUID
    principal_id: UUID
    actor_user_id: UUID
    name: str
    resource_type: str
    external_ref: str | None = None
    request_id: str | None = None
