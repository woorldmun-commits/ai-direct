# Стек ai-direct

Источник: `docs/ARCHITECTURE.md` (§1, §9–11) и `docs/PRD.md` (§8). Здесь только выжимка; при расхождении прав первоисточник.

## Уже есть в коде
- **Бэкенд:** Python, FastAPI (REST + webhooks). Зависимости: `pydantic>=2`, `psycopg[binary]`.
- **БД:** PostgreSQL. Схема — `backend/db/schema.sql`; инварианты продублированы `CHECK`-ограничениями.
- **Тесты:** pytest (`backend/pytest.ini`, `pythonpath = .`), запуск из `backend/`. Схему проверяет встроенный `pgserver` (Python ≤ 3.12) или `TEST_DATABASE_URL` в CI.
- **Модули `backend/app/`:** `contract` (Value и инварианты), `sources` (Директ, Метрика), `sync` (парсинг, санитизация, снимки), `rules` (rule engine), `audit`.

## Запланировано (ещё нет в репозитории)
- **Очереди и расписания:** Redis + arq (`worker.py`; cron встроен, Celery не нужен).
- **Фронтенд:** Next.js (App Router), каталог `frontend/`.
- **Миграции:** Alembic (`backend/migrations/`); ORM — SQLAlchemy.
- **LLM:** YandexGPT Pro через адаптер с единым интерфейсом (`ai/`), только обезличенные агрегаты.
- **Уведомления:** Telegram (webhook-роут в FastAPI, отправка из worker), email.
- **Биллинг:** платёжный провайдер, webhooks (`billing/`).
- **Аутентификация:** Yandex OAuth, токены хранятся шифрованными.

## Внешние API
Директ API v5 (Reports), Яндекс.Метрика, Yandex OAuth, YandexGPT.

## Развёртывание
Yandex Cloud: одна VM с docker compose (`api`, `worker`, `web`, `redis`, Caddy). PostgreSQL — Managed Service. Секреты — Lockbox / переменные окружения.
