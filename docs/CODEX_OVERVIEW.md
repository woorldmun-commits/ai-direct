# ai-direct / inrou — полный обзор проекта для Codex

> Составлен 2026-10-20 по чтению документов и кода (ветка `chore/launch-prep-inrou`). Тесты в момент составления **не запускались**. Если обзор расходится с кодом или `docs/STRATEGY.md`, правы они. Перед правкой любой области прочитайте `CLAUDE.md` и `AGENTS.md` в корне.

---

## 1. Одним абзацем

**ai-direct** — репозиторий SaaS-платформы контроля рекламных расходов в **Яндекс.Директе**. Продукт показывает специалисту, где бюджет тратится неэффективно, **доказывает это цифрами**, предлагает действие, фиксирует решение человека, сверяет ручное выполнение по данным Директа и через 7 дней измеряет эффект. Числа считает **только детерминированный код**; нейросеть, если появится, лишь объясняет готовую рекомендацию. В v1.0 сервис **ничего не пишет в рекламный кабинет** — только читает.

**Названия.** Репозиторий — `ai-direct`. Продукт переименовывался: AdPilot → Rekvero → **inrou** (решение 2026-10-20: бренд `inrou` строчными везде, включая env). В коде, доках и именах переменных остались все три имени (`REKVERO_API_URL`, `ADPILOT_API_URL`, «AdPilot» в README). Не «исправляйте» массово без запроса: это отдельная задача.

## 2. Для кого и какую проблему решает

- **Сегмент v1.0:** малые агентства и самостоятельные директологи (несколько кабинетов у одного человека). Собственник бизнеса — не целевой пользователь v1.0.
- **Работа пользователя:** понять, где деньги уходят впустую → увидеть доказательство → решить → вручную поменять в Директе → проверить эффект → показать клиенту.
- **Оффер:** «Подключите Яндекс.Директ за 2 минуты — покажем, где рекламный бюджет расходуется неэффективно».
- **Чего НЕ обещаем:** автоматический рост эффективности, гарантированную экономию.

## 3. Жёсткие принципы (нарушать нельзя)

1. **Никаких выдуманных данных.** Нет данных → «Недостаточно данных» и что подключить. Ноль ≠ «данных нет».
2. **Каждая цифра = источник + период + снимок + версия правила + формула + уровень уверенности.** Проходит через контракт `Value` (`backend/app/contract.py`).
3. **Деньги — `Decimal`**, рубли с двумя знаками; `float` запрещён (Value его отвергает). В Direct API `returnMoneyInMicros: false`.
4. **Три статуса числа:** `actual` (факт), `estimated` (оценка ≈, обязательна формула), `unavailable` (числа нет, обязательна причина). Инвариант: insufficient ⇔ unavailable ⇔ amount is None.
5. **Границы модулей:** `rules/` и `audit/` не импортируют `ai/` (проверяется тестом; в проекте LLM-адаптера сейчас нет). В LLM уходят только обезличенные агрегаты: без названий кампаний, текстов запросов, ПД, токенов.
6. **Снимки и доказательная цепочка неизменяемы** (append-only на уровне БД).
7. **Решение за человеком.** «Сэкономлено ≈» — только по выполненным рекомендациям, подтверждённым сверкой, как `estimated` (до/после 7 дней без контрольной группы). Слова «потеряно», «возвращено», «заработано» не используются.
8. **Секреты — только в переменных окружения.** Никаких ключей, паролей, токенов, `.env` в git.
9. **152-ФЗ:** персональные данные, локализация в РФ, минимизация (подробно `docs/ARCHITECTURE.md` §2.4–2.5, `docs/LEGAL.md`).
10. **Честный биллинг**, без тёмных паттернов (`docs/PRD.md` §7).

## 4. Главный цикл продукта (сердце)

