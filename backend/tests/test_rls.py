"""Изоляция арендаторов (D13): RLS прикладной роли — второй барьер. Запрос без фильтра по workspace не возвращает
чужого клиента; без app.workspace_id прикладная роль не видит ничего; системная роль видит всё."""

import psycopg
import pytest

from app.tenancy import set_local_workspace, workspace_scope
from test_schema import chain, connected, new_workspace, one  # noqa: F401 — chain: фикстура

# Таблицы без собственного workspace_id, защищённые через родителя (EXISTS по ключу родителя).
VIA_PARENT = {"direct_accounts", "metrika_counters", "stat_rows", "search_query_sightings", "audit_run_snapshots",
              "findings", "explanations", "recommendations", "recommendation_events", "recommendation_results",
              "measurements", "subscription_events", "payments"}
# Сознательно без RLS (schema.sql «Изоляция арендаторов»): данные пользователя и глобальные таблицы.
NO_RLS = {"users", "yandex_identities", "sessions", "telegram_links", "organizations", "organization_memberships",
          "releases", "free_audit_claims",
          # вход по телефону: не данные workspace; рабочим ролям таблицы недоступны вовсе — только функции
          "phone_auth_codes", "phone_auth_events",
          # справочник имён площадок РСЯ: глобальный (id — хэш имени, одинаковый во всех workspace), имя — домен или
          # приложение, не ПД; строка не говорит, чей кабинет. app_rw: SELECT + INSERT, без UPDATE/DELETE
          "placement_names"}


