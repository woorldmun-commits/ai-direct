"""Здоровье подключений и путь unavailable → recheck → available.
Ответ API меняет статус только для ошибок доступа/токена; ошибки данных и временные — только sync_run."""

from datetime import timedelta

import pytest

from app.sources.direct import RetryLater
from app.tenancy import workspace_scope
from app.worker.guard import load_state
from app.worker.recheck import Available, run_recheck
from app.worker.sync import MAX_REPORT_WAIT, Done, Failed, RetryAt, Skipped, run_sync
from test_direct_sync import TO, campaign_tsv, root  # noqa: F401 — root: фикстура
from test_metrika_sync import metrika  # noqa: F401 — metrika: фикстура
from test_schema import chain, new_workspace, one  # noqa: F401 — chain: фикстура
from test_worker_sync import NOW, Spy, new_run, run_status, work, ws  # noqa: F401 — ws: фикстура

LATER = NOW + timedelta(hours=1)


class CountingSpy(Spy):
    def check_access(self, login):
        self.calls += 1
        if self.raise_first:
            exc, self.raise_first = self.raise_first, None
            raise exc
        super().check_access(login)


def account(rw, ws):
    return rw.execute("SELECT status, unavailable_reason FROM direct_accounts WHERE id = %s",
                      (ws["account"],)).fetchone()


def connection(rw, ws):
    return rw.execute("""SELECT status, last_success_at, last_error, last_error_at, has_token
                         FROM direct_connections WHERE workspace_id = %s""", (ws["ws"],)).fetchone()


def deny(ws, code="access_denied"):
    (ws["root"].path / ws["login"] / "unavailable").write_text(code, encoding="utf-8")


def grant(ws):
    (ws["root"].path / ws["login"] / "unavailable").unlink()


def recheck(rw, ws, spy=None, now=LATER):
    return run_recheck(rw, ws["account"], direct=spy or CountingSpy(ws["root"].path), now=now)


# --- unavailable → recheck → available -----------------------------------------------------------

def test_access_denied_then_granted_then_recheck_restores_sync(rw, ws):
    deny(ws)
    assert work(rw, ws, new_run(rw, ws)) == Failed("access_denied")
    assert account(rw, ws) == ("unavailable", "access_denied")
    assert connection(rw, ws)[2:4] == ("access_denied", NOW)

    spy = CountingSpy(ws["root"].path)                          # пока доступа нет, синхронизация API не трогает
    assert work(rw, ws, new_run(rw, ws), direct=spy) == Skipped("direct_unavailable", "access_denied")
    assert spy.calls == 0

    assert recheck(rw, ws) == Failed("access_denied")            # recheck разрешён и для недоступного аккаунта
    assert account(rw, ws) == ("unavailable", "access_denied")

    grant(ws)                                                    # пользователь выдал доступ
    assert recheck(rw, ws) == Available()
    assert account(rw, ws) == ("active", None)
    status, last_success, last_error, _, _ = connection(rw, ws)
    assert (status, last_success) == ("connected", LATER)
    assert last_error == "access_denied"                         # last_error — история, не текущий статус
    assert isinstance(work(rw, ws, new_run(rw, ws)), Done)


def test_successful_sync_restores_status_and_marks_success(rw, ws):
    """Успешный авторизованный запрос — всегда восстановление: статус connected, причина снята, last_success_at."""
    rw.execute("UPDATE direct_connections SET status = 'api_error' WHERE workspace_id = %s", (ws["ws"],))
    assert recheck(rw, ws) == Available()
    assert connection(rw, ws)[:2] == ("connected", LATER)
    assert isinstance(work(rw, ws, new_run(rw, ws)), Done)
    assert connection(rw, ws)[:2] == ("connected", NOW)


