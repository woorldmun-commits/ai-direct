# Launch design and SEO review — 2026-10-17

Scope: current public home page, reference hero, landing styles, page metadata, robots and sitemap. Shared worktree; unrelated changes preserved. Specialist task does not certify production readiness.

## Changes

- `frontend/components/reference/hero.tsx:17`: first screen answers who (Rekvero, analytics for Direct specialists/agencies), value (spend/conversions/reasoned recommendations), and next action (enter cabinet through `/login`). Header action also enters `/login`.
- `hero.tsx:56`: laptop illustration now has empty metrics and a source connection prompt. Removed invented revenue, CPA, trend percentages and Sparkline data. No synthetic client performance is presented as a result.
- `frontend/components/reference/landing.tsx:18`: schematic dashboard visibly says “Схема интерфейса”, with no numeric results; recommendation preview explains its anatomy rather than displaying synthetic campaign recommendations.
- `landing.tsx:38`: customer journey now reads login → connect source → await report → analyze → evaluate recommendation. Approval is explicitly separated from execution. Removed invitations to demo, fake integrations, free-trial/payment claims, and synthetic comparison links. Integration availability is conditional on server setup and account/API permissions. Footer links to legal information without claiming legal approval.
- `frontend/components/reference/ap-landing.css:136`: fluid two-column hero, aligned to a 1240px content region, responsive stacking below 1024px, compact mobile header, restrained CTA/card shadows. Avoided fixed left positioning of illustration over the copy.
- `frontend/components/reference/landing.css:164`: readable 14–17px supporting copy, consistent section gutters, 48px actions, restrained shadows, light section contrast, no new motion dependency. Existing reduced-motion override retained.
- `frontend/app/page.tsx:3`: demo-free title/description, root canonical retained.
- `frontend/app/sitemap.ts:5`: only public homepage in sitemap; removed authentication URLs. Explicit last content modification date 2026-10-17. Legal pages remain excluded pending legal readiness.
- `frontend/app/robots.ts:7`: public pages remain crawlable to read page-specific noindex; API remains disallowed. Robots is not an authorization mechanism.

## Verification completed

- ESLint on hero.tsx, landing.tsx, page.tsx, robots.ts, sitemap.ts: PASS.
- PostCSS parser on both changed CSS files: PASS.
- Source assertions: public hero/landing have no `/demo`, `демо`, `demo-data`, Sparkline, ReferenceChart; all hero navigation anchors exist; login CTA and schematic disclosure exist: PASS.
- Mathematical sRGB contrast checks for explicit core pairs: white/#5b36cf CTA 7.31:1; #4b597b/#f4f7ff supporting copy 6.50:1; #151b3c/white 16.75:1; #7150f5/#f4f7ff eyebrow 4.70:1; #4b5578/#fbfaff hero note 7.05:1. This checks those colors, not full WCAG conformance.
- UI UX Pro Max reduced-motion search verified guidance (respect user preference; avoid excessive motion). Used existing components/CSS instead of adding a library.
- Vengeance UI catalog checked: https://www.vengenceui.com/docs/install-nextjs . Existing navigation, native FAQ details, and CSS primitives fit the current task; no new component/effect required.
- Relevant installed Next.js robots/sitemap docs read before metadata route changes.
- Graphify orientation completed. Graft results inspected; caller graph warned of ambiguous duplicate symbols, so actual source imports verified. Graft saved approximately 9,753 tokens across two calls; no dollar estimate supplied.

## Required integration checks / launch limits

Parent owns production build, browser screenshots, responsive overflow/keyboard checks, full app security and backend tests. Those are not certified by this scoped static pass.

Actual Yandex authorization, account access, consent/legal approvals, configured domain/canonical/OG, reports and production infrastructure must be verified separately. Public copy does not turn an unconfigured integration into a working one. No guaranteed economics, prices, customer testimonials, fake data, or security certification added.
