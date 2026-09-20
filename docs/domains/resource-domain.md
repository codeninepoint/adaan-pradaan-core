# Resource domain (bounded context: `resource`)

## Business responsibility

The Resource domain governs **what resources exist**, **how much can be consumed**, and **how allocation is requested and tracked**:

- Resource type catalog entries (e.g., compute clusters, storage volumes)
- Quota policies and enforcement per scope (tenant/project)
- Allocation workflow (request → approve → provision → active → release)
- Logical resource instances and their lifecycle

## Bounded context boundary

Owns:

- Quotas (policy + usage counters)
- Allocation requests and allocation state machine
- Logical resource instance registry (IDs, status, external references)

Depends on:

- Tenant context (tenant_id/project_id validity and status)
- Authorization checks (who can request/approve)
- Marketplace entitlements (whether a tenant is allowed to allocate certain types)
- Infrastructure provisioning port (async fulfillment)

Does not own:

- Cluster registry and physical provisioning implementation (Infrastructure)
- Permission catalogs/role bindings (Authorization)
- Billing subscription logic (Billing), except emitting usage events

## Aggregates and entities

### Aggregates

- **`ResourceType`** (aggregate root)
  - Invariant: stable code and schema version; referenced by quotas and allocations.
- **`QuotaPolicy`** (aggregate root)
  - Invariant: exactly one policy per (scope, resource_type, period); enforces hard limit.
- **`AllocationRequest`** (aggregate root)
  - Invariant: transitions follow state machine; idempotency enforced.
- **`ResourceInstance`** (aggregate root)
  - Invariant: corresponds to at most one allocation request; carries external reference (future K8s UID).

### Entities / value objects

- `QuotaUsage` (entity under quota policy): `used`, `reserved`
- `ResourceQuantity` (value object): integer quantity + unit (optional Phase 2)

## Entity specifications (Phase 1)

### `ResourceType`

- **Definition**: A platform-defined resource class consumers can request.
- **Business purpose**: Standardize what can be allocated, metered, and governed by quota.
- **Real-world examples**:
  - `compute.cluster`
  - `storage.volume`
  - `marketplace.app` (logical)
- **Attributes**:
  - `id`, `code` (unique), `display_name`, `category`
  - `schema_version`, `properties_schema_json`
  - `meter_name?` (billing meter linkage)
- **Relationships**:
  - ResourceType 1:N QuotaPolicy
  - ResourceType 1:N AllocationRequest
- **Lifecycle states**: `active` → `deprecated`.
- **Ownership**: Resource domain (or shared global catalog, but governed here).
- **Security considerations**:
  - Editing resource types is platform-admin only.
- **Audit requirements**:
  - Create/update/deprecate.
- **Scalability**:
  - Low cardinality; heavily cached; read-mostly.

### `QuotaPolicy`

- **Definition**: Quota limits for a resource type at a scope.
- **Business purpose**: Prevent overconsumption and enable plan-based governance.
- **Real-world examples**: “Project X can allocate at most 3 clusters”.
- **Attributes**:
  - `id`, `scope_type` (`tenant|project`), `scope_id`
  - `resource_type_code`
  - `hard_limit`, `soft_limit?`, `period` (`none|monthly`)
- **Relationships**:
  - QuotaPolicy 1:1 QuotaUsage (conceptually)
- **Cardinality**: one per (scope, resource_type, period).
- **Lifecycle states**: `active` → `disabled` (optional).
- **Ownership**: Resource domain.
- **Security considerations**:
  - Quota changes require strong authorization; careful with TOCTOU.
- **Audit requirements**:
  - Every quota edit; every enforcement failure.
- **Scalability**:
  - Write path during allocations; must be lock-safe (single-row update per scope+type).

### `QuotaUsage` (child entity)

- **Definition**: Current consumption counters for a quota.
- **Business purpose**: Enforce hard limits and implement reservation semantics.
- **Attributes**: `quota_policy_id`, `used`, `reserved`, `updated_at`.
- **Invariant**: `used + reserved <= hard_limit`.
- **Security considerations**:
  - Ensure tenant isolation; never allow cross-tenant updates.
- **Audit requirements**:
  - Log quota exceeded rejections and approvals that change counters.
- **Scalability**:
  - Hot rows possible for large tenants; consider per-project scoping to spread load.

### `AllocationRequest`

- **Definition**: Request to allocate some quantity of a resource type.
- **Business purpose**: Provide an auditable, enforceable workflow for allocation.
- **Real-world examples**: “Create a new compute cluster in project payments”.
- **Attributes**:
  - `id`, `tenant_id`, `project_id`
  - `resource_type_code`, `quantity`
  - `requested_by_principal_id`
  - `status`, `justification?`, `approved_by_principal_id?`
  - `idempotency_key`
- **Relationships**:
  - Project 1:N AllocationRequest
  - AllocationRequest 0..1:1 ResourceInstance
- **Lifecycle states**:
  - `draft` → `submitted` → `pending_approval?` → `approved` → `provisioning` → `active|failed` → `released`
- **Ownership**: Resource domain.
- **Security considerations**:
  - Requires authorization checks at create/approve/release.
  - Idempotency required for CLI retries.
- **Audit requirements**:
  - Request created, approved, rejected, provisioned, released.
- **Scalability**:
  - Potentially high volume; index by `(tenant_id, project_id, status)`.

### `ResourceInstance`

- **Definition**: Logical record representing an allocated instance.
- **Business purpose**: Stable ID for referencing resources across domains (billing, observability, infra).
- **Real-world examples**: “cluster-1234 in acme-prod/payments”.
- **Attributes**:
  - `id`, `tenant_id`, `project_id`
  - `resource_type_code`, `allocation_request_id`
  - `external_ref?` (future K8s UID, cloud provider id)
  - `status`, `metadata_json`
- **Relationships**:
  - N:1 AllocationRequest
- **Lifecycle states**: `provisioning` → `active` → `degraded` → `released`.
- **Ownership**: Resource domain.
- **Security considerations**:
  - Read restricted by tenant/project scope and authorization.
- **Audit requirements**:
  - Provisioning success/failure; state transitions.
- **Scalability**:
  - Query by project; add pagination; index `(tenant_id, project_id, status)`.

## Ownership boundaries (integration points)

- Emits domain events:
  - `AllocationRequested`, `AllocationApproved`, `AllocationProvisioned`, `AllocationFailed`, `ResourceReleased`
- Consumes:
  - Tenant lifecycle events (e.g., suspend → block new allocations)
  - Entitlement signals (Marketplace)
  - Subscription/plan changes that alter quotas (Billing)

