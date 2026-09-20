# Phase 2 ER diagram (minimal foundation)

```mermaid
erDiagram
  Organization ||--o{ Tenant : owns
  Tenant ||--o{ TenantMembership : has
  User ||--o{ TenantMembership : member

  Tenant ||--o{ Role : defines
  Role ||--o{ RolePermission : includes
  Permission ||--o{ RolePermission : granted

  User ||--o{ UserRole : assigned
  Tenant ||--o{ UserRole : scopes
  Role ||--o{ UserRole : assigns

  Tenant ||--o{ Quota : limits
  Tenant ||--o{ Resource : owns
  Tenant ||--o{ ResourceAllocation : requests
  ResourceAllocation ||--o| Resource : creates

  Tenant ||--o{ AuditLog : records
  User ||--o{ AuditLog : actor
```

## Notes for implementation planning

- `User` is global (no `tenant_id`) because a user can belong to multiple tenants.
- `Permission` is global catalog; `Role` is tenant-scoped.
- `AuditLog.tenant_id` is nullable for global actions; most entries will be tenant-scoped.