```
Директ/Метрика (OAuth, только чтение)
  → sync: сырой TSV → парсер с allowlist → санитизация → СНИМОК (snapshots, stat_rows)
  → audit: правила (rules/) на последнем снимке каждого кабинета
  → политика безопасности (audit/policy.py): может только ПОНИЗИТЬ уровень действия
  → доказательная цепочка: issue → finding → explanation → recommendation
  → итог «Расход с признаками неэффективности ≈ N ₽» БЕЗ двойного счёта (audit/exposure.py)
  → экран «Сегодня»/«Анализ»: сколько ≈, сколько проблем, 3 действия
  → решение человека: accepted / postponed / rejected (с причиной) / «Проверил»
  → ручное выполнение в Директе → пользователь отмечает «сделано»
  → сверка по данным Директа (audit/verify.py): confirmed / not_confirmed / pending
  → замер через 7 дней (audit/measurement.py) → «Сэкономлено ≈»
  → уведомления (outbox → notifications) и email-дайджест
```

Статусы рекомендации: `new` → `requires_decision` → `accepted` → `applied` (`execution_mode = manual`, затем сверка) → замер; плюс `postponed`, `rejected`.

## 5. Три правила v1.0 (ровно три; новое — только через `docs/STRATEGY.md`)

Реестр: `backend/app/rules/__init__.py` → `RULES = (HIGH_CPA_TARGET, HIGH_CPA_BASELINE, ZERO_CONV_CAMPAIGN, ZERO_CONV_PLACEMENTS)`.

| Файл | Правило | Суть |
|---|---|---|
| `zero_conv_campaign.py` | `zero_conv_campaign@1` | Кампания с расходом и 0 конверсий за 7 дней. Порог: расход ≥ max(3 × CPA-ориентир, 1 000 ₽) и клики ≥ 50. Ориентир: target_cpa → CPA кампании за 30 дней до окна → CPA аккаунта → абсолютный минимум 5 000 ₽. Порог обоснован Пуассоном (e⁻³ ≈ 5% ложной тревоги). Действие только «проверить» (цели, стратегия, поисковые запросы/минус-фразы), ставку и бюджет не предлагает. |
| `high_cpa.py` | `high_cpa_target@1`, `high_cpa_baseline@1` | CPA выше целевого (если задан `target_cpa`) или выше базового. Общий evaluator, режим — параметр версии; `issue_key` одинаков, так что рекомендация та же. Baseline-режим — только «проверить причину» + «укажите целевой CPA». |
| `zero_conv_placements.py` | `zero_conv_placements@1` | Площадки РСЯ с расходом и без конверсий (в окне и за всю историю снимка 37 дней). Один вывод **на кампанию** («N площадок, ≈ X ₽»), список площадок в evidence. Действие — исключить площадки вручную (уровень `review`). Работает только если в снимке есть отчёт площадок. |

Общие вещи (`rules/domain.py`): `Rule`, `Finding`, `NotEnoughData`, `Fact`, `Window`, `SnapshotView`, `AuditSettings`, `issue_key`, `windows`, `frozen`. Правила — **чистые функции**: без БД, сети, времени. Изменение порогов = новая версия (`@2`), старые не переписываются. Пороги утверждает владелец продукта.

Типичные исходы правила: `Finding` (есть вывод), `NotEnoughData(VOLUME_INSUFFICIENT | SOURCE_MISSING)` (открытая проблема не «исчезает» от нехватки данных), `None` (проблемы нет). Незавершённые («partial») дни досчёта конверсий снижают уверенность: `level_reason = conversions_partial`.

## 6. Backend (`backend/`, Python 3.11)

Зависимости: pydantic ≥ 2, psycopg[binary], cryptography (AES-GCM), httpx, tzdata. Тесты: pytest. Линтер: ruff (`ruff.toml`).

### 6.1 Модули `backend/app/`

