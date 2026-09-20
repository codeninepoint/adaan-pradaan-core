# Docs

## Architecture

- Entry point: [`docs/architecture/README.md`](architecture/README.md)
- **System overview 2** (collective platform reference — start here): [`docs/architecture/system-overview2.md`](architecture/system-overview2.md)
- **Marketplace platform master** (canonical roadmap, phases A–E): [`docs/architecture/marketplace-platform-master.md`](architecture/marketplace-platform-master.md)
- System overview (tenant control-plane, consumer + vendor, Keycloak org realms): [`docs/architecture/system-overview.md`](architecture/system-overview.md)
- Management plane (platform operator, bootstrap, internal admin API): [`docs/architecture/management-plane.md`](architecture/management-plane.md)
- Phase 2 foundation + backend structure: [`docs/architecture/phase2-foundation-overview.md`](architecture/phase2-foundation-overview.md), [`docs/architecture/phase2-backend-structure.md`](architecture/phase2-backend-structure.md)
- Full DDD evolution (blueprint, docs only): [`docs/architecture/full-ddd-evolution.md`](architecture/full-ddd-evolution.md)

## Backend (journey-driven implementation)

- Identity Phase 1 (J1–J6): [`src/identity/ARCHITECTURE.md`](../src/identity/ARCHITECTURE.md)
- User journeys: [`docs/User_Journeys/Adanpradan_identity_auth_journeys.md`](User_Journeys/Adanpradan_identity_auth_journeys.md), [`docs/User_Journeys/02_Tenant_Vendor_Plugin_Journeys.md`](User_Journeys/02_Tenant_Vendor_Plugin_Journeys.md)
- OpenAPI export: [`openapi/identity-phase1.json`](../openapi/identity-phase1.json)

## Domains

- Index: [`docs/domains/README.md`](domains/README.md)
- Tenant (org types, Keycloak realm ref, vendor participation): [`docs/domains/tenant-domain.md`](domains/tenant-domain.md)
- Identity (Keycloak, user registration, org realms): [`docs/domains/identity-domain.md`](domains/identity-domain.md)
- Resource: [`docs/domains/resource-domain.md`](domains/resource-domain.md)
- Authorization (RBAC): [`docs/domains/authorization-domain.md`](domains/authorization-domain.md)
- Vendor / plugin marketplace: [`docs/domains/vendor-plugin-domain.md`](domains/vendor-plugin-domain.md)
- Billing (plans, subscriptions): [`docs/domains/billing-domain.md`](domains/billing-domain.md)
- Metering (meters, usage events): [`docs/domains/metering-domain.md`](domains/metering-domain.md)

## Workflows

- Index: [`docs/workflows/README.md`](workflows/README.md)
- Resource allocation: [`docs/workflows/resource-allocation.md`](workflows/resource-allocation.md)
- Authentication: [`docs/workflows/authentication-flow.md`](workflows/authentication-flow.md)
- Vendor plugin E2E (Acme Metrics): [`docs/workflows/vendor-plugin-e2e-acme-metrics.md`](workflows/vendor-plugin-e2e-acme-metrics.md)
- Marketplace tenant lifecycle: [`docs/workflows/marketplace-tenant-lifecycle.md`](workflows/marketplace-tenant-lifecycle.md)

## Diagrams

- Index: [`docs/diagrams/README.md`](diagrams/README.md)
- ER model: [`docs/diagrams/er-diagram.md`](diagrams/er-diagram.md)
- Allocation sequence: [`docs/diagrams/allocation-sequence.md`](diagrams/allocation-sequence.md)
- Marketplace platform context (C4): [`docs/diagrams/marketplace-platform-context.md`](diagrams/marketplace-platform-context.md)
- Marketplace commercial flow: [`docs/diagrams/marketplace-commercial-flow.md`](diagrams/marketplace-commercial-flow.md)

## Design

- Index: [`docs/design/README.md`](design/README.md)
- Auth UI (Login, Register, session): [`docs/design/auth-screens.md`](design/auth-screens.md)
- Theme tokens (Control Plane Neutral): [`docs/design/theme-control-plane-neutral.md`](design/theme-control-plane-neutral.md)

## Decisions

- Index: [`docs/decisions/README.md`](decisions/README.md)

