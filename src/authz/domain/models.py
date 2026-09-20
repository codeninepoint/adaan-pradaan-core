from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class ApiSurface(str, Enum):
    """Where the request is evaluated. Never infer RBAC from JWT claims."""

    PUBLIC = "public"
    MANAGEMENT = "management"


class AuthorizationDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class AuthorizeCommand:
    principal_id: UUID
    permission_code: str
    api_surface: ApiSurface
    tenant_id: UUID | None = None
    operator_org_id: UUID | None = None
    request_id: str | None = None
    at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuthorizeResult:
    allowed: bool
    decision: AuthorizationDecision
    reason: str
    permission_code: str
    scope_type: str | None = None
    tenant_id: UUID | None = None
    operator_org_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PermissionRecord:
    id: UUID
    code: str
    scope_type: str
    status: str
