# Authorization domain (basic RBAC only, Phase 2)

This document specifies the **minimal RBAC model** to support Phase 2 implementation, including **tenant-scoped** permissions for customers/vendors and **platform-scoped** permissions for SaaS operators on the [management plane](../architecture/management-plane.md).

Non-goals:

- ReBAC / relationship tuples
- ABAC policy engine
- External authorization stores (e.g., SpiceDB)

## Responsibility

Decide whether an authenticated `User` may perform an action:

- **Within a tenant scope** (public control plane API), or
- **At platform scope** (internal admin API only; Platform Operator organization).

## Boundary (what this domain owns)

Owns:

- Permission catalog (global), including `platform.*` codes
- Role definitions:
  - **tenant-scoped** roles (per customer tenant)
  - **platform-scoped** roles (per Platform Operator organization)
- Assignments:
  - user ↔ role (tenant-scoped or platform-scoped)
  - role ↔ permission

Does not own:

- Authentication (Identity)
- Membership (TenantMembership, OrganizationMembership) — Authorization requires membership as a prerequisite but does not store it
- Network placement of admin API (operations / management plane)
- Domain data (Resource, Tenant), except IDs used for scope

## Core concepts

### Permission

An **atomic action**, represented by a stable string code.

Examples:

- `resource.allocation.create`
- `tenant.admin`

### Role

A named bundle of permissions within a tenant, e.g.:

- `tenant-admin`
- `resource-admin`
- `viewer`

## RBAC scopes

| Scope | `scope_type` | Assignment key | API surface |
|-------|--------------|----------------|-------------|
| **Tenant** | `tenant` | `tenant_id` | Public control plane |
| **Platform** | `platform` | `platform_operator_org_id` | Internal admin API only |

**Invariant:** `tenant.admin` and other tenant permissions must **never** imply `platform.*` permissions. Public API must reject tokens used for platform-only routes even if misconfigured in DB.

Platform roles are assignable only to users with active membership in an organization where `is_platform_operator = true`.

## Data model (minimal RBAC tables)

This model is intentionally small and relational (PostgreSQL-friendly). It supports tenant-scoped and platform-scoped assignments plus a global permission catalog.

### Tables and keys

| Table | Purpose | Scoped? | Primary key | Foreign keys | Key uniqueness |
|------|---------|---------|-------------|--------------|----------------|
| `permissions` | global catalog of atomic actions | No | `id` | — | `code` unique; optional `scope` column (`tenant` \| `platform`) |
| `roles` | role definitions | Yes | `id` | `scope_type`, `scope_id` (tenant_id or operator org id) | `(scope_type, scope_id, name)` unique |
| `role_permissions` | map role → permissions | Derived | `id` (or composite) | `role_id`, `permission_id` | `(role_id, permission_id)` unique |
| `user_roles` | assign user → role | Yes | `id` | `user_id`, `role_id`, `scope_type`, `scope_id` | `(scope_type, scope_id, user_id, role_id)` unique |

### Cardinality

| Relationship | Cardinality | Notes |
|--------------|-------------|------|
| `Role` → `Permission` | N:M | via `role_permissions` |
| `User` → `Role` | N:M per tenant | via `user_roles` |
| `Tenant` → `Role` | 1:N | roles are tenant-owned |

### Lifecycle rules

| Entity | Lifecycle | Operational note |
|--------|-----------|------------------|
| `Permission` | `active → deprecated` | rarely changes; treat as catalog |
| `Role` | `active → deprecated` | keep old roles for audit history |
| `user_roles` | `present → revoked` | delete row or soft-delete; prefer soft-delete if you need audit |
| `role_permissions` | `present → removed` | changes require strict authorization |

## RBAC evaluation algorithms (Phase 2)

### Tenant scope (public API)

The system answers: *“Does user U have permission P in tenant T?”*

**Preconditions:**

- request is authenticated (Identity)
- tenant is active (Tenant)
- user has **active membership** in tenant (TenantMembership)
- request is on **public** API surface (not admin)

| Step | Input | Output | Notes |
|------|-------|--------|------|
| 1 | `tenant_id`, `user_id`, `permission_code` | permission id | permission must be tenant-scoped |
| 2 | `tenant_id`, `user_id` | role ids | `user_roles` where `scope_type = tenant` |
| 3 | role ids | permission ids | via `role_permissions` |
| 4 | match | allow/deny | default deny |

