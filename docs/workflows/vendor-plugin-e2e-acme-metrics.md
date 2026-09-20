# Workflow: Vendor plugin E2E (Acme Metrics)

End-to-end reference journey for **Acme Metrics** — a metrics export integration plugin. Demonstrates plugin-first marketplace with subscription + usage.

## Actors

| Actor | Org | Role |
|-------|-----|------|
| Acme vendor user | `organization` vendor | `vendor.plugin.register`, publish |
| Platform operator | Platform operator org | `platform.plugin.approve` |
| Consumer user | `individual` consumer | install, provision |

## Journey map

```mermaid
flowchart LR
  V1[RegisterPlugin] --> V2[SubmitVersion]
  V2 --> P1[PlatformApprove]
  P1 --> D1[AutoDiscovery]
  D1 --> C1[PublishProductOffering]
  C1 --> T1[TenantBrowseInstall]
  T1 --> T2[ProvisionResource]
  T2 --> M1[EmitUsage]
```

## Phase 1 — Vendor plugin

1. Vendor org opts into `vendor` participation.
2. `POST /v1/vendor/plugins` — register `ServicePlugin` (`code: acme.metrics`).
3. `POST /v1/vendor/plugins/{id}/versions` — submit manifest + artifact ref.
4. Management plane: operator approves version → `published`.

**Manifest excerpt:**

```json
{
  "capabilities": [
    {
      "code": "metrics.export",
      "operations": ["provision", "deprovision", "status"]
    }
  ],
  "meters": [
    { "code": "acme.metrics.active_integration_hours", "granularity": "time", "unit": "hour" },
    { "code": "acme.metrics.ingested_samples", "granularity": "usage", "unit": "count" }
  ]
}
```

## Phase 2 — Auto discovery

On approve:

- Capabilities indexed in discovery catalog.
- Adapter route registered (`stub://acme.metrics/v1`).
- Meters registered in Metering catalog.

## Phase 3 — Marketplace catalog

1. `POST /v1/vendor/products` — `Product` bound to plugin.
2. `POST /v1/vendor/offerings` — `MarketplaceOffering` with `plan_id` + `meter_codes`.
3. Platform publishes listing (public catalog read).

## Phase 4 — Tenant request

1. Consumer browses `GET /v1/marketplace/offerings`.
2. `POST /v1/tenants/{tenant_id}/entitlements` — install offering.
3. Billing creates `Subscription` (`trialing` if trial configured).
4. `POST /v1/tenants/{tenant_id}/provisioning` — provision via adapter.
5. Resource domain creates `Resource` linked to entitlement.

## Phase 5 — Metering and billing

| Event | Usage |
|-------|-------|
| Provision success | `acme.metrics.ingested_samples` quantity=0 (activation) |
| Daily scheduler | `active_integration_hours` += 24 while entitlement active |
| Adapter callback (future) | sample ingest counts |

Billing aggregates events for invoice preview at period end.

## API summary (reference)

| Step | API |
|------|-----|
| Register plugin | `POST /v1/vendor/plugins` |
| Submit version | `POST /v1/vendor/plugins/{id}/versions` |
| Approve (mgmt) | `POST /v1/admin/plugins/versions/{id}/approve` |
| Publish offering | `POST /v1/vendor/offerings` |
| Install | `POST /v1/tenants/{tid}/entitlements` |
| Provision | `POST /v1/tenants/{tid}/provisioning` |

## Related

- [vendor-plugin-domain.md](../domains/vendor-plugin-domain.md)
- [marketplace-tenant-lifecycle.md](marketplace-tenant-lifecycle.md)
- [marketplace-commercial-flow.md](../diagrams/marketplace-commercial-flow.md)
