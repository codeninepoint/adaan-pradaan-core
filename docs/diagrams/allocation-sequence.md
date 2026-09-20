# Diagram: Allocation sequence (Phase 1)

```mermaid
sequenceDiagram
  participant CLI as CLI
  participant API as API
  participant Az as Authorization
  participant R as Resource
  participant M as Marketplace
  participant Inf as Infrastructure
  participant Obs as Observability

  CLI->>API: POST /projects/{id}/allocations
  API->>Az: check resource.allocation.create
  API->>M: verify Entitlement (if needed)
  API->>R: create AllocationRequest
  R->>R: reserve quota (reserved++)
  API->>Az: check resource.allocation.approve (if required)
  R->>R: commit quota (used++, reserved--)
  R->>Inf: ProvisioningPort.provision (async)
  Inf-->>R: ProvisioningCompleted / ProvisioningFailed
  R->>R: create/update ResourceInstance
  R->>Obs: register telemetry metadata (optional)
  API-->>CLI: allocation + instance ids
```

## Notes

- Marketplace entitlement check is conditional on `resource_type_code` being gated by an offering.
- Provisioning is asynchronous; Phase 1 models the port/adapter but does not ship Kubernetes manifests.
- Every state transition should emit an audit entry and a domain event (via outbox).

