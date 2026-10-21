# Figma liquid glass — 13 October 2026

Source: [Figma file](https://www.figma.com/design/1cSg62Pc1hnY1R37QBiFcd/Untitled?node-id=6-40562).
The user selected the liquid-glass version, rather than the large blue landing and purple interface montage.

## Implemented

- Main composition follows frame 6:40562 (800×500): Inter, original triangle logo, original glass sculpture, gradients, floating cards and four reference figures. At native size, sculpture geometry is x=470, y=49, width=330, height=451; header logo is x=42, y=22.5, width=22, height=23.
- Original local SVG curves and 21 bars from analytics frame 6:40708. Metric selection changes visible curves; selecting the previous period returns the existing chart calculated from demo data.
- Shared cabinet header/sidebar/cards, login illustration from 6:33531, settings icons/photo from 6:41157, connection status asset from 6:41099, and Business illustration from 6:40969.
- The original 1536×1024 source montage is displayed at 1600×1200 with object-fit:cover, as instructed by Figma. Avatar crop: x=-1235, y=-20 inside 21×23; Business crop: x=-1219, y=-830 inside 84×63. Identical source images were verified by SHA256 and deduplicated.
- Sixteen original assets are local under frontend/public/figma/liquid (2,240,594 bytes). No temporary Figma URLs remain in application source.

## Validation

Production webpack build, TypeScript and full ESLint passed. Existing UI tests passed (charts, CSV safety, settings persistence).
Browser checks: native-size main geometry; mobile menu; mobile overflow; metric curves 3→1→3; current/previous period; evidence drawer. Additional final route/image checks are recorded in the chat.

## Remaining differences from literal 1:1

- Login still uses the working SMS authentication; Figma depicts email/password. No fake email/password authentication was introduced.
- Cabinet numerical data, recommendations, periods, subscription conditions and available integrations retain the existing product contracts. Reference chart curves and landing figures are illustrative demo artwork.
- Below-the-hero landing sections remain available for the existing navigation. They have no corresponding frames in the selected liquid landing composition.
- Other cabinet pages use the shared reference styling but have not been certified pixel-identical to every individual Figma frame.
- Real SMS, Yandex authorization, AI, payments and production deployment were not exercised.

Preview: http://127.0.0.1:3102/
