# Cashfree Payment Gateway

Marketplace checkout collects INR via Cashfree PG (or a local stub). Orders stay `awaiting_payment` until a verified webhook (or stub simulate) marks them paid.

## Provider modes

| `TENANT_PAYMENTS_PROVIDER` | Behaviour |
| --- | --- |
| `stub` (default) | No Cashfree credentials. Checkout creates a session; UI calls `/payment/simulate` to capture. |
| `cashfree` | Live Create Order against sandbox or production; browser opens Cashfree Checkout JS. |

## Environment

```bash
TENANT_PAYMENTS_PROVIDER=cashfree
TENANT_CASHFREE_ENV=sandbox          # or production
TENANT_CASHFREE_APP_ID=…             # x-client-id
TENANT_CASHFREE_SECRET_KEY=…         # x-client-secret (never expose to UI)
TENANT_CASHFREE_API_VERSION=2025-01-01
TENANT_CASHFREE_WEBHOOK_SECRET=…     # optional; falls back to secret key
TENANT_CASHFREE_RETURN_URL_BASE=http://localhost:3000
```

Sandbox API: `https://sandbox.cashfree.com/pg`  
Production API: `https://api.cashfree.com/pg`

## Endpoints

- `POST /api/v1/tenants/{tenant_id}/checkout/sessions` — create order + payment session
- `GET /api/v1/tenants/{tenant_id}/orders/{order_id}/payment` — poll status after return
- `POST /api/v1/tenants/{tenant_id}/orders/{order_id}/payment/simulate` — stub/dev capture
- `POST /api/v1/webhooks/cashfree/payments` — Cashfree notify URL (HMAC verified)
- `GET /api/v1/payments/config` — public `{ provider, cf_env, cashfree_app_id }`

Legacy `POST /tenants/{id}/orders` remains for stub/tests only; Cashfree mode rejects it.

## Webhook setup (sandbox)

1. Point Cashfree webhook (and/or `order_meta.notify_url`) to a tunnel, e.g. `https://<ngrok>/api/v1/webhooks/cashfree/payments`.
2. Subscribe to payment success / failed / user dropped.
3. Signature: `Base64(HMAC-SHA256(timestamp + rawBody, secret))` using `x-webhook-timestamp` + `x-webhook-signature`.

## Refunds

Vendor reject slice and return refund APIs call Cashfree refunds when a `payment_intent` exists (`refund_method=original`). Stub provider records a synthetic refund id.

## UI flow

Checkout modal → create session → stub simulate **or** Cashfree JS checkout → return to `/app/marketplace/orders?payment=return&order_id=…` → poll payment status.