| Пакет / файл | Назначение |
|---|---|
| `contract.py` | Модель `Value` — контракт любого числа. Дублируется в SQL `value_is_valid()`; согласованность держит `tests/test_value_contract.py`. |
| `tenancy.py` | `workspace_scope`: вход в workspace для RLS (`app.workspace_id`). |
| `rules/` | Rule engine (раздел 5). |
| `audit/` | `policy.py` (safety_policy: inspect_only / review / change; только понижает), `templates.py` (шаблонное объяснение без LLM; числа форматируются без округления), `selection.py` (какие кабинеты и снимки входят в аудит; снимки разных дней не смешиваются), `persist.py` (finding → issue/recommendation, события `seen_again`, `resolved` только если действительно проверили), `present.py` (как действие показывается человеку), `exposure.py` (итог без двойного счёта, `exposure_total@1`), `verify.py` (сверка ручного выполнения), `measurement.py` (методики замера `*_measure@N`), `values.py`. |
| `sources/` | Клиенты внешних API: `direct.py` (Reports API v501; `DirectFixture` для тестов и `DirectApi`), `direct_params.py` (параметры объектов для сверки), `metrika.py`, `metrika_discovery.py` (выбор счётчика/целей), `campaigns.py`, `conversion.py`, `http.py`. |
| `sync/` | `parse.py`/`metrika_parse.py` (разбор TSV с allowlist столбцов), `sanitize.py` (маскирование телефонов/контактов в текстах запросов; перекос в сторону приватности), `snapshot.py`, `store.py` (`load_view`). |
| `worker/` | Фоновые задачи (функции, не привязаны к очереди): `sync.py`, `audit.py`, `measure.py`, `outbox.py`, `notify.py`, `recheck.py`, `health.py`, `retention.py`; `guard.py` (единая точка допуска задач, ALLOW/SKIP с причиной), `locks.py` (блокировки workspace/аудита), `runner.py` (долговечная очередь пилота: `python -m app.worker.runner [--once]`). |
| `api/` | FastAPI (подробно ниже). |
| `auth/` | `yandex_oauth.py` (вход и OAuth подключений), `login.py` (вход через Яндекс ID; токен входа нигде не хранится), `email_password.py` (scrypt-хэши, нормализация email), `email_config.py`, `phone.py`/`phone_number.py` (SMS-вход: защита от абуза), `tokens.py` (шифрование токенов Директа/Метрики: AES-GCM, AAD = provider:workspace:connection, ротация ключей). |
| `legal/` | Реестр версий и SHA256 юридических документов (`documents.py`), тексты-заглушки в `texts/`. Хэши шаблонов утверждать нельзя. |
| `insights/` | `report.py` (детерминированная аналитика, без LLM и выдуманных знаменателей), `lead_import.py` (строгий минимизированный CSV лидов; ошибки не эхом возвращают значения строк). |
| `agents/` | Offline-gate «Evidence Supervisor» (раздел 9). |

### 6.2 API (`backend/app/api/`)

`app.py` собирает приложение; все роутеры подключены с общим `PREFIX` (фронтенд ожидает `/api/v1`). Сквозная защита — `middleware.py` (чистый ASGI): `request_id`, заголовки безопасности, CSRF по Origin (403 `csrf_rejected`), лимит тела, последний рубеж для 500. API подключается к БД только ролью **`app_rw`** под RLS; суперпользователь/BYPASSRLS отвергаются (`db.py`). Настройки — только из окружения (`settings.py`).

Известные маршруты (по декораторам):

- `routes.py`: `GET /health`, `GET /me`, `GET /workspaces/{id}/recommendations`, `GET /workspaces/{id}/members`
- `today.py`: `GET /workspaces/{id}/today` — экран «Сегодня»
- `active.py`: единое определение «активной рекомендации» для «Сегодня» и «Рекомендаций» (проблема открыта, кабинет выбран и вошёл в **последний** аудит, и последний аудит её проверил или удержал через «недостаточно данных»)
- `auth.py` (`/auth`): `POST /yandex/start`, `GET /yandex/callback`, `POST /logout`
- `email_auth.py` (`/auth`): конфиг + регистрация, подтверждение email, вход, восстановление и сброс пароля (точные пути — в файле)
- `direct_connect.py`: `POST /workspaces/{id}/direct/start`, `GET /direct/callback`, `GET /workspaces/{id}/direct`, `POST /workspaces/{id}/direct/sync`
- `recommendation_flow.py`: решения по рекомендации (контракт — `docs/handoffs/recommendation-flow-contract.md`)
- `workspace_insights.py`: аналитика, бюджетный план, импорт лидов (контракт — `docs/handoffs/workspace-insights-contract.md`)
- `legal.py`: `GET /documents/{document}`
- Вспомогательное: `deps.py` (сессия, actor только из сессии), `errors.py`, `serialize.py` (`value_of`), `proxy_client.py`.

Полный контракт: `docs/API_CONTRACT.md`; исполнение (v1.1): `docs/API_CONTRACT_EXECUTION.md`.

### 6.3 База данных (`backend/db/schema.sql`, PostgreSQL)

