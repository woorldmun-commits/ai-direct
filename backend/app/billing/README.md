# F04: one workspace purchase

This integration is disabled by default. It creates no merchant account, sends no payment automatically, and stores no card details. The purchase grants 30 days plus the existing three-day grace period; automatic renewal is always false. Existing subscriptions retain their plan codes and prices. An active paid period cannot be upgraded or renewed early in this first version.

## Runtime integration

Migrations 0012/0013, API routes, frontend checkout and public callback relay are integrated. New migrations must stay aligned with `backend/db/schema.sql` and `backend/migrations/released.txt`. Released migrations remain immutable.

The public site provides the exact public POST relay `/api/billing/yookassa/webhook` to backend `/api/v1/billing/yookassa/webhook`, because the backend is bound to loopback. Bound the body, preserve the backend response status, forward no cookies, and use a fixed upstream. Only that backend POST is exempt from browser Origin validation; payment mutations still require session, owner/admin role, workspace access and approved Origin. Configure the public relay URL in the YooKassa merchant cabinet.

## Frontend API

All paths below are backend paths under `/api/v1`; frontend proxies may omit `/v1`.

- `GET /billing/plans`: `{items:[{id,name,plan,amount_minor,accounts}],unit:'workspace',currency:'RUB',period_days:30,grace_days:3,auto_renew:false,checkout_enabled,test,terms_sha256}`. Amounts are integers. Plan IDs are `control/business/agency`; persisted codes are `start/business/business_plus`. Capacity is per workspace, not pooled across an organization.
- After explicit acceptance of the exact offer text, `POST /workspaces/ws_N/billing/orders` with `{request_id:UUID,sku,terms_sha256}` reserves an order. Persist that UUID before this request. The response is `{id,sku,status,amount_minor,currency,test,period_days:30,grace_days:3,auto_renew:false}`. This request never calls the processor. It must complete before checkout begins so its order is committed durably.
- `POST /workspaces/ws_N/billing/orders/{id}/checkout` creates or recovers the same provider payment. Response adds `confirmation_url`, or returns a terminal/review status. Only HTTPS URLs with exact host `yoomoney.ru` or `yookassa.ru`, no credentials and no nonstandard port are accepted. No card form belongs in the application.
- `POST /workspaces/ws_N/billing/orders/{id}/refresh` retrieves the current processor state. Use after returning from hosted checkout or when recovering a timeout. The redirect itself provides no proof of payment. Refresh subscription details after order status becomes `succeeded`.

`GET /workspaces/ws_N/billing/orders/current` recovers the outstanding order for an owner/admin without browser storage, including its original UUID, SKU and terms hash; no receipt or email is returned. A definitive `billing_terms_changed` response before reservation permits discarding the unreserved attempt and obtaining new consent.

Keep the same UUID, SKU and terms hash across retries/reloads. Never create a new order because the processor timed out. `billing_provider_unavailable` is 503 and may mean that a payment was already created; retry the same order. Unknown creation older than 24 hours is `billing_reconciliation_required` (409) and needs operator review, because the provider's idempotency guarantee expires. `billing_order_pending` blocks a second outstanding order; `billing_existing_subscription` blocks an active paid period; `billing_terms_changed` means the currently offered document differs. `review_required` never grants new access.

## Operator configuration

Set these only after account, receipt setup and document review are complete:

```
INROU_BILLING_ENABLED=1
INROU_BILLING_LEGAL_APPROVED=1
INROU_BILLING_ORIGIN=https://your-approved-site.example
INROU_BILLING_TERMS_SHA256=<sha256 of the exact approved offer>
YOOKASSA_SHOP_ID=<merchant shop ID>
YOOKASSA_SECRET_KEY=<secret outside repository>
YOOKASSA_TEST_MODE=1
YOOKASSA_VAT_CODE=<approved receipt VAT code>
YOOKASSA_TAX_SYSTEM_CODE=<approved tax system code>
YOOKASSA_PAYMENT_SUBJECT=<service or intellectual_activity as approved>
YOOKASSA_PAYMENT_MODE=<full_payment or full_prepayment as approved>
```

The Settings constructor additionally requires the offer hash to match both the latest published backend text and `API_SIGNUP_APPROVED_HASHES.offer`; bundled draft texts are rejected.

Live mode additionally requires `YOOKASSA_TEST_MODE=0` and `INROU_BILLING_LIVE_APPROVED=1`. Enabled but incomplete configuration fails startup. The billing origin must be an allowed API origin. Legal/fiscal flags are an operator attestation, not a legal opinion or proof of successful merchant onboarding. Test-mode purchases grant access only where that test merchant configuration is explicitly enabled; never enable it against real customer workspaces.

## Failure recovery and finance

Every fulfillment verifies a current authenticated GET against amount, RUB, merchant, test/live mode, provider ID and server-created order/workspace metadata. The order, payment, paid event, subscription and completion marker commit together. Callback response 200 happens after this commit; errors remain eligible for provider redelivery. All writes serialize with workspace deletion and duplicate fulfillment. Receipt request email is retained only in the pending immutable request snapshot. Success/cancellation/review clears it; dedicated retention removes snapshots older than 24 hours in bounded audited batches (normal daily scheduling means up to one extra interval). Unknown creating orders then require operator reconciliation, and cannot be recreated after the idempotency window. Pending payments with a known provider ID still reconcile by authenticated GET. Workspace deletion clears request email automatically. Deleted workspaces retain only an anonymized order tombstone.

Refunds are initiated manually in the merchant cabinet. A verified full or partial refund records the exact refund amount, revokes only the linked subscription, and marks the order for operator review. There is no refund API, automatic refund decision or partial-access restoration. The approved offer and runbook must account for that policy before enabling billing.

Schedule `python -m app.billing.reconcile` daily with `WORKER_QUEUE_DATABASE_URL` for role `app_system` and the billing configuration. It makes authenticated GET requests only, repairs known pending fulfillments, and reports purchase/ledger discrepancies with a nonzero exit status. Scheduling and alert delivery are deployment tasks; this module does not install a scheduler. Never blindly recreate an order whose provider ID is unknown after the 24-hour window; reconcile its metadata in the merchant cabinet first.

`reconciliation.sql` compares purchases and their payment records. It does **not** establish payout/settlement equality: fees, settlement reports and the merchant's bank account require a separate finance import and a verified payout-to-ledger comparison before commercial launch. Merchant test cards, a real sandbox callback, actual receipt registration, live consent texts, provider outages, dispute deadlines and payout reconciliation remain operator acceptance checks. No such external verification was performed here.

Official contracts: [idempotency and uncertain errors](https://yookassa.ru/developers/using-api/interaction-format), [notifications and current-object verification](https://yookassa.ru/developers/using-api/webhooks).