def test_expired_token_is_connection_status_and_recheck_restores_it(rw, ws):
    (ws["root"].path / "connection_error").write_text("token_expired", encoding="utf-8")
    assert work(rw, ws, new_run(rw, ws)) == Failed("token_expired")
    assert connection(rw, ws)[0] == "token_expired" and account(rw, ws) == ("active", None)  # аккаунт ни при чём
    spy = CountingSpy(ws["root"].path)
    assert work(rw, ws, new_run(rw, ws), direct=spy) == Skipped("direct_unavailable", "token_expired")
    assert spy.calls == 0
    (ws["root"].path / "connection_error").unlink()              # токен обновили
    assert recheck(rw, ws) == Available() and connection(rw, ws)[0] == "connected"


def test_revoked_token_drops_token_and_recheck_cannot_help(rw, ws):
    (ws["root"].path / "connection_error").write_text("token_revoked", encoding="utf-8")
    assert work(rw, ws, new_run(rw, ws)) == Failed("token_revoked")
    status, *_, has_token = connection(rw, ws)
    assert (status, has_token) == ("token_revoked", False)       # отозванный токен не храним
    spy = CountingSpy(ws["root"].path)
    assert recheck(rw, ws, spy) == Skipped("direct_unavailable", "token_revoked")  # нужен новый OAuth
    assert spy.calls == 0


# --- ошибки данных и временные не трогают подключение --------------------------------------------

def test_broken_report_does_not_touch_account_or_connection(rw, ws):
    ws["root"]("broken", campaign=campaign_tsv(eval_cost="-1.00"))
    rw.execute("UPDATE direct_accounts SET client_login = 'broken' WHERE id = %s", (ws["account"],))
    assert work(rw, ws, new_run(rw, ws)) == Failed("invalid_report_format", "negative_value")
    assert account(rw, ws) == ("active", None)
    assert connection(rw, ws)[:4] == ("connected", None, None, None)


def test_report_timeout_is_only_the_runs_problem(rw, ws):
    run_id = new_run(rw, ws)
    spy = Spy(ws["root"].path, raise_first=RetryLater(600))
    assert isinstance(work(rw, ws, run_id, direct=spy), RetryAt)
    spy.raise_first = RetryLater(600)
    assert run_sync(rw, run_id, direct=spy, metrika=None, release_id=ws["release"], period_to=TO,
                    now=NOW + MAX_REPORT_WAIT) == Failed("report_timeout", "report_not_ready")
    assert account(rw, ws) == ("active", None) and connection(rw, ws)[:4] == ("connected", None, None, None)


def test_recheck_retry_and_inactive_workspace(rw, ws):
    assert recheck(rw, ws, CountingSpy(ws["root"].path, raise_first=RetryLater(30, "rate_limited"))) == \
        RetryAt(30, "rate_limited")
    rw.execute("UPDATE workspaces SET status = 'deactivated', deactivated_at = now() WHERE id = %s", (ws["ws"],))
    spy = CountingSpy(ws["root"].path)
    assert recheck(rw, ws, spy) == Skipped("workspace_inactive", "deactivated") and spy.calls == 0


# --- Метрика: восстанавливается сама при каждой синхронизации ------------------------------------

def metrika_connection(rw, ws):
    return rw.execute("""SELECT status, last_success_at, last_error FROM metrika_connections
                         WHERE workspace_id = %s""", (ws["ws"],)).fetchone()


@pytest.mark.parametrize("unavailable, expected", [
    ("access_denied", ("permission_missing", None, "access_denied")),     # права — это подключение
    ("report_unavailable", ("connected", None, "report_unavailable")),    # временное — только last_error
])
def test_metrika_errors(rw, ws, tmp_path, unavailable, expected):
    from app.sources.metrika import MetrikaFixture
    (tmp_path / "m" / "555").mkdir(parents=True)
    (tmp_path / "m" / "555" / "unavailable").write_text(unavailable, encoding="utf-8")
    assert isinstance(work(rw, ws, new_run(rw, ws), metrika_source=MetrikaFixture(tmp_path / "m")), Done)
    assert metrika_connection(rw, ws) == expected