Принцип: инварианты живут в `CHECK` и триггерах, а не только в Python. Метки в схеме: `[A]` — append-only, `[O]` — outbox/очереди.

- **Люди и доступ:** `users`, `yandex_identities`, `sessions`, `legal_acceptances`, `organizations`, `organization_memberships`, `workspaces`, `workspace_memberships`, `workspace_settings`, `email_credentials`, `email_pending_signups`, `email_reset_tokens`, `email_auth_attempts`, `phone_auth_codes`, `phone_auth_events`.
- **Подключения:** `direct_connections`, `direct_accounts`, `metrika_connections`, `metrika_counters` (токены шифрованные, читаются только ролью `app_token`).
- **Данные:** `releases`, `sync_runs`, `snapshots`, `stat_rows`, `search_query_texts`, `search_query_sightings` (тексты запросов хранятся 60 дней), `placement_names`.
- **Аудит и доказательства:** `audit_runs`, `audit_run_snapshots`, `issues`, `findings`, `explanations`, `recommendations`, `recommendation_results`, `recommendation_events`, `measurements`.
- **Коммуникации и деньги:** `outbox_events`, `digests`, `notifications`, `subscriptions`, `subscription_events`, `payments`, `free_audit_claims`, `deletion_requests`.
- **Аналитика пилота:** `workspace_budget_plans`, `workspace_lead_imports`, `workspace_leads`.
- Остаток от отказа: `telegram_links` (Telegram **полностью удалён из продукта**, не добавляйте).
- **Роли:** `app_rw` (API), `app_system` (очередь/outbox, RLS не фильтрует по workspace), `app_token` (чтение токенов), `app_deleter` (только EXECUTE функций удаления). RLS по `app.workspace_id`.
- **Миграции:** `backend/migrations/` (`released.txt` фиксирует чек-суммы выпущенных; LF принудительно). Версии: `0001_baseline`, `0002_phone_auth_protection`, `0003_placement_names`, `0004_value_unavailable_reason`, `0005_workspace_placement_names`, `0006_workspace_insights`, `0007_email_auth`, `0008_pilot_sync_queue`. Выпущенные миграции не править — только новая. Запуск: `python -m migrations`.

Модель данных подробно: `docs/DATA_MODEL.md` (§9.5 — RLS).

### 6.4 Тесты и evals

Запуск (**не npm**): `cd backend && .venv/Scripts/python.exe -m pytest`. Venv на Python 3.11 (`uv venv --python 3.11 .venv`, `uv pip install -r requirements-dev.txt`); системный 3.14 не годится, `pgserver` требует ≤ 3.12. Без `pgserver` тесты схемы берут `TEST_DATABASE_URL`.

В `backend/tests/` ~60 файлов: правила (`test_rule_*`), контракт Value, exposure, замер, воркеры, сверка, RLS и изоляция арендаторов (`test_rls`, `test_api_isolation`, `test_access`), аутентификация (email, phone, Yandex), токены и шифрование, миграции/схема, санитизация, deploy, границы модулей, `test_agent_supervisor`. Golden-кейсы правил — `backend/evals/` (`golden.py`, `cases/{high_cpa,zero_conv_campaign,zero_conv_placements}`). `backend/scripts/e2e_account.py` — прогон аудита на реальном кабинете (MVP-0).

## 7. Замер эффекта (`audit/measurement.py`)

Дизайн у всех методик один: `uncontrolled_before_after` — 7 дней до и 7 дней после дня выполнения (сам день ни в одном окне), без контрольной группы. Методика выбирается по `measurements.policy = '<issue_type>_measure@N'`, её ставит триггер БД при переходе в `done`. `saved` («Сэкономлено») есть только при вердикте `effect`; любое сомнение → `saved = NULL`.

- `high_cpa_measure@2` (текущая): `saved = конверсии_после × max(CPA_до − CPA_после, 0)`, подтверждается только если конверсии_после ≥ конверсий_до; иначе `not_confirmed`.
- `high_cpa_measure@1` — историческая, для воспроизводимости старых замеров.
- `zero_conv_campaign_measure@2`, `zero_conv_placements_measure@2` — первые версии (номер «@2» ставит триггер для любого issue_type).
- Параметры методики — часть версии; изменение = новая версия, старые замеры не пересчитываются.

## 8. Фронтенд

