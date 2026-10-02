from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from authz.application.authorization_service import AuthorizationService
from authz.application.role_bindings import RoleBindingService
from authz.infrastructure.repositories import build_authorization_service
from identity.interface.api.dependencies import get_session, get_session_factory


def get_authorization_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AuthorizationService:
    return build_authorization_service(session, session_factory=session_factory)


def get_role_binding_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> RoleBindingService:
    return RoleBindingService(session, authorization)
