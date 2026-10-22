---
name: inrou-visual-regression
description: Use when comparing an INROU page with its reference screenshot or checking a UI change for visual regressions across viewports and themes.
---

1. Фронтенд — `designe 1.0/`. Определи package manager по lock-файлу; не запускай install в корне репозитория.
2. Эталон: `reference/index.html` и verified screenshots. Concept crops — не эталон для пикселей.
3. Снимай через Playwright (`@playwright/test`, chromium) при одинаковых viewport, DPR, шрифтах и данных: 320, 375, 768, 1024, 1440, 1920 — где экран применим. Светлая и тёмная тема, hover/focus/empty/error/loading.
4. Сначала правь крупное (сетка, типографика, отступы), потом бордеры, тени, графики.
5. Отчёт: пути к скриншотам до/после, список оставшихся расхождений. Не называй экран «pixel perfect» без эталона.
6. Скриншоты кладём вне репозитория или в игнорируемую папку; не коммить бинарные артефакты без просьбы.
