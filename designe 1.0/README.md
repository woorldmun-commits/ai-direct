# inrou — активный сайт

Папка `designe 1.0` содержит основной сайт INROU на Next.js 16.4.2: дизайн из `INROU_FINAL_HANDOFF/reference/index.html`, публичные страницы и рабочий кабинет. Кремовые поверхности, хвойная навигация, Georgia/Inter; светлая, тёмная и системная темы. Архитектура и серверные контракты сохранены. Доказательства и ограничения: [отчёт реализации](../docs/design-implementation/IMPLEMENTATION_REPORT.md).

## Локальный запуск

Из этой папки на Node.js 22:

```text
npm ci
npm run build
npm run start -- --hostname 127.0.0.1 --port 3120
```

После обычного `npm ci` зависимости устанавливаются из `package-lock.json`; локальная ссылка на чужой `node_modules` не требуется и в релиз не входит.

Основные пути:

- `/` — главная; `/features`, `/how-it-works`, `/agencies`, `/business`, `/about`, `/integrations`, `/pricing`, `/security`, `/faq`, `/contact` — публичные страницы.
- `/demo/<section>` — демонстрационный кабинет, **404 по умолчанию**; только локальный QA включает `INROU_DEMO=1`. Все показатели синтетические; решения живут в памяти до перезагрузки. `/demo/states` — галерея loading/empty/error/insufficient/stale/partial/forbidden/expired/success. Реклама не изменяется.
- `/login`, `/signup`, `/verify-email`, `/forgot-password`, `/reset-password` — вход, подтверждение и восстановление аккаунта. Доступность зависит от конфигурации backend и документов.
- `/register` — совместимый адрес регистрации, перенаправляет на `/signup`.
- `/onboarding/{organization,business-profile,connect,first-audit}` — первый запуск с серверными состояниями и проверкой сессии.
- `/workspace` — совместимый редирект со старых `?view=`; 14 разделов `/workspace/{overview,analysis,recommendations,campaigns,connections,impact,reports,alerts,ai,history,team,plans,settings,business-profile}`, дополнительно `data-health` и `onboarding-review`. Контекст — `?workspace=ws_…`. Паспорт — `/workspace/recommendations?workspace=…&rec=…`; старый `/workspace/recommendations/[id]` сохранён как редирект. Поддержаны детали подключений, сигналов, участников, недельного отчёта и история через паспорт. Для недоступных кампаний — полноценный макет без вымышленных показателей.
- `/legal` и страницы документов — правовая информация. Наличие текста на странице само по себе не является утверждением документов владельцем.

## Настройки Next.js

Скопируйте `.env.example` в локальный файл настроек только в своём окружении. Секреты и реальные session-токены не должны попадать в репозиторий или браузерные env.

- `INROU_API_URL` — origin backend без пути; HTTPS, кроме loopback HTTP. Приложение добавляет `/api/v1`.
- `INROU_APP_ORIGIN` — точный публичный origin браузера; необходим за reverse proxy с внутренним адресом. Тот же origin должен быть разрешён backend.
- `INROU_SESSION_COOKIE` — имя серверной cookie, по умолчанию `session`. Значение токена передаёт только cookie.
- `NEXT_PUBLIC_SITE_URL` — подтверждённый HTTPS origin при сборке. Пока он не задан либо является локальным, индексация закрыта, sitemap пуст.
- `NEXT_PUBLIC_YM_ID` — необязательный согласованный счётчик. Загружается после согласия; закрытые страницы аккаунта исключены, Webvisor/clickmap выключены.
- `NEXT_PUBLIC_YANDEX_VERIFICATION` — необязательный код подтверждения публичного сайта.

Не используйте `INROU_LOCAL_PREVIEW=true` в production: этот режим предназначен для изолированного локального стенда с тестовой почтой и документами.

## Backend и регистрация

