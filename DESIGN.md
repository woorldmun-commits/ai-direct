# Rekvero public site

Scope: the public `/` landing page. Product workspace routes retain their existing design. Mode: persuade. Positioning: a calm workspace for decisions in advertising.

An ivory ground, graphite typography and restrained emerald accents create a bright, focused environment. Manrope is the existing display and body face; IBM Plex Mono is reserved for formulas and measured data. Large centered headlines lead to a legible preview of the actual demo contracts. Editorial feature rows, a sequential workflow and a transparent calculation provide distinct density and rhythm below the hero.

Liquid Glass belongs to floating navigation and the product preview frame: translucent surfaces, optical highlights and backdrop blur reveal the surfaces underneath. It does not replace legible content surfaces. Core content works when backdrop filtering is unavailable.

Motion introduces the hero and preview once, with transform/opacity and the existing ease-out token. Hover motion is restricted to precise pointers. Reduced-motion preferences remove animation and smooth scrolling. Focus, mobile wrapping, native FAQ disclosure and the budget range control remain accessible.

Implementation: `frontend/components/landing/premium.css` scopes the replacement world to `.premium-site`. The page composes existing landing modules and preserves product data components. Prices and legal identity placeholders are excluded from the marketing surface; early-access terms remain explicit.
