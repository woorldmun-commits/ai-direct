"""Защиты схемы из ревью: ссылки только внутри своего workspace, жизненные циклы sync_run и issue только вперёд,
коды вместо свободного текста. Каждый тест — сценарий, который раньше проходил."""

import psycopg
import pytest

from test_schema import connected, chain, key, new_workspace, one  # noqa: F401 — chain: фикстура


@pytest.fixture
def other(rw, chain):
    """Чужой workspace со своим подключением Директа и аккаунтом."""
    ws = new_workspace(rw, "other")
    conn = connected(rw, "direct", ws, f"other{ws}")
    account = one(rw, "INSERT INTO direct_accounts (direct_connection_id) VALUES (%s) RETURNING id", conn)
    return {"ws": ws, "account": account}


# --- ссылки только внутри своего workspace -------------------------------------------------------

def test_sync_run_cannot_point_to_account_of_another_workspace(rw, chain, other):
    """Иначе удаление workspace владельца аккаунта навсегда упало бы на внешнем ключе."""
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("INSERT INTO sync_runs (workspace_id, direct_account_id, kind) VALUES (%s, %s, 'scheduled')",
                   (chain["ws"], other["account"]))


def test_issue_cannot_point_to_account_of_another_workspace(rw, chain, other):
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("""INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                      VALUES (%s, %s, %s, 'high_cpa', 'campaign', 1)""",
                   (chain["ws"], other["account"], key("x", other["account"])))


def test_digest_cannot_reference_snapshot_of_another_workspace(rw, chain, other):
    audit = one(rw, "SELECT audit_run_id FROM findings WHERE id = %s", chain["finding"])
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("""INSERT INTO digests (workspace_id, kind, snapshot_id, audit_run_id, payload)
                      VALUES (%s, 'daily', %s, %s, '{}')""", (other["ws"], chain["snapshot"], audit))


def test_snapshot_needs_own_running_sync_run(rw, chain, other):
    queued = one(rw, "INSERT INTO sync_runs (workspace_id, direct_account_id, kind) VALUES (%s, %s, 'scheduled') "
                     "RETURNING id", chain["ws"], chain["account"])
    insert = """INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to, data_until,
                  partial_from, sources)
                VALUES (%s, %s, %s, '2026-08-25', '2026-09-30', now(), '2026-09-28', '{yandex_direct}')"""
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):  # запуск ещё не начат
        rw.execute(insert, (chain["ws"], queued, chain["release"]))
    rw.execute("UPDATE sync_runs SET status = 'running' WHERE id = %s", (queued,))
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):  # снимок в чужой workspace
        rw.execute(insert, (other["ws"], queued, chain["release"]))
    rw.execute(insert, (chain["ws"], queued, chain["release"]))


# --- жизненные циклы только вперёд ---------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "UPDATE sync_runs SET status = 'queued', finished_at = NULL WHERE id = %s",           # откат завершённого
    "UPDATE sync_runs SET error_code = 'x', status = 'failed' WHERE id = %s",             # переписать итог
])
def test_finished_sync_run_is_immutable(rw, chain, sql):
    run = one(rw, "SELECT sync_run_id FROM snapshots WHERE id = %s", chain["snapshot"])  # succeeded
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute(sql, (run,))


def test_sync_run_identity_is_frozen(rw, chain, other):
    run = one(rw, "INSERT INTO sync_runs (workspace_id, direct_account_id, kind) VALUES (%s, %s, 'scheduled') "
                  "RETURNING id", chain["ws"], chain["account"])
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("UPDATE sync_runs SET kind = 'resync' WHERE id = %s", (run,))
    rw.execute("UPDATE sync_runs SET status = 'running' WHERE id = %s", (run,))
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("UPDATE sync_runs SET status = 'queued' WHERE id = %s", (run,))


@pytest.mark.parametrize("sql", [
    "UPDATE issues SET issue_key = %(other_key)s WHERE id = %(id)s",          # подменить идентичность проблемы
    "UPDATE issues SET object_id = 999 WHERE id = %(id)s",
])
def test_open_issue_can_only_be_closed(rw, chain, sql):
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute(sql, {"id": chain["issue"], "other_key": key("other")})
    rw.execute("UPDATE issues SET closed_at = now(), close_reason = 'resolved' WHERE id = %s", (chain["issue"],))


def test_closed_issue_cannot_be_reopened(rw, chain):
    """Проблема вернулась — это новая строка issues (DATA_MODEL.md §4), история закрытой не переписывается."""
    rw.execute("UPDATE issues SET closed_at = now(), close_reason = 'resolved' WHERE id = %s", (chain["issue"],))
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("UPDATE issues SET closed_at = NULL, close_reason = NULL WHERE id = %s", (chain["issue"],))


# --- коды вместо свободного текста ---------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "UPDATE sync_runs SET status = 'failed', finished_at = now(), error_code = 'x', "
    "error_reason = 'Server said: login ivan.petrov' WHERE id = %s",              # текст сервера с ПД
    "UPDATE workspace_settings SET attribution_model = 'linear' WHERE workspace_id = %s",
    "UPDATE workspace_settings SET attribution_model = 'lastsign' WHERE workspace_id = %s",  # устаревшая модель
])
def test_codes_not_free_text(rw, chain, sql):
    if "workspace_settings" in sql:
        rw.execute("INSERT INTO workspace_settings (workspace_id) VALUES (%s)", (chain["ws"],))
        target = chain["ws"]
    else:
        target = one(rw, "INSERT INTO sync_runs (workspace_id, direct_account_id, kind) VALUES (%s, %s, 'scheduled') "
                         "RETURNING id", chain["ws"], chain["account"])
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute(sql, (target,))


def test_app_role_cannot_create_objects(rw):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("CREATE TABLE sneaky (id int)")
