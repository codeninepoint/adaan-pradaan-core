from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID


@dataclass
class RegistrationBootstrapResult:
    org_id: UUID
    tenant_id: UUID
    project_id: UUID
    tenant_admin_role_id: UUID
