# Workflow: Resource allocation (Phase 1)

## Business goal

Allow a tenant/project to request resources while enforcing:

- Authorization (who can request/approve)
- Entitlements (if resource type is marketplace-gated)
- Quotas (hard limits + reservation semantics)
- Auditability (every state transition is recorded)
- Provisioning integration (asynchronous fulfillment via infrastructure port)

## Preconditions

- Caller is authenticated (User or ServiceAccount).
- Tenant and Project exist and are `active`.
- Caller has required permissions at project/tenant scope.
- For marketplace resource types: tenant has an active entitlement.

## Sequence (high-level)

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

## State machine (AllocationRequest)

```mermaid
stateDiagram-v2
  [*] --> draft
  draft --> submitted: submit
  submitted --> pending_approval: requires_approval
  submitted --> approved: auto_approve
  pending_approval --> approved: approve
  pending_approval --> rejected: reject
  approved --> provisioning: start
  provisioning --> active: provision_ok
  provisioning --> failed: provision_fail
  active --> releasing: release
  releasing --> released: complete
  rejected --> [*]
  failed --> [*]
  released --> [*]
```

## Domain responsibilities

- **Authorization**:
  - `resource.allocation.create` at project scope
  - `resource.allocation.approve` if approval is required (policy-driven)
- **Marketplace**:
  - entitlement check for gated offerings
- **Resource**:
  - quota reservation and commit semantics
  - allocation request lifecycle + resource instance registry
  - emits events for provisioning and billing usage
- **Infrastructure**:
  - fulfills provisioning request (Phase 1: stub adapter; Phase 2: Kubernetes integration)
- **Observability**:
  - tenant/project metadata for correlation (Phase 1: configuration only)

## Key invariants and failure modes

- **Quota exceeded**: reject at reservation step; emit audit event and return error (Problem Details).
- **Provisioning failure**:
  - mark allocation `failed`
  - consider rolling back quota commit or using a compensating “release” event (choose one policy and audit it)
- **Idempotency**:
  - `X-Idempotency-Key` required for allocation POST.
  - repeat requests return same AllocationRequest/ResourceInstance outcome.

