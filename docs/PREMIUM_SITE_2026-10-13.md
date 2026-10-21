# Premium Rekvero landing

Local production preview: http://127.0.0.1:3106/ (127.0.0.1 only).

The owner requested a premium visual redesign, Liquid Glass, animation and relevant agents/tools, and explicitly authorized repositioning. The landing now presents Rekvero as a calm workspace for advertising decisions. Brand and backend contracts are retained. Placeholder paid prices, legal identity placeholder text and unsupported team-role promises were removed from the marketing surface.

Implementation: landing hero, editorial features, workflow, explanation, budget slider, early-access options, FAQ and footer. Liquid Glass is limited to navigation and the preview frame; animations respect reduced motion. Styles are scoped to the public landing. Existing demo data components are reused.

Verification: final Next.js production build and TypeScript pass; ESLint passes for changed TS/TSX files. Browser checks at 1440, 390 and 320px pass for width/metric overflow, keyboard range limits, FAQ disclosure, anchor targets, reduced motion and demo navigation. `results/check-premium.cjs` is the repeatable browser self-check; screenshots are in `results/premium-desktop.png`, `results/premium-mobile.png` and `results/premium-preview.png`. Independent agent review found no remaining P1/P2 defects after mobile amounts were changed to rows.

Build unblockers: generated stale `.next` cache cleared, nested experimental `magicui-preview` excluded from app TypeScript, recursive class-array type inference fixed without changing runtime behavior. The `cn` helper passed a nested-array/empty-input self-check.

Tools: Impeccable, Animate, Playwright CLI and codebase-memory skills read; three agents performed implementation, copy review and final review. Existing shadcn MCP responded, Uilora catalog timed out after 300s. Chrome MCP lacks a Chrome executable; Playwright with installed Edge worked. No unnecessary new project dependencies added. Graphify could not run (uv trampoline failed); graft and direct source checks supplied structural evidence.

Limits: project-wide ESLint still reports existing errors in imported `apple-mail-tabs` and the nested experimental build outputs. Live OAuth/SMS integrations, production data and deployment were not exercised. The local server runs the production build in a hidden background process; backend service readiness is separate.
