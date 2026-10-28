---
name: inrou-visual-fidelity
description: Use when reproducing an INROU page, chart, shadow, responsive layout, animation or UI state from the provided HTML and screenshots.
---

1. Identify target route, viewport, state and exact reference; distinguish verified screenshots from concept crops.
2. Extract computed CSS and geometry from `reference/index.html`; save design tokens before implementation.
3. Reuse existing frontend/router/components. Reconstruct layout and graphic shapes rather than replacing them with generic illustrations.
4. Run page at matched viewport/DPR/fonts/data, capture screenshot through Playwright, compare with authorized reference, and fix major layout and typography discrepancies first, then borders/shadows/graphics.
5. Test responsive widths, keyboard, focus, loading/error/empty/insufficient, reduced motion.
6. Produce screenshot paths and a diff report; do not call an unreferenced design "pixel perfect".
