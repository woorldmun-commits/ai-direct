import os
import tempfile
from pathlib import Path

import psycopg
import pytest

SCHEMA = Path(__file__).parents[1] / "db" / "schema.sql"
ROLES = ("app_migrator", "app_rw", "app_token", "app_system", "app_deleter")


def _admin_uri() -> str:
    """Суперпользовательский DSN: TEST_DATABASE_URL в CI, иначе встроенный PostgreSQL (pgserver) локально."""
    if uri := os.environ.get("TEST_DATABASE_URL"):
        return uri
    import pgserver

    return pgserver.get_server(Path(tempfile.gettempdir()) / "ai-direct-pgtest", cleanup_mode="stop").get_uri()


def _with_user(uri: str, user: str, dbname: str) -> str:
    return psycopg.conninfo.make_conninfo(uri, user=user, dbname=dbname)


@pytest.fixture(scope="session")
def db():
    """Чистая БД со схемой, накатанной ролью-владельцем. Возвращает фабрику подключений по ролям."""
    admin = _admin_uri()
    dbname = "ai_direct_test"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {dbname}")
        for role in ROLES:
            conn.execute(
                f"DO $$ BEGIN CREATE ROLE {role} LOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            )
        conn.execute("GRANT app_rw TO app_token")  # воркер = права приложения + чтение токенов
        conn.execute("GRANT app_rw TO app_system")  # системные задачи = права приложения без фильтра RLS
        conn.execute(f"CREATE DATABASE {dbname} OWNER app_migrator")
    with psycopg.connect(_with_user(admin, "postgres", dbname), autocommit=True) as conn:
        conn.execute("GRANT CREATE, USAGE ON SCHEMA public TO app_migrator")
        conn.execute("GRANT USAGE ON SCHEMA public TO app_rw, app_token, app_system, app_deleter")
    with psycopg.connect(_with_user(admin, "app_migrator", dbname), autocommit=True) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))

    def connect(role: str) -> psycopg.Connection:
        return psycopg.connect(_with_user(admin, role, dbname), autocommit=True)

    return connect


@pytest.fixture
def rw(db):
    """Подготовка данных тестов и системные задачи: права приложения (app_rw) без фильтра RLS по workspace.
    Изоляцию прикладной роли проверяют тесты с db("app_rw") и workspace_scope (test_rls.py)."""
    with db("app_system") as conn:
        yield conn
