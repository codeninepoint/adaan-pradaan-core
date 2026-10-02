from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from authz.application.authorization_service import AuthorizationService
from authz.domain.deny_messages import public_forbid_detail
from authz.domain.models import ApiSurface, AuthorizeCommand
from resources.domain.repositories import ResourceRepository
from shared.domain.exceptions import ForbiddenError


@dataclass(frozen=True, slots=True)
class ListResourcesCommand:
    tenant_id: UUID
    principal_id: UUID
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ListedResource:
    resource_id: UUID
    tenant_id: UUID
    name: str
    resource_type: str
    status: str


class ListResourcesHandler:
    def __init__(
        self,
        *,
        resources: ResourceRepository,
        authorization: AuthorizationService,
    ) -> None:
        self._resources = resources
        self._authorization = authorization

    async def handle(self, command: ListResourcesCommand) -> list[ListedResource]:
        decision = await self._authorization.authorize(
            AuthorizeCommand(
                principal_id=command.principal_id,
                permission_code="resource.read",
                api_surface=ApiSurface.PUBLIC,
                tenant_id=command.tenant_id,
                request_id=command.request_id,
            )
        )
        if not decision.allowed:
            raise ForbiddenError(public_forbid_detail(decision.reason))

        rows = await self._resources.list_by_tenant(tenant_id=command.tenant_id)
        return [
            ListedResource(
                resource_id=r.id,
                tenant_id=r.tenant_id,
                name=r.name,
                resource_type=r.resource_type,
                status=r.status,
            )
            for r in rows
        ]
