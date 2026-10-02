from __future__ import annotations

from temporalio.client import Client

from shared.settings import settings

_client: Client | None = None


async def start_org_upgrade(payload: dict) -> None:
    """Enqueue J07. Workflow id is the registration request id (idempotent start)."""
    global _client
    if _client is None:
        _client = await Client.connect(settings.temporal_address)
    await _client.start_workflow(
        "OrgUpgradeWorkflow",
        payload,
        id=f"org-upgrade-{payload['request_id']}",
        task_queue=settings.temporal_task_queue,
    )
