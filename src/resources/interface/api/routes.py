from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from identity.interface.api.dependencies import CurrentAuthDep
from resources.application.commands import CreateResourceCommand
from resources.application.create_resource import CreateResourceHandler
from resources.interface.api.dependencies import get_create_resource_handler
from resources.interface.api.schemas import CreateResourceRequest, CreateResourceResponse

router = APIRouter(prefix="/api/v1", tags=["resources"])


@router.post(
    "/tenants/{tenant_id}/resources",
    response_model=CreateResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resource(
    tenant_id: UUID,
    body: CreateResourceRequest,
    auth: CurrentAuthDep,
    handler: Annotated[CreateResourceHandler, Depends(get_create_resource_handler)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> CreateResourceResponse:
    user, _session, _credential = auth
    result = await handler.handle(
        CreateResourceCommand(
            tenant_id=tenant_id,
            principal_id=user.principal_id,
            actor_user_id=user.id,
            name=body.name,
            resource_type=body.resource_type,
            external_ref=body.external_ref,
            request_id=x_request_id,
        )
    )
    return CreateResourceResponse(
        id=str(result.resource_id),
        tenant_id=str(result.tenant_id),
        name=result.name,
        resource_type=result.resource_type,
        status=result.status,
    )
