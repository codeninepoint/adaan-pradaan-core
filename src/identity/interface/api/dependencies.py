from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from identity.application.identity_service import IdentityApplicationService
from identity.application.ports.keycloak import KeycloakClient
from identity.infrastructure.keycloak_admin import RealKeycloakClient
from identity.infrastructure.keycloak_client import FakeKeycloakClient
from shared.domain.exceptions import UnauthorizedError
from shared.settings import settings

_bearer = HTTPBearer(auto_error=False)
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_keycloak: KeycloakClient | None = None


def _ensure_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(settings.database_url, echo=False)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return _ensure_factory()


async def get_session() -> AsyncSession:
    factory = _ensure_factory()
    async with factory() as session:
        yield session


def get_keycloak() -> KeycloakClient:
    global _keycloak
    if _keycloak is None:
        mode = (settings.keycloak_mode or "fake").lower()
        if mode == "fake":
            _keycloak = FakeKeycloakClient()
        elif mode == "real":
            _keycloak = RealKeycloakClient(
                base_url=settings.keycloak_base_url or "",
                admin_username=settings.keycloak_admin_username,
                admin_password=settings.keycloak_admin_password,
                client_id=settings.keycloak_client_id,
            )
        else:
            raise RuntimeError(f"unsupported TENANT_KEYCLOAK_MODE={mode!r}")
    return _keycloak


def get_identity_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    keycloak: Annotated[KeycloakClient, Depends(get_keycloak)],
) -> IdentityApplicationService:
    return IdentityApplicationService(session, keycloak)


async def get_current_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> tuple:
    if not credentials:
        raise HTTPException(status_code=401, detail="invalid token")
    try:
        return await service.resolve_user_from_access_token(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


CurrentAuthDep = Annotated[tuple, Depends(get_current_auth)]
