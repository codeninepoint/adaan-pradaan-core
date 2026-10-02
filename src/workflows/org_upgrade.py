"""J07 organization upgrade — Temporal workflow + activity."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from temporalio import activity, workflow
from temporalio.common import RetryPolicy


@activity.defn(name="run_org_upgrade")
async def run_org_upgrade_activity(payload: dict) -> dict:
    from identity.interface.api.dependencies import get_keycloak, get_session_factory
    from tenant.application.org_upgrade import OrgUpgradeService

    factory = get_session_factory()
    async with factory() as session:
        service = OrgUpgradeService(session, get_keycloak())
        result = await service.run_for_request(
            request_id=UUID(payload["request_id"]),
            requester_principal_id=UUID(payload["requester_principal_id"]),
        )
    return {
        "request_id": str(result.request_id),
        "status": result.status,
        "org_id": str(result.org_id),
        "keycloak_realm_ref": result.keycloak_realm_ref,
        "error_message": result.error_message,
    }


@workflow.defn(name="OrgUpgradeWorkflow")
class OrgUpgradeWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        return await workflow.execute_activity(
            "run_org_upgrade",
            payload,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_attempts=5,
            ),
        )