- **Актуальный сайт — `designe 1.0/`** (Next.js 16 App Router, React 19, Tailwind 4, lucide-react; Node ≥ 22.6). Для хостинга Root Directory = `designe 1.0`. **`frontend/` — legacy**, при деплое автоматически не выбирать.
- Страницы (`designe 1.0/app/`): `/` лендинг, `features`, `how-it-works`, `integrations`, `pricing`, `security`, `faq`, `contact`, `legal`, `login`, `signup`, `verify-email`, `forgot-password`, `reset-password`, `onboarding`, `workspace` (реальные данные), `prisma-preview`. Раздел `/demo` **удалён** в текущих незакоммиченных изменениях (старый README ещё его упоминает).
- Компоненты: `components/app/` (shell, today, recommendations, why-drawer — «Почему так решено», freshness, command-palette, rec-actions), `components/landing/`, `components/reference/` (лендинг/авторизация/кабинет «launch-reference»), `components/workspace/` (midnight-shell), `value-view.tsx` (показ `Value` — «Факт / Оценка ≈ / Недостаточно данных»), `charts.tsx`.
- `lib/`: `api-origin.ts`, `auth-proxy.ts` (прокси к backend), `value.ts`.
- Конфиг: `REKVERO_API_URL` (alias `ADPILOT_API_URL`) — origin backend без пути (приложение добавляет `/api/v1`); `REKVERO_APP_ORIGIN` — публичный origin; `NEXT_PUBLIC_SITE_URL` задавать только после подтверждённого HTTPS-домена (до этого индексация закрыта). Серверных секретов во фронтенде нет.
- Проверки (`designe 1.0/scripts/`): `check-adpilot-visual.mjs`, `check-adpilot-accessibility.mjs`, `check-pilot-browser.mjs`, `check-workspace-proxy.mjs`, `check-chart-geometry.mjs`. Команды: `npm ci`, `npm run lint`, `npm run test:model`, `npm run test:pilot`, `npm run build`, `npm run start -- --hostname 127.0.0.1 --port 3120`.
- Правило честности UI: ошибки API **не** заменяются демо-значениями; модельные данные всегда явно помечены.

## 9. Агенты и роли — что создано

Важно: это **рабочие профили для ручной координации**, а не автономные сотрудники внутри SaaS. Они не запускают фоновых процессов и не подключают LLM.

**Иерархия:** владелец продукта → руководитель интеграции → профильные исполнители → QA → независимый Evidence Supervisor. Финальный вердикт проверяющего обязателен; публикацию и внешние действия разрешает только человек.

Описания: `docs/project-agents/*.md` (человеческие), субагенты Claude Code: `.claude/agents/inrou/*.md`.

| Субагент | Зона | Что делает |
|---|---|---|
| `inrou-backend-metrics` | `rules/`, `audit/`, `insights/` | Правила, суммы без двойного счёта, тексты рекомендаций, замер «Сэкономлено ≈». |
| `inrou-integrations-data` | `sources/`, `sync/`, `worker/` | OAuth Директа и Метрики, отчёты, санитизация, снимки, очередь. |
| `inrou-frontend` | `designe 1.0/` | Лендинг, вход, онбординг, экран «Анализ», рекомендации, доступность, мобильная вёрстка. |
| `inrou-seo` | публичные страницы | Индексация, метаданные, canonical, JSON-LD, robots/sitemap, llms.txt, GEO. |
| `inrou-security` | ревью, **право вето, код не пишет** | Вход, сессии, лимиты, RLS, токены, секреты, ПД, что уходит в ИИ, CSP. |
| `inrou-legal` | тексты, ПД | 152-ФЗ, 38-ФЗ, оферта, правила Директа; готовит черновики, **юридических решений не принимает**. |
| `inrou-qa` | тесты | Негативные сценарии, регрессии, e2e путь пользователя. |
| `inrou-product` | продукт/экономика | Сегмент, позиционирование, цена, метрики пилота, конкуренты (eLama, Click.ru, К50, Roistat). |
| `inrou-release-ops` | сборка/эксплуатация | Dockerfile, deploy/, CI, бэкапы, /health, гигиена репозитория. |
| `inrou-supervisor` | приёмка | Выносит **PASS / NEEDS_WORK / BLOCKED**, код не пишет. |

