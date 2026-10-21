# Rekvero — Codex handoff, 14.10.2026

## Scope and evidence

This package is an **offline prototype**, not the production repo. Its actual code is `index.html`; no API, auth, persistence, LLM, or campaign changes are available. Prior requirements in `CODEX_MASTER_PLAN.md` express intent and are NOT proof of implementation. Do not treat previously discussed PR numbers, release gates, or readiness claims as currently verified. Inspect Git repository and active branch yourself before touching production code.

## Completed inside THIS package (v3)

1. Retained landing, hero, demo cabinet with five pages, three theme choices and adaptive layouts.
2. Consolidated duplicate trust content into the methodology section and repaired the header anchor.
3. Added accessible, native-details FAQ about integrations, actions, insufficient data and trial.
4. Fixed confirmation flow so canceling a status change returns focus to the recommendation drawer rather than dismissing the entire context.
5. Removed misleading positive confirmation from connection information dialogs (no OAuth performed).
6. Search input now filters already rendered recommendation cards without recreating or refocusing the input on each keystroke. Result count updates; filter resets and select filters still render.
7. The status label now uses the shared map of all eight demo statuses instead of generic placeholder text.
8. Demo profile name and demo notification checkbox now persist during SPA navigation **in memory only**; nothing is sent to a server and values reset when the page reloads.
9. Static checks in `verify_static.py` verify JavaScript syntax, unique IDs, internal anchors, dialog labels, and feature markers.

## Known limitations of this prototype

- Status transition simulation deliberately permits states that would be forbidden in production. UI demo is NOT an authoritative state machine.
- History resides in JavaScript memory only; has no user identity, immutable audit storage, timestamps, signature or evidence versioning.
- Chart is illustrative; no measurement, tooltip drill-down, campaign API or verified ad data.
- Browser E2E, screenshots, Lighthouse, WCAG audit and screen-reader testing were **not completed** in this turn. Static checks are not substitutes.
- Embedded single-file JavaScript/HTML string rendering is not an appropriate final architecture for the React/Next project.
- The landing page has no live trial signup, payment, public customer testimonials, privacy/legal production review, or verified integration support.
- Local system/browser permissions can restrict external Google Fonts; local fallbacks exist.
- Mobile menu is visually compact but not fully usability-tested on physical devices.

## Must-do — Codex P0 / prior to real customer access

### P0-00: Audit first, then reconcile

- Collect: current branch and SHA; `git status`, open PRs, CI history, `frontend` routes/components, `backend` services/workers, database migrations, API spec, auth, RLS, feature flags, tests, security and release docs.
- Build `IMPLEMENTATION_MATRIX.md` for each feature: **implemented / partial / missing / unverified / blocked**, with file:line or test references. Verify whether previous fixes/PRs already did work; do not reproduce or overwrite.
- Inspect secrets only by safe presence/config checks, never print values.
- Never merge/deploy/push without owner approval.

### P0-01: Truthful metrics and coherent context

- Central metric registry: definition, unit, source, window, timezone, aggregation, attribution, freshness, data status (`actual / estimated / unavailable`; plus completeness/reason).
- Direct campaign conversions and agreed conversion definition; Metrika diagnostic comparison, not an interchangeable sum. Audit cross-channel denominator compatibility.
- Keep `insufficient` separate from numeric 0; avoid `float` for money. Confirm settled/delayed conversions and provisional recent-day policy.
- After account/date changes, abort or discard stale requests; tenant/account/period must remain consistent across **all** tabs.
- Test: missing conversions, 0 genuinely observed conversions, low sample, overlapping loss estimates, attribution mismatch, conversions still settling, invalid currency, 30-day baselines and boundary CPA thresholds.

### P0-02: Auth, tenant isolation and integration safety

- Server-side permissions and tenant isolation for every account/endpoint/resource; test horizontal authorization and cache isolation.
- Secure email/password (as currently decided unless repo docs differ); session protection, CSRF, rate-limits, reset flow. Audit 152-FZ compliance with counsel.
- OAuth token storage server-side; validate state/callback/scopes; explicit reauth/revocation; track auth, sync and data availability separately.
- Show integration support exactly matching verified implemented capabilities; no fabricated available channels.

### P0-03: Recommendation lifecycle and safe actions

