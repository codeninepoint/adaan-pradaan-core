# Phase 2 backend structure (FastAPI + SQLAlchemy, modular monolith)

This document defines a **minimal but extensible** module structure for implementation.

## Goals

- Keep bounded contexts separate without microservices.
- Make “tenant scoping” and “authorization checks” hard to forget.
- Support gradual evolution (RLS, async provisioning, marketplace plugins) later.

## Proposed folder layout

```
src/
  bootstrap/
    app.py
    settings.py
    deps.py
    middleware/
      auth.py
      tenant_context.py
      correlation.py
      audit.py

  core/
    db/
      base.py
      session.py
      types.py

  identity/
    domain/models.py
    infrastructure/repos.py
    application/services.py
    interfaces/api.py

  tenant/
    domain/models.py
    infrastructure/repos.py
    application/services.py
    interfaces/api.py

  authorization/
    domain/models.py
    infrastructure/repos.py
    application/services.py
    interfaces/api.py

  resources/
    domain/models.py
    infrastructure/repos.py
    application/services.py
    interfaces/api.py

  audit/
    domain/models.py
    infrastructure/repos.py
    application/services.py
    interfaces/api.py

  marketplace/
    domain/models.py
    infrastructure/repos.py
    application/services.py
    application/adapters/
      stub.py
    interfaces/api.py
    interfaces/admin_api.py

  billing/
    domain/models.py
    infrastructure/repos.py
    application/services.py
    interfaces/api.py

  metering/
    domain/models.py
    infrastructure/repos.py
    application/services.py
    interfaces/api.py
```

## Phase B — Marketplace module

| Service | Responsibility |
|---------|----------------|
| `PluginService` | Register plugin, submit/approve versions |
| `DiscoveryService` | Index capabilities, register adapter routes |
| `CatalogService` | Products, offerings (requires published plugin) |
| `EntitlementService` | Tenant install/uninstall |
| `ProvisioningService` | Adapter dispatch, resource linkage |

Admin routes (management plane): plugin version approve, vendor verify.

## Phase C — Billing and metering modules

| Service | Responsibility |
|---------|----------------|
| `PlanService` | CRUD plans |
| `SubscriptionService` | Create/update subscription on entitlement |
| `MeteringService` | Register meters, emit idempotent `UsageEvent` |
| `BillingService` | Period aggregation, invoice preview |

## Layering conventions (DDD-inspired, minimal)

| Layer | Contains | Must not contain |
|------|----------|------------------|
| `domain/` | SQLAlchemy models (or dataclasses), enums, invariants | FastAPI routers, request parsing |
| `infrastructure/` | repositories, DB queries, persistence concerns | business workflows spanning multiple aggregates |
| `application/` | services/use-cases coordinating repos + authz + audit | HTTP-specific concerns |
| `interfaces/` | FastAPI routes, request/response schemas | raw DB session usage |

**See also:** [full-ddd-evolution.md](full-ddd-evolution.md) — what would change to move from this minimal layering to full tactical DDD (blueprint only; no code change required by that guide).

## Repository pattern (pragmatic)

### Why repos exist

- Enforce tenant scoping by API design (every tenant-scoped query requires `tenant_id`).
- Keep SQLAlchemy query patterns consistent.

### Minimal repository interface style

| Repo | Key methods (examples) | Tenant scoping |
|------|-------------------------|---------------|
| `TenantRepo` | `get_tenant(tenant_id)` | tenant_id is primary key |
| `MembershipRepo` | `is_active_member(tenant_id, user_id)` | explicit tenant_id |
| `RBACRepo` | `get_user_permission_codes(tenant_id, user_id)` | explicit tenant_id |
| `QuotaRepo` | `get_for_update(tenant_id, resource_type)` | explicit tenant_id + row lock |
| `AllocationRepo` | `create_allocation(...)` | explicit tenant_id |
| `AuditRepo` | `append(entry)` | tenant_id optional but explicit |

## Service layer (application services)

### Service responsibilities

| Service | Responsibility | Notes |
|---------|----------------|------|
| `AuthService` | login/token issuance (Phase 2) | JWT only; sessions optional |
| `TenantService` | org/tenant CRUD + membership management | seeds default roles/quotas (optional) |
| `RBACService` | `check(tenant_id, user_id, permission_code)` | always default deny |
| `AllocationService` | quota check + create allocation + audit | one transaction |
| `AuditService` | append audit records | called by other services or middleware |

### Transaction guidance

- Business operations that modify multiple tables must occur in a single transaction at the **service layer** (not in routers).
- Example: allocation → lock quota → update used → insert allocation → insert audit.

## API route organization (minimal, implementation-friendly)

Prefer tenant-scoped routes where possible:

- `/v1/auth/*`
- `/v1/orgs/*`
- `/v1/tenants/*`
- `/v1/tenants/{tenant_id}/memberships/*`
- `/v1/tenants/{tenant_id}/roles/*`
- `/v1/tenants/{tenant_id}/resources/*`
- `/v1/tenants/{tenant_id}/allocations/*`
- `/v1/tenants/{tenant_id}/audit/*`

## Middleware responsibilities (Phase 2)

| Middleware | Responsibility | Output |
|------------|----------------|--------|
| Auth | validate JWT, resolve user | `request.state.user_id` |
| TenantContext | resolve tenant, verify membership and tenant status | `request.state.tenant_id` |
| Correlation | ensure correlation id | `request.state.correlation_id` |
| Audit (optional) | helper to write consistent audit entries | uses `AuditService` |

## Evolution hooks (without building them now)

- Add PostgreSQL RLS later by keeping `tenant_id` everywhere.
- Replace RBAC repo queries with SpiceDB later by keeping a single `RBACService.check()` boundary.
- Add async provisioning later by keeping allocation state machine and introducing a job table/eventing.

