"""Доступ к OAuth-токенам: приложение не видит шифротекст, пишет и сбрасывает токен только функциями,
читает токен только роль воркера app_token — и только в пределах своего workspace."""

import psycopg
import pytest

from app.tenancy import workspace_scope
from test_schema import chain, connected, new_workspace, one  # noqa: F401 — chain: фикстура

TOKEN = b"\xde\xad\xbe\xef"


@pytest.fixture
def token_role(db):
    with db("app_token") as conn:
        yield conn


@pytest.fixture
def conn_id(rw, chain):
    cid = connected(rw, "direct", chain["ws"], f"tok{chain['ws']}", token=TOKEN)
    return cid


@pytest.mark.parametrize("sql", [
    "SELECT * FROM direct_connections",                         # массовое чтение со столбцом токена
    "SELECT token_enc FROM direct_connections",
    "SELECT token_enc FROM metrika_connections",
    "UPDATE direct_connections SET token_enc = '\\x00'",
    "INSERT INTO direct_connections (workspace_id, yandex_login, token_enc, status) VALUES (1, 'x', '\\x00', 'connected')",
    "SELECT connection_token('direct', 1, 1)",                  # чтение токена — не для роли приложения
])
def test_app_role_has_no_token_access(rw, sql):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute(sql)


def test_app_role_sees_everything_but_the_token(rw, chain, conn_id):
    status, has_token = rw.execute("SELECT status, has_token FROM direct_connections WHERE id = %s",
                                   (conn_id,)).fetchone()
    assert (status, has_token) == ("connected", True)


def test_worker_reads_token_only_within_its_workspace(rw, chain, conn_id, token_role):
    assert bytes(one(token_role, "SELECT connection_token('direct', %s, %s)", chain["ws"], conn_id)) == TOKEN
    other_ws = new_workspace(rw, "x")
    with pytest.raises(psycopg.errors.NoDataFound):             # чужой workspace — как будто подключения нет
        token_role.execute("SELECT connection_token('direct', %s, %s)", (other_ws, conn_id))


def test_worker_role_keeps_app_rights(token_role, chain):
    """Права приложения — и его изоляция RLS: в своём workspace (workspace_scope) видно, вне его — нет."""
    assert one(token_role, "SELECT count(*) FROM workspaces WHERE id = %s", chain["ws"]) == 0
    with workspace_scope(token_role, chain["ws"]):
        assert one(token_role, "SELECT count(*) FROM workspaces WHERE id = %s", chain["ws"]) == 1


def test_set_token_cannot_target_another_workspace(rw, chain, conn_id):
    other_ws = new_workspace(rw, "x")
    with pytest.raises(psycopg.errors.NoDataFound):
        rw.execute("SELECT set_connection_token('direct', %s, %s, %s, NULL)", (other_ws, conn_id, b"\x01"))


def test_drop_token_removes_it_and_disconnect_is_final(rw, chain, conn_id, token_role):
    rw.execute("SELECT drop_connection_token('direct', %s, %s, 'disconnected')", (chain["ws"], conn_id))
    rw.execute("SELECT drop_connection_token('direct', %s, %s, 'token_revoked')", (chain["ws"], conn_id))
    assert rw.execute("SELECT status, has_token FROM direct_connections WHERE id = %s",
                      (conn_id,)).fetchone() == ("disconnected", False)  # отзыв не перезаписывает отключение
    with pytest.raises(psycopg.errors.NoDataFound):
        token_role.execute("SELECT connection_token('direct', %s, %s)", (chain["ws"], conn_id))


def test_security_definer_functions_have_fixed_search_path(rw):
    """Иначе вызывающий мог бы подложить свою функцию/таблицу через search_path и выполнить её от имени владельца."""
    rows = rw.execute("""SELECT p.proname, p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                         WHERE n.nspname = 'public' AND p.prosecdef""").fetchall()
    assert {name for name, _ in rows} == {"delete_workspace_data", "purge_search_query_texts", "set_connection_token",
                                          "drop_connection_token", "connection_token", "purge_personal_data",
                                          # доступ и изоляция (D3, D13, D16)
                                          "workspace_role", "user_workspaces", "task_workspace",
                                          "check_organization_has_owner", "check_mandate",
                                          # управление организацией и командой (D3)
                                          "require_org_manager", "create_organization", "create_workspace",
                                          "set_organization_member", "remove_organization_member",
                                          "set_workspace_member", "remove_workspace_member"}
    assert all(cfg and any(c.startswith("search_path=") for c in cfg) for _, cfg in rows)
