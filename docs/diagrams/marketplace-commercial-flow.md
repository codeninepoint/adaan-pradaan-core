# Diagram: Marketplace commercial flow (subscription + usage)

Sequence for install → provision → meter → rate.

## Sequence

```mermaid
sequenceDiagram
  actor Consumer
  participant API as PublicAPI
  participant Mkt as Marketplace
  participant Bill as Billing
  participant Prov as Provisioning
  participant Adpt as PluginAdapter
  participant Meter as Metering
  participant Res as Resource

  Consumer->>API: POST entitlements
  API->>Mkt: create Entitlement
  Mkt->>Bill: create Subscription trialing_or_active
  Bill-->>API: subscription_id

  Consumer->>API: POST provisioning
  API->>Prov: ProvisioningRequest
  Prov->>Adpt: provision
  Adpt-->>Prov: success metadata
  Prov->>Res: create Resource
  Prov->>Meter: emit UsageEvent idempotent

  Note over Meter: daily scheduler for time meters

  Meter->>Bill: period aggregation export
  Bill->>API: invoice preview
  Consumer->>API: GET invoice-preview
```

## Data touched

| Step | Tables / entities |
|------|-------------------|
| Install | `entitlements`, `subscriptions` |
| Provision | `provisioning_requests`, `resources` |
| Meter | `usage_events` |
| Bill | `usage_aggregations`, `invoice_preview` |

## Commercial states

Entitlement and subscription align on install and revoke. See billing domain state diagram in [billing-domain.md](../domains/billing-domain.md).

## Related

- [marketplace-tenant-lifecycle.md](../workflows/marketplace-tenant-lifecycle.md)
- [vendor-plugin-e2e-acme-metrics.md](../workflows/vendor-plugin-e2e-acme-metrics.md)
