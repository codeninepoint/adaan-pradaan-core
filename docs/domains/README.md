# Domains

This folder contains one document per **bounded context**. Each domain doc should cover:

- Business responsibility
- Bounded context boundary (what it owns / does not own)
- Aggregates/entities and key invariants
- Security and audit considerations
- Integration points (events, ACLs)

## Core platform docs (aligned)

| Domain | Doc | Focus |
|--------|-----|-------|
| Platform overview | [system overview](../architecture/system-overview.md) | Consumer + vendor control-plane, org types, Keycloak |
| Tenant | [tenant-domain.md](tenant-domain.md) | Organization (`individual` \| `organization`), tenants, registration journeys |
| Identity | [identity-domain.md](identity-domain.md) | Users, Keycloak realms, credentials, org realm provisioning |
| Authorization | [authorization-domain.md](authorization-domain.md) | Basic RBAC (Phase 2) |
| Resource | [resource-domain.md](resource-domain.md) | Resources, quotas, allocations |
| Vendor / plugin | [vendor-plugin-domain.md](vendor-plugin-domain.md) | Marketplace, plugins, provisioning |
| Billing | [billing-domain.md](billing-domain.md) | Plans, subscriptions, invoice preview |
| Metering | [metering-domain.md](metering-domain.md) | Meters, usage events, aggregation |

## Read order (new contributors)

1. [System overview 2](../architecture/system-overview2.md)
2. [Marketplace platform master](../architecture/marketplace-platform-master.md)
3. [System overview (Phase 1)](../architecture/system-overview.md)
4. [Identity domain](identity-domain.md) + [Tenant domain](tenant-domain.md)
5. [Vendor plugin domain](vendor-plugin-domain.md) + [Billing](billing-domain.md) + [Metering](metering-domain.md) (marketplace commercial path)
6. [Phase 2 foundation](../architecture/phase2-foundation-overview.md) (implementation)
