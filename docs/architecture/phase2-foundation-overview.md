# Phase 2 foundation overview (minimal implementation plan)

This document refines Phase 1 architecture into the **minimum set of bounded contexts and models** required to start building a modular monolith using **FastAPI + PostgreSQL + SQLAlchemy**.

## Scope (included)

- **Identity**: users + JWT authentication
- **Tenant**: organizations, tenants, user membership in tenants
- **RBAC (basic)**: roles, permissions, user-role, role-permission
- **Resource**: resources, quotas, resource allocations
- **Audit logging**: append-only audit logs for security-sensitive actions

## Non-goals (explicit)

- ReBAC
- Marketplace
- Billing
- Kubernetes orchestration
- Event bus/outbox
- Microservices
- Observability stack
- SpiceDB integration

## Architectural shape (modular monolith)

- Single FastAPI application, structured as **bounded-context modules**.
- Each module contains:
  - **domain** (models + invariants)
  - **infrastructure** (SQLAlchemy repositories)
  - **application** (services/use cases)
  - **interfaces** (API routes)

## Tenant isolation strategy (minimal, Phase 2)

### Data scoping rule

- Any tenant-owned data is stored in a table containing a required `tenant_id` column.
- Repositories accept `tenant_id` explicitly in all tenant-scoped queries.

### Enforcement points

- **Middleware** verifies:
  - request is authenticated
  - tenant exists and is active
  - user is a member of the tenant (active membership)
- **Service layer** performs authorization checks and enforces quota rules.

> This keeps the code compatible with enabling PostgreSQL RLS later, but Phase 2 does not depend on RLS.

## JWT design (minimal)

### Required claims

- `sub`: `user_id` (UUID)
- `exp`: expiration timestamp
- `iat`: issued-at timestamp

### Optional claims (if you implement refresh sessions)

- `sid`: session id (UUID)

### Principles

- **Do not embed roles/permissions in the token**. RBAC is evaluated per request against the database so role changes take effect immediately.

## Domain model (Phase 2 foundation)

This section is an implementation-oriented catalog of the entities we will implement first.

### Identity bounded context

#### `User`

- **Purpose**: human principal that authenticates and performs actions.
- **Attributes**:
  - `id` (PK, UUID)
  - `email` (unique)
  - `display_name`
  - `password_hash`
  - `status`: `active | locked | disabled`
  - `created_at`, `updated_at`, `last_login_at?`
- **PK/FK**: PK `id`; referenced by TenantMembership, UserRole, ResourceAllocation (actor), AuditLog (actor).
- **Cardinality**:
  - User N:M Tenant via `TenantMembership`
  - User N:M Role via `UserRole` (within tenant)
- **Lifecycle**: `active` → `locked|disabled`
- **Ownership**: Identity
- **Tenant scoping**: global (no `tenant_id`)

### Tenant bounded context

#### `Organization`

- **Purpose**: top-level customer entity; groups tenants.
- **Attributes**:
  - `id` (PK)
  - `name`, `slug` (unique)
  - `status`: `active | suspended | closed`
  - timestamps
- **PK/FK**: PK `id`
- **Cardinality**: Organization 1:N Tenant
- **Lifecycle**: active → suspended → closed
- **Ownership**: Tenant
- **Tenant scoping**: global (no `tenant_id`)

#### `Tenant`

- **Purpose**: primary isolation boundary for data and RBAC.
- **Attributes**:
  - `id` (PK)
  - `organization_id` (FK → Organization)
  - `name`, `slug`
  - `status`: `active | suspended | deleted`
  - timestamps
- **PK/FK**: PK `id`; FK `organization_id`
- **Cardinality**:
  - Tenant 1:N TenantMembership
  - Tenant 1:N Role
  - Tenant 1:N Resource / Quota / ResourceAllocation / AuditLog
- **Lifecycle**: active → suspended → deleted
- **Ownership**: Tenant
- **Tenant scoping**: defines `tenant_id` scope for all tenant-owned data

#### `TenantMembership`

- **Purpose**: link a `User` to a `Tenant` (belongs-to).
- **Attributes**:
  - `id` (PK)
  - `tenant_id` (FK → Tenant)
  - `user_id` (FK → User)
  - `membership_role`: `owner | member | viewer` (not a permission bundle)
  - `status`: `active | removed`
  - timestamps
- **Cardinality**:
  - Tenant 1:N TenantMembership
  - User 1:N TenantMembership (across tenants)
- **Lifecycle**: active → removed
- **Ownership**: Tenant
- **Tenant scoping**: tenant-scoped (contains `tenant_id`)

