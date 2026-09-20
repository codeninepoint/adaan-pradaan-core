from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from authz.domain.deny_messages import public_forbid_detail
from authz.domain.models import ApiSurface, AuthorizeCommand
from authz.application.authorization_service import AuthorizationService
from resources.application.commands import CreateResourceCommand
from resources.domain.aggregate import Resource
from resources.domain.repositories import ResourceRepository
from shared.application.ports import UnitOfWork
from shared.domain.exceptions import ConflictError, ForbiddenError


@dataclass(frozen=True, slots=True)
class CreateResourceResult:
    resource_id: UUID
    tenant_id: UUID
    name: str
    resource_type: str
    status: str


class CreateResourceHandler:
    """
    Vertical-slice command handler for creating a tenant-scoped resource.

    Transaction boundary: all authz reads + insert commit together via UnitOfWork.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        resources: ResourceRepository,
        authorization: AuthorizationService,
    ) -> None:
        self._uow = uow
        self._resources = resources
        self._authorization = authorization

    async def handle(self, command: CreateResourceCommand) -> CreateResourceResult:
        decision = await self._authorization.authorize(
            AuthorizeCommand(
                principal_id=command.principal_id,
                permission_code="resource.create",
                api_surface=ApiSurface.PUBLIC,
                tenant_id=command.tenant_id,
                request_id=command.request_id,
            )
        )
        if not decision.allowed:
            raise ForbiddenError(public_forbid_detail(decision.reason))

        if await self._resources.exists_by_name(tenant_id=command.tenant_id, name=command.name.strip()):
            raise ConflictError("resource name already exists in tenant")

        resource = Resource.create(
            tenant_id=command.tenant_id,
            name=command.name,
            resource_type=command.resource_type,
            created_by_principal_id=command.principal_id,
            external_ref=command.external_ref,
        )
        await self._resources.add(resource)
        await self._uow.commit()

        return CreateResourceResult(
            resource_id=resource.id,
            tenant_id=resource.tenant_id,
            name=resource.name,
            resource_type=resource.resource_type,
            status=resource.status,
        )
