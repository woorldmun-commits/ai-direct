"""Пул соединений прикладной роли и транзакция запроса.

Один запрос — одно соединение и одна транзакция: аутентификация, вход в workspace (SET LOCAL app.workspace_id,
app/tenancy.py) и чтение данных идут в ней. SET LOCAL живёт до конца транзакции, поэтому соединение уходит в пул
без контекста workspace. Пул это проверяет (reset): соединение с выставленным app.workspace_id — значит, кто-то
выставил его на сессию в обход tenancy — в пул не возвращается, а закрывается.

configure: соединение API — только роль без суперпользователя и без BYPASSRLS: иначе RLS (второй барьер) молча
отключился бы."""

from typing import Iterator

import psycopg
from fastapi import Request
from psycopg_pool import ConnectionPool

from app.api.settings import Settings


class UnsafeDatabaseRole(RuntimeError):
    pass


def _configure(conn: psycopg.Connection) -> None:
    # Проверяется имя роли, а не только флаги: владелец таблиц (app_migrator) не попадает под RLS без FORCE,
    # у app_system политика USING (true), app_token читает OAuth-токены любого workspace.
    with conn.transaction():
        row = conn.execute("""SELECT current_user = 'app_rw' AND NOT (r.rolsuper OR r.rolbypassrls) FROM pg_roles r
                              WHERE r.rolname = current_user""").fetchone()
    if row is None or not row[0]:
        raise UnsafeDatabaseRole("API connects only as a role under RLS (app_rw), not superuser / BYPASSRLS")


def _reset(conn: psycopg.Connection) -> None:
    """Вызывается пулом после возврата соединения (транзакция уже завершена). Контекст workspace должен быть пуст."""
    with conn.transaction():
        leaked = conn.execute("SELECT current_setting('app.workspace_id', true)").fetchone()[0]
    if leaked:
        raise RuntimeError("connection returned to the pool with app.workspace_id set")  # пул закроет соединение


def create_pool(settings: Settings) -> ConnectionPool:
    return ConnectionPool(settings.database_url, min_size=settings.pool_min_size, max_size=settings.pool_max_size,
                          timeout=settings.pool_timeout, open=False, configure=_configure, reset=_reset,
                          kwargs={"autocommit": False}, name="api")


def request_connection(request: Request) -> Iterator[psycopg.Connection]:
    """Зависимость (scope="function"): соединение в транзакции запроса. Исключение — откат, иначе COMMIT до ответа."""
    pool: ConnectionPool = request.app.state.pool
    with pool.connection() as conn:
        with conn.transaction():
            yield conn