### Authorization bounded context (basic RBAC)

#### `Permission`

- **Purpose**: atomic right represented as a stable code string.
- **Attributes**:
  - `id` (PK)
  - `code` (unique), e.g. `resource.allocation.create`
  - `description`
- **Cardinality**: Permission N:M Role via `RolePermission`
- **Lifecycle**: active → deprecated (rare)
- **Ownership**: Authorization
- **Tenant scoping**: global catalog (no `tenant_id`)

#### `Role`

- **Purpose**: bundle of permissions, owned by a tenant.
- **Attributes**:
  - `id` (PK)
  - `tenant_id` (FK → Tenant)
  - `name` (unique per tenant)
  - `is_system` (seeded default roles)
  - `status`: `active | deprecated`
- **Cardinality**:
  - Role N:M Permission via `RolePermission`
  - Role N:M User via `UserRole`
- **Lifecycle**: active → deprecated
- **Ownership**: Authorization
- **Tenant scoping**: tenant-scoped via `tenant_id`

#### `UserRole`

- **Purpose**: assign a role to a user in a tenant.
- **Attributes**:
  - `id` (PK)
  - `tenant_id` (FK → Tenant)
  - `user_id` (FK → User)
  - `role_id` (FK → Role)
  - timestamps
- **Cardinality**: User N:M Role per tenant
- **Lifecycle**: active → revoked (delete or soft-delete)
- **Ownership**: Authorization
- **Tenant scoping**: tenant-scoped via `tenant_id`

#### `RolePermission`

- **Purpose**: assign a permission to a role.
- **Attributes**:
  - `id` (PK)
  - `role_id` (FK → Role)
  - `permission_id` (FK → Permission)
- **Cardinality**: Role N:M Permission
- **Lifecycle**: present/removed
- **Ownership**: Authorization
- **Tenant scoping**: implied by role (no `tenant_id` required)

### Resource bounded context

#### `Resource`

- **Purpose**: registry of tenant-owned resources.
- **Attributes**:
  - `id` (PK)
  - `tenant_id` (FK → Tenant)
  - `type` (string, e.g. `compute.cluster`)
  - `name`
  - `status`: `active | deleted`
  - `metadata_json`
  - timestamps
- **Cardinality**: Tenant 1:N Resource
- **Lifecycle**: active → deleted
- **Ownership**: Resource
- **Tenant scoping**: tenant-scoped via `tenant_id`

#### `Quota`

- **Purpose**: minimal quota record to support allocation checks.
- **Attributes**:
  - `id` (PK)
  - `tenant_id` (FK → Tenant)
  - `resource_type`
  - `hard_limit`
  - `used`
  - timestamps
- **Cardinality**: Tenant 1:N Quota
- **Lifecycle**: active → disabled
- **Ownership**: Resource
- **Tenant scoping**: tenant-scoped via `tenant_id`

#### `ResourceAllocation`

- **Purpose**: record the allocation request and outcome for a resource type.
- **Attributes**:
  - `id` (PK)
  - `tenant_id` (FK → Tenant)
  - `resource_type`
  - `quantity`
  - `status`: `requested | pending_approval | approved | rejected | allocated | failed | released`
  - `requested_by_user_id` (FK → User)
  - `approved_by_user_id?` (FK → User)
  - `resource_id?` (FK → Resource)
  - timestamps
- **Cardinality**:
  - Tenant 1:N ResourceAllocation
  - ResourceAllocation 0..1 Resource
- **Lifecycle**: see state diagram in `docs/diagrams/phase2-allocation-state.md`
- **Ownership**: Resource
- **Tenant scoping**: tenant-scoped via `tenant_id`

### Audit bounded context

#### `AuditLog`

- **Purpose**: append-only record of security-relevant actions and business changes.
- **Attributes**:
  - `id` (PK)
  - `occurred_at`
  - `tenant_id?` (nullable for global actions)
  - `actor_user_id?` (FK → User)
  - `action`
  - `resource_type?`, `resource_id?`
  - `ip?`, `user_agent?`, `correlation_id?`
  - `payload_json`
- **Cardinality**: many entries per entity
- **Lifecycle**: recorded (terminal)
- **Ownership**: Audit/Platform
- **Tenant scoping**: tenant-scoped when `tenant_id` present; access restricted by RBAC

## Minimal permission catalog (starting point)

- `tenant.read`, `tenant.admin`
- `resource.read`, `resource.create`, `resource.delete`
- `resource.allocation.create`, `resource.allocation.approve`, `resource.allocation.release`
- `audit.read`

