# Стек ai-direct

Источник: `docs/ARCHITECTURE.md` (§1, §9–11) и `docs/PRD.md` (§8); объём версий — `docs/STRATEGY.md` и `docs/VERSION_SCOPE.md`. Текущий этап — неделя 1 плана v1.0 (CI, миграции, security headers, каркас FastAPI, RLS + actor из сессии, защита SMS-потока, тесты изоляции). Здесь только выжимка; при расхождении прав первоисточник.

## Уже есть в коде
- **Бэкенд:** Python 3.11. Зависимости: `pydantic>=2`, `psycopg[binary]`, `cryptography` (AES-GCM токенов), `httpx` (OAuth, Директ, Метрика), `tzdata`.
- **БД:** PostgreSQL. Схема — `backend/db/schema.sql`: инварианты в `CHECK` и триггерах, append-only доказательства, роли `app_rw` / `app_token` / `app_system` / `app_deleter`, RLS по `app.workspace_id` (`docs/DATA_MODEL.md` §9.5).
- **Тесты:** pytest (`backend/pytest.ini`, `pythonpath = .`), запуск из `backend/`. Схему проверяет встроенный `pgserver` (Python ≤ 3.12) или `TEST_DATABASE_URL` в CI.
- **Модули `backend/app/`:** `contract` (Value и инварианты), `sources` (Директ, Метрика), `sync` (парсинг, санитизация, снимки), `rules` (rule engine), `audit` (политика уровней, выбор, сохранение, замер), `auth` (вход через Яндекс ID, OAuth подключений, шифрование токенов), `legal` (реестр версий и хэшей документов, тексты-заглушки), `tenancy` (вход в workspace для RLS).
- **Задачи воркера** (`app/worker/`, функции без очереди): синхронизация, аудит, замер, outbox, уведомления, перепроверка доступа, здоровье подключений, ретеншн; допуск — `guard`, блокировки — `locks`.
- **Фронтенд:** Next.js (App Router) + Tailwind, `frontend/`: лендинг, вход/регистрация, онбординг, юридические страницы и демо-кабинет на тестовых данных (`/demo`), без подключения к бэкенду.

## Запланировано (ещё нет в репозитории)
- **API:** FastAPI (REST + webhooks) по `docs/API_CONTRACT.md`.
- **Очереди и расписания:** Redis + arq (cron встроен, Celery не нужен) поверх существующих функций задач. Семейства задач с отдельными ролями БД — `docs/EXECUTION_SAFETY.md` §9. LangGraph не используем: свой state machine + PostgreSQL + arq.
- **[v1.1] Исполнение через Direct API** (`execution/`: реестр возможностей, риск, кворум, предусловие, откат) — `docs/EXECUTION_SAFETY.md`, `docs/API_CONTRACT_EXECUTION.md`. В v1.0 Директ только читается: ручное выполнение пользователем, фиксация и сверка по данным Директа.
- **Миграции:** Alembic (`backend/migrations/`); ORM — SQLAlchemy.
- **LLM:** YandexGPT Pro через адаптер с единым интерфейсом (`ai/`), только обезличенные агрегаты. В v1.0 — только объяснение рекомендации («Почему AdPilot так решил»); «Спросить AI» — v1.1.
- **Уведомления:** Telegram (webhook-роут в FastAPI, отправка из worker; оповещения без названий, утренний дайджест, недельный отчёт); email — только чеки и биллинг.
- **Биллинг:** платёжный провайдер, webhooks (`billing/`).
- **Аутентификация [v1.0]:** вход по номеру телефона + SMS-код через российского SMS-провайдера (юридический HOLD — `docs/LEGAL.md`; в коде пока вход через Яндекс ID, `auth/login.py`). Yandex OAuth — только подключение Директа и Метрики; токены хранятся шифрованными.

## Внешние API
Директ API v5 (v1.0 — только чтение: Reports и параметры объектов для сверки; запись изменений — v1.1), Яндекс.Метрика, Yandex OAuth, YandexGPT, SMS-провайдер (российский, не выбран).

## Развёртывание
Yandex Cloud: одна VM с docker compose (`api`, `worker`, `web`, `redis`, Caddy). PostgreSQL — Managed Service. Секреты — Lockbox / переменные окружения.
