# Architecture decisions (ADRs)

This folder holds Architecture Decision Records and Implementation Decision Records.

## Records

| ID | Title |
|----|-------|
| [IDR-002](idr-002-identity-authz-schema.md) | Identity & Authorization schema (principals-centric) |

## Suggested Phase 1 ADRs to add next

- D1: Modular monolith with bounded contexts
- D2: Org → Tenant → Project hierarchy
- D3: Shared PostgreSQL + `tenant_id` + RLS as default isolation
- D4: Tenant membership separate from RBAC role bindings
- D5: Allocation as an aggregate (quota reservation + provisioning lifecycle)
- D6: Lean JWT; authorization evaluated per request
- D7: Outbox pattern for cross-context integration