def test_metrika_success_restores_connection(rw, ws):
    rw.execute("UPDATE metrika_connections SET status = 'permission_missing' WHERE workspace_id = %s", (ws["ws"],))
    assert isinstance(work(rw, ws, new_run(rw, ws)), Done)
    assert metrika_connection(rw, ws) == ("connected", NOW, None)


# --- приоритет подписки --------------------------------------------------------------------------

def subscription(rw, ws, status, end_days):
    rw.execute("""INSERT INTO subscriptions (workspace_id, plan, status, price, current_period_start, current_period_end)
                  VALUES (%s, 'start', %s, 4990, %s, %s)""",
               (ws["ws"], status, NOW - timedelta(40), NOW + timedelta(end_days)))


def test_active_subscription_wins_over_later_history(rw, ws):
    subscription(rw, ws, "expired", 30)          # историческая запись с более поздним концом периода
    s = load_state(rw, ws["ws"], ws["account"], NOW)
    assert s.subscription_status == "active" and s.paid


def test_without_active_the_latest_ended_is_reported(rw, ws):
    rw.execute("UPDATE subscriptions SET status = 'expired' WHERE workspace_id = %s", (ws["ws"],))
    subscription(rw, ws, "expired", -30)
    s = load_state(rw, ws["ws"], ws["account"], NOW)
    assert (s.subscription_status, s.subscription_period_end, s.paid) == ("expired", NOW + timedelta(10), False)
    never_paid = new_workspace(rw, "new")
    assert load_state(rw, never_paid, None, NOW).subscription_status is None


# --- Регрессии из ревью ---------------------------------------------------------------------------

@pytest.mark.parametrize("closed", ["disconnected", "token_revoked"])
def test_api_error_does_not_resurrect_closed_connection(rw, ws, closed):
    """Пользователь отключил Директ, а запоздавшая синхронизация получила token_expired: статус остаётся закрытым."""
    from app.worker.health import direct_failure
    conn_id = one(rw, "SELECT id FROM direct_connections WHERE workspace_id = %s", ws["ws"])
    rw.execute("SELECT drop_connection_token('direct', %s, %s, %s)", (ws["ws"], conn_id, closed))
    direct_failure(rw, ws["account"], "token_expired", LATER)
    assert connection(rw, ws)[0] == closed


def test_repeated_failure_keeps_since_when(rw, ws):
    from app.worker.health import direct_failure
    direct_failure(rw, ws["account"], "token_expired", NOW)
    direct_failure(rw, ws["account"], "token_expired", LATER)
    assert one(rw, "SELECT status_changed_at FROM direct_connections WHERE workspace_id = %s", ws["ws"]) == NOW


def test_metrika_access_denied_does_not_resurrect_disconnected(rw, ws):
    from app.worker.health import metrika_result
    mconn = one(rw, "SELECT id FROM metrika_connections WHERE workspace_id = %s", ws["ws"])
    rw.execute("SELECT drop_connection_token('metrika', %s, %s, 'disconnected')", (ws["ws"], mconn))
    metrika_result(rw, ws["counter"], "access_denied", NOW)
    assert metrika_connection(rw, ws)[0] == "disconnected"


# --- RLS: recheck под прикладной ролью воркера (D13) -----------------------------------------------

def test_recheck_runs_under_worker_role_only_in_own_workspace(db, rw, ws):
    other = new_workspace(rw, "other-recheck")
    deny(ws)
    assert work(rw, ws, new_run(rw, ws)) == Failed("access_denied")
    grant(ws)
    with db("app_token") as worker:
        with workspace_scope(worker, other):  # изнутри чужого workspace аккаунт не раскрывается
            assert recheck(worker, ws) == Skipped("account_not_found")
        assert account(rw, ws) == ("unavailable", "access_denied")
        assert recheck(worker, ws) == Available()
        assert one(worker, "SELECT count(*) FROM direct_accounts") == 0  # после задачи — ничего
    assert account(rw, ws) == ("active", None)