Для email-регистрации нужны соответствующие backend-маршруты, миграции, почтовый сервис и утверждённые документы точной версии `2026-10-01`, `ru-RU`, с проверяемым SHA-256. Форма остаётся закрытой, если эти требования не выполнены. Яндекс ID — отдельный способ входа; вход сам по себе не подключает рекламные источники.

Рабочий кабинет использует `/me`, `today`, `insights` и рекомендации. Обновления плана бюджета и импорта заявок проходят через закрытый allowlist Next.js proxy. Дневной ряд, не переданный сервером, не рисуется вымышленными данными. Доступ к рекламным данным и изменения рекламы — отдельные разрешения и процессы.

Важно для текущего релиза: часть backend-расширений и миграций существует только в локальном рабочем дереве. Перед запуском полного сервиса нужно подготовить и проверить backend-релиз; проверенный локальный frontend не доказывает готовность backend из чистого `main`.

Тарифы в интерфейсе: Контроль — 1 990 ₽/месяц за 1 аккаунт; Бизнес — 4 990 ₽ до 5; Агентство — 9 990 ₽ до 15. Это опубликованное предложение интерфейса: оплата и серверные права тарифов ещё не подключены. Рекламный бюджет оплачивается отдельно.

## Проверки

```text
npm run lint
npm run test:model
npm run test:pilot
npm run test:ix
node scripts/check-auth-proxy.mjs
node scripts/check-workspace-proxy.mjs
node scripts/check-site.mjs
node scripts/check-insights.mjs
node --experimental-strip-types scripts/check-chart-geometry.mjs
node scripts/check-inrou-csv-security.mjs
node scripts/check-assets.mjs
npm run build
npm run test:headers
npm audit --audit-level=high --package-lock-only --omit=dev
```

`test:headers` поднимает отдельный сервер из готовой `.next` сборки. `REQUIRE_BROWSER=1` требует установленный Playwright/Chromium и не допускает тихий пропуск браузерной проверки. `HTTP_ONLY=1` используется только когда браузер проверяется другим runner; эти флаги несовместимы.

Финальная браузерная проверка: сначала запустить `scripts/pilot-fixture.py` через backend venv (одноразовая локальная БД, порт 3121; `INROU_INTELLIGENCE_ENABLED=1` для анализа), затем после сборки `node scripts/check-ix-acceptance.mjs`. Runner сам поднимает временный Next server только на `127.0.0.1:3130`, использует Edge/Playwright из bundled runtime и останавливает свой сервер. `PLAYWRIGHT_MODULE` задаёт установленный пакет Playwright; `AXE_PATH` — установленный `axe.min.js` для WCAG проверки. Без axe отчёт явно помечает аудит UNAVAILABLE. Нужна свежая фикстура: E2E сохраняют бюджет/импорт/ручное решение. Сессионные cookie фикстуры не выводятся в отчёт. Публичный доступ/реальные данные не используются.

Матрица: 54 маршрута, light/dark, 320/375/390/768/1024/1280/1440/1920; скриншоты 390/1440, 19 сравнений с неизменёнными PNG архива и оригинальным HTML в том же Edge. Новые макеты — `docs/design-implementation/new_screen_baselines/`, статус PENDING до утверждения владельцем.

Активный CI: `.github/workflows/inrou-launch.yml`. Успешная локальная сборка не заменяет успешный CI чистого checkout.

## Границы готовности

Перед внешним запуском нужны подтверждённые домен и hosting/TLS, опубликованный совместимый backend и миграции, production БД с резервным копированием и проверкой восстановления, настроенная почта/OAuth, доступы к реальным источникам, утверждённые документы и проверенные права пользователей. Оплата, недостающие API и производственные интеграции не появляются от одной настройки дизайна.

22 октября 2026 года audit обнаружил critical advisory в Next.js 16.3.8. Next.js и eslint-config-next обновлены до 16.4.2, без `audit fix --force`. Результат повторного audit и оставшиеся dev-зависимости фиксируются в отчёте. Успешный audit не заменяет проверку конфигурации, прав и production.
