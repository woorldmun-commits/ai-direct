---
name: inrou-evidence-ui
description: Use when implementing INROU KPI cards, AI-analyst, Data Health, recommendation detail and effect/verification workflows.
---

1. Read latest product contracts and the existing API/data models first. Check values are actual, estimated or unavailable with source, period, and freshness.
2. Never turn unknown values into zero or fictitious results. Distinguish illustrative demo state explicitly.
3. AI replies must show source references and arithmetic explanations only when actual evidence exists; otherwise disclose limitations.
4. Recommendation detail shows reasons, evidence, formula, risks, status, decision buttons and manual execution/verification; require server-backed permission/validation/idempotency for persisted actions.
5. No automatic advertising changes, no Telegram and no fabricated economic benefit.
6. Test malformed/missing/stale data, zero conversions, disconnected source, forbidden role, concurrent decision and failed verification.
