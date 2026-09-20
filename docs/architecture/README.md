# Architecture documentation

## Start here

- **System overview 2** (collective detailed overview): [`system-overview2.md`](system-overview2.md)
- **Marketplace platform master** (canonical index, phases A–E): [`marketplace-platform-master.md`](marketplace-platform-master.md)
- **System overview** (tenant control-plane, consumer + vendor model, Keycloak org realms): [`system-overview.md`](system-overview.md)
- **Management plane** (platform admin, bootstrap, VPN/zero-trust, admin API): [`management-plane.md`](management-plane.md)
- **Phase 2 foundation** (minimal implementation scope): [`phase2-foundation-overview.md`](phase2-foundation-overview.md)
- **Phase 2 backend structure** (module layout + marketplace/billing/metering): [`phase2-backend-structure.md`](phase2-backend-structure.md)
- **Full DDD evolution** (blueprint: current → tactical DDD; docs only): [`full-ddd-evolution.md`](full-ddd-evolution.md)

## Domains (bounded contexts)

- Tenant: [`docs/domains/tenant-domain.md`](../domains/tenant-domain.md)
- Identity: [`docs/domains/identity-domain.md`](../domains/identity-domain.md)
- Resource: [`docs/domains/resource-domain.md`](../domains/resource-domain.md)
- Authorization (RBAC): [`docs/domains/authorization-domain.md`](../domains/authorization-domain.md)
- Vendor / plugin marketplace: [`docs/domains/vendor-plugin-domain.md`](../domains/vendor-plugin-domain.md)
- Billing: [`docs/domains/billing-domain.md`](../domains/billing-domain.md)
- Metering: [`docs/domains/metering-domain.md`](../domains/metering-domain.md)

## Workflows

- Resource allocation: [`docs/workflows/resource-allocation.md`](../workflows/resource-allocation.md)
- Authentication: [`docs/workflows/authentication-flow.md`](../workflows/authentication-flow.md)
- Vendor plugin E2E: [`docs/workflows/vendor-plugin-e2e-acme-metrics.md`](../workflows/vendor-plugin-e2e-acme-metrics.md)
- Marketplace tenant lifecycle: [`docs/workflows/marketplace-tenant-lifecycle.md`](../workflows/marketplace-tenant-lifecycle.md)

## Diagrams

- ER model: [`docs/diagrams/er-diagram.md`](../diagrams/er-diagram.md)
- Allocation sequence: [`docs/diagrams/allocation-sequence.md`](../diagrams/allocation-sequence.md)
- Marketplace context: [`docs/diagrams/marketplace-platform-context.md`](../diagrams/marketplace-platform-context.md)
- Commercial flow: [`docs/diagrams/marketplace-commercial-flow.md`](../diagrams/marketplace-commercial-flow.md)

## Decisions

- Index: [`docs/decisions/README.md`](../decisions/README.md)
