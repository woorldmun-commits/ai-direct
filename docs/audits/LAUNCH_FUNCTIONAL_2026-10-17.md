# Functional launch review — 2026-10-17

## Result

**Production launch: NO-GO until external setup is complete.** The owner confirmed no domain, hosting, operator details, OAuth application, or production database are available. No production credentials, legal approvals, sessions, workspaces, advertising connections, payments, or data were fabricated.

## Implemented public journey

- Landing action enters `/login` (landing changes owned by the design reviewer).
- `/login` requests real Yandex ID authorization through same-origin `POST /api/auth/yandex/start`. Existing accounts can enter without repeating consent. Registration controls are hidden until the backend publishes both exact approved documents and their UTF8 SHA256 hashes validate. Creating an account then requires separate, initially unchecked offer and personal-data consent controls. Their versions are explicitly sent to the backend for hash approval and persisted acceptance checks. Incomplete selection prevents submission.
- Yandex redirects to `/api/auth/yandex/callback`. The proxy forwards only bounded state/code/error values and the dedicated encrypted flow cookie. Backend verifies flow and exchanges the code; the browser receives an HttpOnly session cookie and a relative redirect to `/workspace`.
- `/workspace` reads the actual API on the server: `/me`, authorized workspace `/today`, and paginated `/recommendations`. Runtime validators reject invalid amounts, dates, identifiers, metadata, or list shapes. No fixture or model store is imported by these public routes.
- Missing, expired, or revoked sessions redirect to login when the API is configured. Configuration failure, unavailable upstream, unauthorized workspace, malformed cursor, missing workspace membership, and empty real data each have explicit states. No synthetic figures replace missing data.
- Logout posts to the backend revocation endpoint through the same-origin proxy.
- All former `/demo` page routes and their layout redirect to `/workspace`; onboarding leads to the same real workspace; signup leads to login. Public Prisma prototype route redirects home.

## Trust boundaries

- API origin comes only from server `REKVERO_API_URL`; credentials, paths, query, fragments, and non-HTTPS remote origins are rejected. Session cookie name is validated; session values remain on the server. Backend GETs use `no-store`, fixed path allowlist, redirect refusal, 8-second timeout, and a 1 MiB stream cap.
- Auth proxy supports exactly three paths and their allowed HTTP methods. POST Origin must equal the incoming site origin; the backend performs its configured-origin check independently. Only the session and `adpilot_oauth_flow` cookies are forwarded; analytics or other browser cookies are excluded.
- Auth request body is capped at 4 KiB while streaming; upstream JSON at 8 KiB. Body reads have an 8-second deadline and outbound requests a 15-second deadline. Responses use `no-store`. Upstream internals and exceptions are not rendered.
- Upstream OAuth redirects are restricted to `/workspace` or `/login` and optional query; external redirects are rejected. The browser separately accepts authorization URLs only at `https://oauth.yandex.ru/authorize`.
- UI output uses escaped React text. Workspace IDs and pagination cursors are checked before building server paths. No query-provided user ID, actor, token, API URL, or return URL is accepted.

## Verified in this agent

- TypeScript `tsc --noEmit`: PASS.
- Targeted ESLint for workspace/auth/legacy routes, auth component, API helpers, and new test scripts: PASS.
- `node scripts/check-pilot.mjs`: PASS — runtime Value contracts, unavailable/estimated semantics, exact Decimal formatting, invalid dates, tenant IDs/cursors, freshness, recommendation shape.
- `node scripts/check-auth-proxy.mjs`: PASS — untrusted origin/path/method, server URL validation, cookie passthrough, no token reflection, safe redirect restriction, duplicate callback values, oversized request and response, missing configuration. Tests mock only the outbound fetch for this isolated boundary check.
- Browser and real HTTP integration are performed by the parent agent; do not infer their result from this document until its consolidated report records it.

## Reproducible isolated HTTP test

1. Use the backend Python environment to run `frontend/scripts/live-fixture.py --metadata <private-temp-file> --port 3121`. It refuses external database environment configuration and creates a disposable local PostgreSQL with synthetic test tenants. Session values are written only to the supplied private metadata file and not printed.
2. Start the frontend with server `REKVERO_API_URL=http://127.0.0.1:3121`.
3. Run `frontend/scripts/check-live-http.mjs` with `BASE_URL` set to a local frontend origin and `LIVE_FIXTURE_PATH` set to the metadata file.
4. The test checks owner SSR, missing/expired/revoked sessions, unauthorized tenant selection, malformed cursor, absent workspace membership, real empty data, legacy redirects, cache policy, and token non-disclosure. It never calls real advertising providers. Remove the temporary metadata and stop the disposable processes after testing.

## External launch blockers

- Production domain/TLS, trusted origin, hosting, database app roles/schema/backup and restore, runtime secrets and monitoring.
- Yandex ID application credentials and registered frontend callback. Backend default configuration disables real authorization; the UI reports temporary unavailability rather than authenticating locally.
- Approved actual operator/legal documents and explicit SHA256 approval mapping. Placeholder documents cannot authorize new registration.
- Backend provisions a real empty organization/workspace on approved new registration. Direct/Metrika provisioning is not exposed as a self-service HTTP endpoint: actual advertising sources still require administrator setup. Authorized workspaces are readable; a user with no membership sees the true empty state. This does not constitute completed provider onboarding.
- Full recommendation evidence, decision/execution workflow and live provider synchronization are outside the currently exposed read API. No action buttons claim to perform unsupported operations.
- Real OAuth and advertising-account end-to-end verification requires owner-provided setup; no such external actions were performed.

## Changed files owned by this agent

`frontend/app/demo/**/page.tsx`, `frontend/app/demo/layout.tsx`, `frontend/app/login/page.tsx`, `frontend/app/signup/page.tsx`, `frontend/app/onboarding/page.tsx`, `frontend/app/prisma-preview/page.tsx`, `frontend/app/workspace/page.tsx`, `frontend/app/workspace/pilot.css`, `frontend/app/api/auth/[...path]/route.ts`, `frontend/components/reference/auth.tsx`, `frontend/components/reference/auth.css`, `frontend/lib/api-origin.ts`, `frontend/lib/legal-document.ts`, `frontend/app/legal/page.tsx`, `frontend/app/legal/[slug]/page.tsx`, `frontend/lib/auth-proxy.ts`, `frontend/lib/pilot.ts`, `frontend/lib/pilot-contract.ts`, `frontend/scripts/check-pilot.mjs`, `frontend/scripts/check-auth-proxy.mjs`, `frontend/scripts/live-fixture.py`, `frontend/scripts/check-live-http.mjs`, `frontend/.env.example`, `frontend/.gitignore`, and this report.

Other agents own backend auth/security, landing/design/SEO, global metadata, proxy/security headers, deployment configuration, and consolidated launch testing.
