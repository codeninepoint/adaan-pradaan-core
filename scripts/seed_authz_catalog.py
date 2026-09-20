#!/usr/bin/env python3
"""Idempotent AuthZ catalog / system-role seed command.

Examples:
  PYTHONPATH=src python scripts/seed_authz_catalog.py
  PYTHONPATH=src python scripts/seed_authz_catalog.py --tenant-id <uuid>
  PYTHONPATH=src python scripts/seed_authz_catalog.py --operator-org-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from authz.infrastructure.seed import (
    seed_permission_catalog,
    seed_platform_system_roles,
    seed_tenant_system_roles,
)
from shared.settings import settings


async def _run(tenant_id: UUID | None, operator_org_id: UUID | None) -> int:
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            session: AsyncSession
            n = await seed_permission_catalog(session)
            print(f"permissions upserted: {n}")

            if tenant_id is not None:
                report = await seed_tenant_system_roles(session, tenant_id)
                print(
                    f"tenant system roles: roles={report.roles_upserted} "
                    f"links_added={report.role_permissions_upserted}"
                )

            if operator_org_id is not None:
                report = await seed_platform_system_roles(session, operator_org_id)
                print(
                    f"platform system roles: roles={report.roles_upserted} "
                    f"links_added={report.role_permissions_upserted}"
                )

            await session.commit()
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed AuthZ permission catalog and system roles")
    parser.add_argument("--tenant-id", type=UUID, default=None, help="Also seed tenant system roles")
    parser.add_argument(
        "--operator-org-id",
        type=UUID,
        default=None,
        help="Also seed platform system roles for this operator org",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.tenant_id, args.operator_org_id))


if __name__ == "__main__":
    sys.exit(main())