### Platform scope (admin API)

The system answers: *“Does user U have platform permission P?”*

**Preconditions:**

- request is authenticated (Identity)
- request arrives on **management plane** (network + ingress policy)
- user has **active membership** in a Platform Operator org (`is_platform_operator = true`)

| Step | Input | Output | Notes |
|------|-------|--------|------|
| 1 | `user_id`, `permission_code` | permission id | permission must start with `platform.` |
| 2 | `user_id` | operator org id | membership in platform operator org |
| 3 | operator org id, `user_id` | role ids | `user_roles` where `scope_type = platform` |
| 4 | role ids | permission ids | via `role_permissions` |
| 5 | match | allow/deny | default deny |

### Caching guidance (later, not required now)

- Cache permission id by code (global).
- Cache user’s role ids within tenant with short TTL.
- Do not cache across tenants without scoping key.

## Minimal permission catalog (starter set)

### Tenant scope (public API)

| Code | Meaning | Typical owners |
|------|---------|----------------|
| `tenant.read` | view tenant metadata | viewer+ |
| `tenant.admin` | manage tenant membership/roles/settings | tenant-admin |
| `resource.read` | list/read resources | viewer+ |
| `resource.create` | create resource records | resource-admin |
| `resource.delete` | delete resources | resource-admin |
| `resource.allocation.create` | request allocation | resource-admin |
| `resource.allocation.approve` | approve allocation (if required) | tenant-admin |
| `resource.allocation.release` | release allocation | resource-admin |
| `audit.read` | read audit logs (tenant-scoped) | tenant-admin |

### Platform scope (admin API only)

| Code | Meaning | Typical owners |
|------|---------|----------------|
| `platform.admin` | full platform configuration | platform operator admin |
| `platform.tenant.suspend` | suspend customer tenant | platform admin / security |
| `platform.tenant.read` | read any tenant metadata (support) | platform support |
| `platform.vendor.verify` | verify vendor identity | platform governance |
| `platform.plugin.approve` | approve plugin version for marketplace | platform governance |
| `platform.audit.read` | read cross-tenant audit | platform admin / compliance |
| `platform.support` | read-only support bundle (JIT elevation) | platform support |

## Seeding strategy (minimal, Phase 2)

Seed per tenant at creation time:

| Seed role | Intent | Included permissions (suggested) |
|-----------|--------|----------------------------------|
| `tenant-admin` | full tenant admin | `tenant.*`, `resource.*`, `audit.read` |
| `resource-admin` | resource operations | `resource.*`, `resource.allocation.*` |
| `viewer` | read-only | `tenant.read`, `resource.read` |

### Platform operator seed roles (install / bootstrap)

| Seed role | Intent | Included permissions (suggested) |
|-----------|--------|----------------------------------|
| `platform-admin` | full platform ops | `platform.admin`, `platform.audit.read` |
| `platform-governance` | marketplace governance | `platform.vendor.verify`, `platform.plugin.approve` |
| `platform-support` | read-only support | `platform.tenant.read`, `platform.support` |

Assign only to users in `PlatformOperatorOrganization`. See [management plane](../architecture/management-plane.md).

## Audit requirements

Audit all of the following:

- Role created/updated/deprecated
- Permission added/deprecated (rare)
- Role-permission assignment changes
- User-role assignment changes
- Authorization failures for sensitive actions (rate-limited to avoid log floods)
- All `platform.*` grants and revocations (high sensitivity)
- Platform scope checks on admin API (allow and deny)

## Security considerations

| Risk | Mitigation |
|------|------------|
| Privilege escalation by direct role edits | protect role/assignment endpoints with `tenant.admin` |
| Confused deputy across tenants | always pass/require `tenant_id` in RBAC queries and routes |
| Token staleness | do not embed roles in JWT |
| Enumeration of roles/users | scope list endpoints to tenant and restrict by permission |
| Customer token on admin API | separate ingress + reject `platform.*` checks without operator org membership |
| Platform permissions on public API | public middleware denies routes requiring `platform.*` |

## Related documentation

- [Management plane](../architecture/management-plane.md)
- [Tenant domain](tenant-domain.md) — `PlatformOperatorOrganization`
- [Identity domain](identity-domain.md) — operator Keycloak client and bootstrap


