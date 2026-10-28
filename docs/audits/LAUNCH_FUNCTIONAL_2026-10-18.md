# Functional verification follow-up — 2026-10-18

Production admission remains **NO-GO** until the external configuration, legal approval and provider integration gates in the original functional report are satisfied. This follow-up records the verification-script changes; it does not assert deployment or live provider success.

## Changes

- Updated `frontend/scripts/check-headers.mjs` to check the current public `/`, `/login`, and legal pages. Retired demo, onboarding, signup and Prisma preview routes must redirect to their real destinations, retain the static security headers, and be `no-store`.
- Retained production CSP checks: unique usable request nonce, nonce on every executable script, strict script policy, restricted media source, frame/object/form/base policies, no unsafe script evaluation or inline script allowance, and static asset security headers.
- Added anonymous workspace and foreign-origin auth POST checks. With configured API, an anonymous workspace request must redirect to login. Without API configuration it must show the explicit unavailable state without metric cards. Both must be uncached. A forged Origin logout POST must return 403 with `no-store`.
- Legal pages must show an explicit draft/unavailable or approved status; published content must include its SHA256. Legal drafts remain excluded from sitemap and `noindex,nofollow`. No invented legal entity placeholders are accepted.
- Added explicit `HTTP_ONLY=1` for separate browser verification. The script prints a browser skip, and fails before starting a server if `REQUIRE_BROWSER=1` is also set. The existing CI browser requirement therefore cannot be bypassed by this setting.
- Replaced the retired demo-dialog browser expectation with the current login page. Where approved registration documents enable checkboxes, partial consent must disable submission. Theme execution and console/CSP checks remain, as do legal page overflow checks.
- Expanded `check-auth-proxy.mjs` with exact legal document transport tests: fixed document/version/locale, raw UTF8 digest validation including CRLF preservation, unknown keys, wrong MIME, oversized response, tampered text, and unavailable network. Draft approval remains an explicit false value; no truthy coercion is accepted.

## Verification performed by this agent

| Check | Result |
| --- | --- |
| `node scripts/check-auth-proxy.mjs` | PASS; outbound fetch mocked for these boundary tests |
| `node --experimental-strip-types scripts/check-pilot.mjs` | PASS; Decimal precision, Value semantics and tenant/cursor contracts |
| `node --check scripts/check-headers.mjs` | PASS |
| Targeted ESLint on the four verification scripts | PASS |
| `HTTP_ONLY=1 REQUIRE_BROWSER=1 node scripts/check-headers.mjs` | Expected rejection, exit 1 before server startup |

Parent owns production build, real PostgreSQL/FastAPI-to-SSR HTTP integration, and browser verification. Their final evidence belongs in the consolidated launch report. No browser, real OAuth exchange, advertising write or external account setup was performed by this verification agent. No libraries, environment files, landing content or Next configuration were changed by this agent.

## Source review and limits

Reviewed the actual auth proxy, exact-document loader, consent rendering, legal rendering and workspace fetch boundaries. Fixed server-origin allowlists, per-operation path/method constraints, request Origin comparison, cookie forwarding, redirect restrictions, streaming caps and deadlines remain. The backend remains responsible for provider validation, legal hash approval and session lifecycle. Frontend validation does not replace backend authorization or edge abuse limits.

The graph's coverage metadata reported changed/untracked sources. Conclusions above therefore use direct current-source reads rather than assuming the graph snapshot is complete. This is bounded source/test verification, not a claim of attack-proof operation or completed live infrastructure testing.
