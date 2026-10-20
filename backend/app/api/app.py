"""Фабрика приложения API. Запуск: `uvicorn app.api:create_app --factory` (настройки — из окружения, settings.py).

Базовый путь /api/v1 (API_CONTRACT.md §1). Документация OpenAPI не публикуется: CSP API — default-src 'none'."""

from contextlib import asynccontextmanager
from threading import BoundedSemaphore

from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from app.api import errors
from app.api.auth import router as auth_router
from app.api.email_auth import router as email_auth_router
from app.api.db import create_pool
from app.api.legal import router as legal_router
from app.api.workspace_insights import router as insights_router
from app.api.recommendation_flow import router as recommendation_flow_router
from app.api.middleware import BoundaryMiddleware
from app.api.routes import router
from app.api.today import router as today_router
from app.api.settings import Settings

PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, pool: ConnectionPool | None = None) -> FastAPI:
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
    # Reserve a DB slot for ordinary traffic when the pool has more than one connection.
    app.state.auth_callbacks = BoundedSemaphore(max(1, settings.pool_max_size - 1))
    app.state.email_kdf_slots = BoundedSemaphore(2)
    errors.install(app)
    app.include_router(router, prefix=PREFIX)
    app.include_router(today_router, prefix=PREFIX)
    app.include_router(auth_router, prefix=PREFIX)
    app.include_router(email_auth_router, prefix=PREFIX)
    app.include_router(legal_router, prefix=PREFIX)
    app.include_router(insights_router, prefix=PREFIX)
    app.include_router(recommendation_flow_router, prefix=PREFIX)
    app.add_middleware(BoundaryMiddleware, settings=settings)
    return app
