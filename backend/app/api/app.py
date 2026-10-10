"""Фабрика приложения API. Запуск: `uvicorn app.api:create_app --factory` (настройки — из окружения, settings.py).

Базовый путь /api/v1 (API_CONTRACT.md §1). Документация OpenAPI не публикуется: CSP API — default-src 'none'."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from app.api import errors
from app.api.db import create_pool
from app.api.integrations import router as integrations_router
from app.api.middleware import BoundaryMiddleware
from app.api.ratelimit import RateLimitMiddleware
from app.api.routes import router
from app.api.phone_login import router as phone_router
from app.api.sessions import router as sessions_router
from app.api.today import router as today_router
from app.api.settings import Settings
from app.flags import flag

PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, pool: ConnectionPool | None = None, **services) -> FastAPI:
    """services — подмена внешних зависимостей (app/api/services.py: login_app, api_app, http, token_keys, …)."""
    settings = settings or Settings.from_env()
    pool = pool or create_pool(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool.open(wait=True, timeout=settings.pool_timeout)  # роль БД проверяется при первом соединении (db.py)
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.pool = pool
    app.state.services = dict(services)
    errors.install(app)
    app.include_router(router, prefix=PREFIX)
    app.include_router(today_router, prefix=PREFIX)
    app.include_router(sessions_router, prefix=PREFIX)
    app.include_router(integrations_router, prefix=PREFIX)
    if flag("sms_login"):  # юридический HOLD: без флага маршрутов /auth/code/* нет (404)
        app.include_router(phone_router, prefix=PREFIX)
    # Порядок: последний добавленный — внешний. Boundary снаружи: 429 лимита получает request_id и заголовки.
    app.add_middleware(RateLimitMiddleware, trusted=settings.trusted_proxies)
    app.add_middleware(BoundaryMiddleware, settings=settings)
    return app