def rls_tables(conn) -> set[str]:
    return {r[0] for r in conn.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                                          WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity""")}


@pytest.fixture
def app(db):
    with db("app_rw") as conn:
        yield conn


@pytest.fixture
def other(rw):
    """Чужой workspace со своими строками: подключение, аккаунт, подписка, событие outbox."""
    ws = new_workspace(rw, "other")
    account = one(rw, "INSERT INTO direct_accounts (direct_connection_id) VALUES (%s) RETURNING id",
                  connected(rw, "direct", ws, f"o{ws}"))
    rw.execute("""INSERT INTO subscriptions (workspace_id, plan, status, price, current_period_start, current_period_end)
                  VALUES (%s, 'start', 'active', 4990, now(), now() + interval '1 month')""", (ws,))
    rw.execute("""INSERT INTO outbox_events (workspace_id, event_type, aggregate_type, aggregate_id)
                  VALUES (%s, 'x', 'y', 1)""", (ws,))
    return {"ws": ws, "account": account}


def test_every_table_is_classified(rw):
    """Новая таблица не останется без решения: либо RLS, либо явно в списке «без RLS»."""
    tables = {r[0] for r in rw.execute("""SELECT tablename FROM pg_tables WHERE schemaname = 'public'""")}
    assert rls_tables(rw) | NO_RLS == tables and not (rls_tables(rw) & NO_RLS)
    with_ws = {r[0] for r in rw.execute("""SELECT table_name FROM information_schema.columns
                                           WHERE table_schema = 'public' AND column_name = 'workspace_id'
                                             AND table_name IN (SELECT tablename FROM pg_tables)""")}
    assert with_ws | VIA_PARENT | {"workspaces"} <= rls_tables(rw)


def test_without_workspace_app_role_sees_nothing(app, rw, chain, other):
    """Ни одной строки ни одного workspace — по всем таблицам под RLS (в БД есть данные многих тестов)."""
    for table in sorted(rls_tables(rw)):
        cols = "workspace_id" if table in ("direct_connections", "metrika_connections") else "*"
        # оферта и согласия — документы пользователя, не workspace (как users); мандаты агентства — под RLS
        where = " WHERE workspace_id IS NOT NULL" if table == "legal_acceptances" else ""
        assert one(app, f"SELECT count({cols}) FROM {table}{where}") == 0, table


def test_with_workspace_only_own_rows(app, rw, chain, other):
    with workspace_scope(app, chain["ws"]):
        # «забыли фильтр» — всё равно только свой клиент
        assert {r[0] for r in app.execute("SELECT id FROM recommendations")} == {chain["rec"]}
        assert {r[0] for r in app.execute("SELECT workspace_id FROM direct_connections")} == {chain["ws"]}
        assert {r[0] for r in app.execute("SELECT id FROM workspaces")} == {chain["ws"]}
        assert one(app, "SELECT count(*) FROM direct_accounts WHERE id = %s", other["account"]) == 0
        assert one(app, "SELECT count(*) FROM subscriptions WHERE workspace_id = %s", other["ws"]) == 0
        assert one(app, "SELECT count(*) FROM findings WHERE id = %s", chain["finding"]) == 1
        assert one(app, "SELECT count(*) FROM explanations WHERE id = %s", chain["explanation"]) == 1
    with workspace_scope(app, other["ws"]):
        assert one(app, "SELECT count(*) FROM recommendations") == 0
        assert one(app, "SELECT count(*) FROM explanations WHERE id = %s", chain["explanation"]) == 0
        assert one(app, "SELECT count(*) FROM outbox_events") == 1


def test_cannot_write_into_or_change_another_workspace(app, chain, other):
    with workspace_scope(app, chain["ws"]):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="row-level security"):
            app.execute("""INSERT INTO outbox_events (workspace_id, event_type, aggregate_type, aggregate_id)
                           VALUES (%s, 'x', 'y', 1)""", (other["ws"],))
        with pytest.raises(psycopg.errors.IntegrityConstraintViolation):  # ссылка на невидимый чужой аккаунт
            app.execute("""INSERT INTO sync_runs (workspace_id, direct_account_id, kind)
                           VALUES (%s, %s, 'scheduled')""", (chain["ws"], other["account"]))
        changed = app.execute("UPDATE direct_accounts SET is_selected = true WHERE id = %s", (other["account"],))
        assert changed.rowcount == 0  # чужой строки для прикладной роли нет


def test_worker_role_is_isolated_too(db, chain):
    with db("app_token") as worker:
        assert one(worker, "SELECT count(*) FROM issues") == 0
        with workspace_scope(worker, chain["ws"]):
            assert one(worker, "SELECT count(*) FROM issues WHERE workspace_id = %s", chain["ws"]) == 1


def test_system_role_sees_all_workspaces(rw, chain, other):
    assert one(rw, "SELECT count(DISTINCT workspace_id) FROM direct_connections WHERE workspace_id IN (%s, %s)",
               chain["ws"], other["ws"]) == 2


def test_organization_context_opens_nothing(app, rw, chain):
    """Организационного контекста нет: app.organization_id не открывает ни workspace, ни команду."""
    org = one(rw, "SELECT organization_id FROM workspaces WHERE id = %s", chain["ws"])
    with app.transaction():
        app.execute("SELECT set_config('app.organization_id', %s, true)", (str(org),))
        assert one(app, "SELECT count(*) FROM workspaces") == 0
        assert one(app, "SELECT count(*) FROM workspace_memberships") == 0
        assert {r[0] for r in app.execute("SELECT workspace_id FROM user_workspaces(%s)", (chain["user"],))} == \
            {chain["ws"]}  # список своих workspace — функцией


# --- функции SECURITY DEFINER сверяют workspace с контекстом ----------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT set_connection_token('direct', %(ws)s, %(conn)s, '\\x02', NULL)",
    "SELECT drop_connection_token('direct', %(ws)s, %(conn)s, 'disconnected')",
    "SELECT connection_token('direct', %(ws)s, %(conn)s)",
])
def test_token_functions_reject_workspace_other_than_context(db, rw, chain, other, sql):
    conn_id = one(rw, "SELECT id FROM direct_connections WHERE workspace_id = %s", chain["ws"])
    with db("app_token") as worker:
        with workspace_scope(worker, other["ws"]), \
                pytest.raises(psycopg.errors.InsufficientPrivilege, match="not the current workspace"):
            worker.execute(sql, {"ws": chain["ws"], "conn": conn_id})
        assert one(rw, "SELECT has_token FROM direct_connections WHERE id = %s", conn_id)  # токен не тронут
        # без контекста (системная задача, OAuth-колбэк до входа) — workspace только явным параметром
        assert worker.execute("SELECT connection_token('direct', %s, %s)", (chain["ws"], conn_id)).fetchone()[0]


def test_task_workspace_is_hidden_from_another_workspace(app, chain, other):
    assert one(app, "SELECT task_workspace('direct_account', %s)", chain["account"]) == chain["ws"]
    with workspace_scope(app, other["ws"]):
        assert one(app, "SELECT task_workspace('direct_account', %s)", chain["account"]) is None
        assert one(app, "SELECT task_workspace('direct_account', %s)", other["account"]) == other["ws"]


# --- помощники входа в workspace -------------------------------------------------------------------

def test_set_local_lives_until_end_of_transaction(app, chain):
    with pytest.raises(RuntimeError):
        set_local_workspace(app, chain["ws"])  # autocommit: значение не пережило бы запрос
    with app.transaction():
        set_local_workspace(app, chain["ws"])
        assert one(app, "SELECT count(*) FROM issues") == 1
    assert one(app, "SELECT count(*) FROM issues") == 0


def test_scope_is_reset_after_task_even_on_error(app, chain, other):
    with pytest.raises(ZeroDivisionError), workspace_scope(app, chain["ws"]):
        assert one(app, "SELECT count(*) FROM issues") == 1
        1 / 0
    assert one(app, "SELECT count(*) FROM issues") == 0  # соединение вернётся в пул без чужого workspace
    with pytest.raises(RuntimeError), workspace_scope(app, chain["ws"]), workspace_scope(app, other["ws"]):
        pass  # задача одного workspace не переходит в чужой
    with workspace_scope(app, chain["ws"]), workspace_scope(app, chain["ws"]):  # повторный вход в тот же — можно
        assert one(app, "SELECT count(*) FROM issues") == 1
    assert one(app, "SELECT current_setting('app.workspace_id', true)") == ""


@pytest.mark.parametrize("bad", [0, -1, "1 OR true", None, True])
def test_scope_rejects_non_ids(app, bad):
    with pytest.raises(ValueError), workspace_scope(app, bad):
        pass
