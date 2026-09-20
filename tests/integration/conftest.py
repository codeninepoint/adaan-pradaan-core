from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from api.main import create_app
from authz.infrastructure.seed import seed_permission_catalog
from identity.infrastructure.keycloak_client import FakeKeycloakClient
from identity.infrastructure.models import IdentityRealmRow
import identity.infrastructure.models  # noqa: F401
import tenant.infrastructure.models  # noqa: F401
import authz.infrastructure.models  # noqa: F401
import resources.infrastructure.models  # noqa: F401
from shared.infrastructure.models import Base
from identity.infrastructure.models import DeliverySecretRow


async def get_delivery_secret(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    purpose: str,
) -> str:
    async with session_factory() as session:
        result = await session.execute(
            select(DeliverySecretRow)
            .where(
                DeliverySecretRow.purpose == purpose,
                DeliverySecretRow.consumed_at.is_(None),
                DeliverySecretRow.secret_plain.is_not(None),
            )
            .order_by(DeliverySecretRow.created_at.desc())
        )
        row = result.scalars().first()
        assert row is not None and row.secret_plain is not None
        return row.secret_plain


@pytest.fixture(scope="session")
def postgres_url():
    env = os.getenv("TENANT_DATABASE_URL")
    if env:
        yield env
        return
    with PostgresContainer("postgres:16-alpine") as postgres:
        url = postgres.get_connection_url()
        yield url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
            "postgresql://", "postgresql+asyncpg://"
        )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(postgres_url: str) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(postgres_url, echo=False)
    async with engine.begin() as conn:
        for schema in ("platform", "identity", "tenant", "authz", "resource"):
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        realm = await session.execute(
            select(IdentityRealmRow).where(IdentityRealmRow.realm_name == "platform")
        )
        if not realm.scalar_one_or_none():
            session.add(
                IdentityRealmRow(
                    id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
                    realm_name="platform",
                    realm_type="platform",
                    issuer="https://platform.auth.platform.io",
                    issuer_url="https://platform.auth.platform.io",
                    status="active",
                )
            )
        await seed_permission_catalog(session)
        await session.commit()

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def session_factory(engine: AsyncEngine) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    yield async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def clean_db(session_factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[None, None]:
    async with session_factory() as session:
        await session.execute(
            text(
                """
                TRUNCATE TABLE
                  platform.outbox_events,
                  resource.resources,
                  authz.authorization_audit_log,
                  authz.principal_roles,
                  authz.role_permissions,
                  authz.roles,
                  tenant.tenant_memberships,
                  tenant.projects,
                  tenant.tenants,
                  tenant.org_memberships,
                  tenant.organizations,
                  identity.api_keys,
                  identity.service_accounts,
                  identity.delivery_secrets,
                  identity.password_reset_tokens,
                  identity.verification_tokens,
                  identity.audit_log,
                  identity.sessions,
                  identity.credentials,
                  identity.users,
                  identity.principals
                RESTART IDENTITY CASCADE
                """
            )
        )
        # CASCADE may clear identity_realms (FK → organizations); restore platform realm.
        realm = await session.execute(
            select(IdentityRealmRow).where(IdentityRealmRow.realm_name == "platform")
        )
        if not realm.scalar_one_or_none():
            session.add(
                IdentityRealmRow(
                    id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
                    realm_name="platform",
                    realm_type="platform",
                    issuer="https://platform.auth.platform.io",
                    issuer_url="https://platform.auth.platform.io",
                    status="active",
                )
            )
        await seed_permission_catalog(session)
        await session.commit()
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def client(session_factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_session():
        async with session_factory() as session:
            yield session

    from identity.interface.api import dependencies as deps

    deps._session_factory = session_factory
    deps._keycloak = FakeKeycloakClient()
    app.dependency_overrides[deps.get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
