"""Temporal worker for org-upgrade. Run: python -m workflows.worker"""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from shared.settings import settings
from workflows.org_upgrade import OrgUpgradeWorkflow, run_org_upgrade_activity


async def main() -> None:
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[OrgUpgradeWorkflow],
        activities=[run_org_upgrade_activity],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
