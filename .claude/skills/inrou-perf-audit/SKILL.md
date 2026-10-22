---
name: inrou-perf-audit
description: Use when auditing INROU frontend performance - page load, bundle size, chart rendering, animations.
---

1. Измеряй, потом оптимизируй: Lighthouse (mobile, throttling) и Chrome DevTools trace на production-сборке, не dev-сервере.
2. Метрики: LCP, CLS, INP, размер JS по маршруту, число запросов. Зафиксируй baseline в отчёте.
3. Подозреваемые: тяжёлые графики (рендер на клиенте, лишние перерисовки), шрифты, неоптимизированные изображения, лишние client-компоненты в Next.js.
4. Анимации — только `transform`/`opacity`; 60 fps на среднем мобильном профиле.
5. Не добавляй зависимости ради оптимизации; не меняй внешний вид без сверки с `inrou-visual-regression`.
6. Отчёт: было → стало, какое изменение дало выигрыш.