**Правила работы агентов:** у каждого исполнителя своя зона записи, зоны не пересекаются. Общие файлы (`backend/db/schema.sql`, `backend/migrations/`, `auth/`, остальное `api/`, `tenancy.py`, lock-файлы) меняет **только руководитель интеграции**. Один писатель на worktree; чужие изменения не откатывать. Цикл: исполнитель → передача → supervisor → вердикт → владелец решает о коммите. Формат передачи: `scope`, `revision`, `changed_files`, `claims`, `evidence`, `checks`, `not_checked`, `risks`, `owner_action` (`docs/handoffs/project-agents-contract.md`). Каждый вывод помечается `fact` / `estimate` / `hypothesis` / `unavailable`.

**Offline-gate `backend/app/agents/`** (`supervisor.py`, `__main__.py`): проверяет структурированные `Value`-утверждения против независимо подготовленного manifest (workspace, период, возраст данных, SHA256 источника, уникальность id). Он проверяет согласованность, **не подлинность** произвольного JSON, не считает новых метрик и не читает свободный текст. Manifest обязан подготовить владелец интеграции, а не отправляющий агент. Запуск из `backend`: `python -m app.agents verify claims.json --evidence trusted-manifest.json`. В runtime автоматически не подключён.

## 10. Развёртывание и эксплуатация

- **Локально (Docker):** `python deploy/configure_local.py` (один раз создаёт `deploy/.env`, повторно не перезаписывает ключи — не пересоздавать, если в БД уже есть токены) → `docker compose --env-file deploy/.env up --build -d`. Адрес `http://localhost:10000`, проверка `/api/health`. Bootstrap (`deploy/bootstrap.py`) создаёт роли БД и запускает миграции, существующую БД не сбрасывает. `deploy/Caddyfile`, `deploy/serve.py`, `Dockerfile`, `compose.yaml`.
- **Render (демо-стенд):** `render.yaml`, free-план, регион Frankfurt. **Только демонстрация, без клиентских ПД, данных и токенов** (локализация в РФ). SMTP-порты закрыты, сервис засыпает.
- **Цель:** Yandex Cloud, одна VM с docker compose (`api`, `worker`, `web`, `redis`, Caddy), managed PostgreSQL, секреты в Lockbox/env.
- **Для реальных клиентов нужно:** HTTPS и `/api/health`; **два отдельных приложения Яндекса** (вход `YANDEX_LOGIN_*` и API Директа/Метрики `YANDEX_API_*`, права `direct:api`, `metrika:read`, одобренный доступ к API Директа); callback'и `/api/auth/yandex/callback` и `/api/direct/callback`; утверждённые юр. тексты и их SHA256 в `API_SIGNUP_APPROVED_HASHES`; `TOKEN_ENCRYPTION_KEY_1` (base64 от 32 случайных байт) и `YANDEX_API_ENABLED=1`; проверенный SMTP. Подробности: `ADPILOT_LAUNCH.md`, `deploy/README.md`.
- **Роли БД при деплое:** API — `app_rw`, очередь — `app_system`, токены — `app_token`; миграции — отдельной `MIGRATION_DATABASE_URL`.
- **CI:** `.github/workflows/ci.yml`.

## 11. Планируется, но в репозитории ещё нет

- Redis + arq вместо текущего `worker/runner.py`; Alembic/SQLAlchemy (сейчас собственные SQL-миграции).
- LLM-адаптер (YandexGPT Pro, `ai/`, только обезличенные агрегаты, только объяснение). Сейчас объяснения шаблонные.
- Биллинг/платёжный провайдер (`billing/`), автоматическая сверка, рассылка дайджеста по расписанию, CRM API (аудит 2026-10-18).
- **v1.1:** исполнение через Direct API (`execution/`, права, idempotency, лимиты, журнал, approval, откат — `docs/EXECUTION_SAFETY.md`), офлайн-конверсии CSV, «Спросить AI» только для чтения, Web Push.
- **v2.0:** Outcome Graph, автоматизация по заранее одобренным правилам, CRM, VK Реклама.

## 12. Карта репозитория

