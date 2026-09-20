# Diagram: Marketplace platform context (C4)

System context for the general multi-tenant marketplace control-plane.

## Context diagram

```mermaid
flowchart TB
  subgraph external [ExternalActors]
    Consumer[ConsumerUser]
    Vendor[VendorUser]
    PlatOp[PlatformOperator]
  end

  subgraph platform [MarketplaceControlPlane]
    PublicAPI[PublicAPI]
    AdminAPI[ManagementAPI]
    subgraph modules [BoundedContexts]
      Identity[Identity]
      Tenant[Tenant]
      AuthZ[Authorization]
      Resource[Resource]
      Market[Marketplace]
      Bill[Billing]
      Meter[Metering]
    end
  end

  subgraph data [DataPlane]
    PG[(PostgreSQL)]
    KC[Keycloak]
  end

  Consumer --> PublicAPI
  Vendor --> PublicAPI
  PlatOp --> AdminAPI
  PublicAPI --> Identity
  PublicAPI --> Tenant
  PublicAPI --> AuthZ
  PublicAPI --> Resource
  PublicAPI --> Market
  PublicAPI --> Bill
  PublicAPI --> Meter
  AdminAPI --> Market
  AdminAPI --> Tenant
  Identity --> KC
  modules --> PG
```

## Container notes

| Container | Responsibility |
|-----------|----------------|
| Public API | Tenant-scoped customer + vendor routes |
| Management API | Platform RBAC only; private network |
| PostgreSQL | System of record |
| Keycloak | Authentication realms |

## Trust boundaries

- Public ingress never routes to Admin API.
- `platform.*` permissions evaluated only on management plane.
- Plugin adapters (stub → HTTP/gRPC) run behind platform dispatch.

## Related

- [marketplace-platform-master.md](../architecture/marketplace-platform-master.md)
- [system-overview.md](../architecture/system-overview.md)