- Model: `new / requires_decision / approved / applied / postponed / rejected / failed / cancelled` plus separate `execution_mode`, `execution_status`, `verification_status`, `rollback_status`.
- Implement server-controlled legal transitions, idempotency and immutable audit log; mutation actions demand confirmation, authorization and explainable evidence.
- No implicit API apply on approval. No active AI-LLM on real client data before legal/security approval.
- Write tests covering concurrent approvals, retries, stale recommendations, failed apply, verification mismatch, rollback, permission revocation and duplicate submissions.

### P0-04: Reliable data sync

- Incremental pulls, refresh/expiry handling, retry with backoff, job idempotency, observable partial failures, last successful sync, per-account health.
- No synthetic numbers or hardcoded conversion values outside an isolated demo fixture boundary.
- Do not claim causal money saved without controlled evidence.

## P1 — high-value product/UX, parallel only after relevant contracts verified

1. Port tokens, components, responsive layout and theme handling into existing frontend stack. Do not transplant `innerHTML` string renderer; use accessible typed UI primitives. Preserve existing routing.
2. Landing: strong Russian offer; responsive interactive demo with explicit fake-data label; FAQ, methodology, capability statuses, correct trial/tier labels, privacy and legal links; never assert fabricated social proof.
3. Analysis: Summary → metrics → chart(s) → changes → budget concerns → campaigns, with metric provenance, skeleton/empty/error/stale states, filters encoded in URL as appropriate, units and axes labeled, drill-down.
4. Recommendations: real filters/search/pagination, detail evidence drawer, status timeline, allowed decisions; loading/errors and mutation feedback.
5. Effect: applied/verified changes, before/after measured observations, only prove economics where justified; otherwise ‘insufficient’.
6. Connections: authentication, scopes, last sync, errors, reconnect/remove actions; correct copy per integration.
7. Settings: persistent server profile, analytics thresholds and goal attribution, preferences, notification permissions, security; unsaved-change protection.
8. 7-day trial and tier display consistent with verified entitlement/payment lifecycle. Hide price for unapproved Business/Business+ tiers.

## P2 — polish / scalability

- Animate meaningfully (tab 180–220ms; drawer 240–300ms; modal 180–240ms; chart updates ~350–550ms) and respect reduced motion.
- Visual regression both themes 320/390/768/1280/1440 widths; usability and screen-reader audits, contrast WCAG 2.2 AA; menu on phone.
- Optimize render stability, loading, chart point count and long table virtualization; target CWV LCP <=2.5s, INP <=200ms, CLS <=0.1 (measure field data).
- SEO structured metadata only with confirmed canonical domain and published capabilities.
- Optional Chief Analyst with channel-specific deterministic analyzers; keep model explanations evidence-bound and legal-gated.

## Recommended PR order

0. Discovery/report only (no refactor) → 1. Metric/data-safety gaps → 2. Auth/integrations safety gaps → 3. Recommendation workflow → 4. Real sync/effect → 5. Shared design tokens/themes → 6. Landing → 7. Remaining five screens → 8. E2E/security/a11y/performance/launch checks.

Existing PRs may cover these already. Reorder based on dependencies and evidence. Require scoped diff, tests, screenshots, rollback notes, no unapproved merge.

## Acceptance criteria for each feature

- Reproducible manual test steps, unit/integration/E2E coverage, clean build/lint/typecheck, screenshot evidence light/dark/phone, errors/loading/empty states, accessibility keyboard + focus, server authorization tests for account operations.
- User can trace each displayed production metric to verifiable source and timestamp; no synthetic production values.
- Operator can see exact lifecycle from suggestion to action to verification, without mismatched states.
- On each PR: report paths changed, tests executed and outcomes, unverified areas, risk and rollback.

## Codex execution prompt

Inspect the existing Rekvero repository and `CODEX_MASTER_PLAN.md`, `CODEX_HANDOFF_V3.md`, `index.html`. Treat `index.html` strictly as a visual interaction reference and not an API/business-logic source. First produce evidence-backed implementation matrix comparing current code with handoff. Resolve existing implementation, tests, docs and PRs before editing. Fix P0 failures first. For each change create a minimal branch/PR with tests, screenshots in both themes, migration/rollback notes; do not push/merge/deploy without explicit approval, do not put real secrets or client data into third-party LLMs, do not invent any advertising numbers. Explicitly report any features that remain unverified.