| Путь | Что это |
|---|---|
| `backend/` | Весь серверный код, схема БД, миграции, тесты, evals |
| `designe 1.0/` | **Активный фронтенд** |
| `frontend/` | Legacy-фронтенд (не трогать без запроса) |
| `docs/` | Каноническая документация: STRATEGY (верх иерархии), VERSION_SCOPE, PRD, ARCHITECTURE, DATA_MODEL, API_CONTRACT*, EXECUTION_SAFETY, ECONOMICS, LEGAL*, AI_GOVERNANCE, CLAIMS_REGISTRY, DISASTER_RECOVERY, DATA_FLOW_INVENTORY, PRODUCT_SPEC; `audits/` (аудиты 2026-10-17/18), `handoffs/`, `project-agents/` |
| `_docs/` | Краткие выжимки: `project.md` (бизнес-контекст), `stack.md` |
| `deploy/`, `Dockerfile`, `compose.yaml`, `render.yaml` | Деплой |
| `.claude/agents/inrou/` | Субагенты Claude Code |
| `brand/`, `design/`, `PRODUCT.md`, `DESIGN.md` | Бренд, голос, дизайн-система («midnight-champagne») |
| `prov1/`, `sites/`, `results/`, `artifacts/`, `reference/`, `magicui-demo/` | Эксперименты, прототипы сайтов, отчёты проверок, артефакты аудитов — **не продакшн-код** |
| `delo/`, `pipeline/`, `zasedaniya/` | Бизнес-заметки (компания, решения, цифры; контент-план). Поля «ЗАПОЛНИТЬ» — не заполнены |
| `graphify-out/`, `graft/` | Автосгенерированные графы кода (не править руками) |
| `ADPILOT_LAUNCH.md`, `VISUAL_AUDIT.md`, `AGENTS.md`, `CLAUDE.md` | Запуск, аудит, инструкции агентам |

**Мусор в корне** (похоже на побочные продукты shell-ошибок; не использовать и не удалять без запроса владельца): `a{padding`, `div{flex`, `span{display`, `t)`, `str`, `{}]{25`, `0`, `Explanation\``, `tuple[Output`, `s.run`, `C:UserswoorlDocumentsclaudeai-directworkdir_env.txt`; аналогично в `designe 1.0/` (`44`, `500`, `div{flex`, `{}]{3`).

## 13. Текущее состояние (на 2026-10-20)

- Ветка `chore/launch-prep-inrou`, `main` — основная. Последние коммиты: email-вход, юридические документы API, insights и recommendation flow (`2410652`), фронтенд-релиз AdPilot (`651a7cd`).
- Незакоммичено много правок: подготовка к запуску под брендом inrou (CI, `.gitignore`, `PRODUCT.md`, `_docs/*`, backend API/legal/worker/sources, `schema.sql`, `migrations/released.txt`), удаление `designe 1.0/app/demo/*`, правки лендинга и авторизации.
- Дедлайн запуска пилота сдвинут на **~1 ноября 2026** (надёжное ядро, read-only агенты, кабинеты с ~12.10), первые клиенты через concierge-пилот.
- В документах сохраняются противоречия: «вход только по SMS» (STRATEGY/PRODUCT) против реализованного email+пароль и Яндекс ID. Пометка о смене курса стоит в шапке `docs/STRATEGY.md`. Уточняйте у владельца, если задача зависит от способа входа.

## 14. Рекомендации Codex по работе в проекте

1. Перед правкой читайте: `CLAUDE.md`, `AGENTS.md`, затем `docs/STRATEGY.md` и документ своей области.
2. Любое число — через `Value` и `Decimal`. Не используйте `float` для денег.
3. Не меняйте `rules/` и `audit/` так, чтобы они импортировали `ai/`.
4. Не правьте выпущенные миграции; новая миграция + запись в `released.txt` только руководителем интеграции.
5. Не расширяйте список правил (их три) без правки `docs/STRATEGY.md` владельцем.
6. Не добавляйте запись в Директ в v1.0.
7. Не вводите Telegram, не выдумывайте цены, отзывы, кейсы, логотипы клиентов.
8. После изменения backend: `cd backend && .venv/Scripts/python.exe -m pytest`. После изменения фронтенда: команды из раздела 8.
9. Коммиты — в формате `feat:`, `fix:`, `refactor:`, `docs:`, `test:`; **без** трейлера `Co-Authored-By`.
10. Заметили баг вне задачи — сообщите, но не чините попутно.
