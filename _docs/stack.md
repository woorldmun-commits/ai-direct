# Стек ai-direct

Источник: `docs/ARCHITECTURE.md` (§1, §9–11) и `docs/PRD.md` (§8); объём версий — `docs/VERSION_SCOPE.md`. Здесь только выжимка; при расхождении прав первоисточник.

## Уже есть в коде
- **Бэкенд:** Python, FastAPI (REST + webhooks). Зависимости: `pydantic>=2`, `psycopg[binary]`.
- **БД:** PostgreSQL. Схема — `backend/db/schema.sql`; инварианты продублированы `CHECK`-ограничениями.
- **Тесты:** pytest (`backend/pytest.ini`, `pythonpath = .`), запуск из `backend/`. Схему проверяет встроенный `pgserver` (Python ≤ 3.12) или `TEST_DATABASE_URL` в CI.
- **Модули `backend/app/`:** `contract` (Value и инварианты), `sources` (Директ, Метрика), `sync` (парсинг, санитизация, снимки), `rules` (rule engine), `audit`.

## Запланировано (ещё нет в репозитории)
- **Очереди и расписания:** Redis + arq (`worker.py`; cron встроен, Celery не нужен). Семейства задач с отдельными ролями БД — `docs/ARCHITECTURE.md`. LangGraph не используем: свой state machine + PostgreSQL + arq.
- **Фронтенд:** Next.js (App Router), каталог `frontend/`.
- **Миграции:** Alembic (`backend/migrations/`); ORM — SQLAlchemy.
- **LLM:** YandexGPT Pro через адаптер с единым интерфейсом (`ai/`), только обезличенные агрегаты.
- **Уведомления:** Telegram (webhook-роут в FastAPI, отправка из worker), email.
- **Биллинг:** платёжный провайдер, webhooks (`billing/`).
- **Аутентификация [v1.0]:** вход по номеру телефона + SMS-код через российского SMS-провайдера (юридический HOLD — `docs/LEGAL.md`; в коде пока вход через Яндекс ID, `auth/login.py`). Yandex OAuth — только подключение Директа и Метрики; токены хранятся шифрованными.

## Внешние API
Директ API v5 (Reports и запись изменений по одобрению), Яндекс.Метрика, Yandex OAuth, YandexGPT, SMS-провайдер (российский, не выбран).

## Развёртывание
Yandex Cloud: одна VM с docker compose (`api`, `worker`, `web`, `redis`, Caddy). PostgreSQL — Managed Service. Секреты — Lockbox / переменные окружения.
