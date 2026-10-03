"""Guard, блокировки workspace и воркер синхронизации. Состояние читается в момент выполнения: задача, поставленная
в очередь до деактивации или истечения подписки, после неё не делает ни запросов к API, ни записей."""

from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from app.rules import RULES
from app.rules.domain import AuditSettings, Finding, run
from app.sources.direct import DirectFixture, RetryLater
from app.sync.store import load_view
from app.tenancy import set_local_workspace
from app.worker.guard import RULES as GUARD_RULES
from app.worker.guard import Allow, Skip, State, Task, guard, load_state
from app.worker.locks import workspace_exclusive, workspace_shared
from app.worker.sync import PLACEMENTS_REPORT_ENV, Done, Failed, RetryAt, Skipped, run_sync
from test_direct_sync import CAMPAIGN_RULES, TO, root  # noqa: F401 — root: фикстура
from test_metrika_sync import metrika  # noqa: F401 — metrika: фикстура
from test_schema import connected, chain, one  # noqa: F401 — chain: фикстура

NOW = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)


# --- Guard: таблица решений ----------------------------------------------------------------------

def state(**kw) -> State:
    base = dict(workspace_status="active", subscription_status="active", subscription_period_end=NOW + timedelta(9),
                direct_status="connected", direct_account_status="active", direct_unavailable_reason=None, now=NOW)
    return State(**{**base, **kw})


@pytest.mark.parametrize("task, kw, expected", [
    (Task.SYNC, {}, Allow()),
    (Task.SYNC, dict(workspace_status="deactivated"), Skip("workspace_inactive", "deactivated")),
    (Task.SYNC, dict(workspace_status="deletion_pending"), Skip("workspace_inactive", "deletion_pending")),
    (Task.SYNC, dict(subscription_status=None), Skip("subscription_inactive", "none")),
    (Task.SYNC, dict(subscription_status="expired"), Skip("subscription_inactive", "expired")),
    (Task.SYNC, dict(subscription_status="past_due"), Allow()),                                      # грейс 3 дня
    # верхняя граница и для active/past_due: опоздавшая задача истечения не даёт бессрочный доступ
    (Task.SYNC, dict(subscription_status="active", subscription_period_end=NOW - timedelta(days=3)),
     Skip("subscription_inactive", "active")),
    (Task.SYNC, dict(subscription_status="past_due", subscription_period_end=NOW - timedelta(days=2)), Allow()),
    (Task.SYNC, dict(subscription_status="canceled"), Allow()),                                      # до конца периода
    (Task.SYNC, dict(subscription_status="canceled", subscription_period_end=NOW),
     Skip("subscription_inactive", "canceled")),
    # одна проверка Директа — причина внутри: UI показывает конкретное действие
    (Task.SYNC, dict(direct_status="token_expired"), Skip("direct_unavailable", "token_expired")),
    (Task.SYNC, dict(direct_status=None), Skip("direct_unavailable", "not_connected")),
    (Task.SYNC, dict(direct_account_status="unavailable", direct_unavailable_reason="access_denied"),
     Skip("direct_unavailable", "access_denied")),
    (Task.SYNC, dict(direct_status="token_revoked", direct_account_status="unavailable",
                     direct_unavailable_reason="access_denied"), Skip("direct_unavailable", "token_revoked")),
    (Task.AUDIT, dict(direct_status="token_expired"), Allow()),                  # аудит читает снимок, не API
    (Task.AUDIT, dict(subscription_status="expired"), Skip("subscription_inactive", "expired")),
    (Task.MEASURE, dict(subscription_status="expired"), Skip("subscription_inactive", "expired")),
    (Task.NOTIFY, dict(subscription_status="expired"), Skip("subscription_inactive", "expired")),
    (Task.NOTIFY_BILLING, dict(subscription_status="expired"), Allow()),
    (Task.NOTIFY, dict(workspace_status=None), Skip("workspace_inactive", None)),
    (Task.DELETE, dict(workspace_status="deletion_pending", subscription_status=None, direct_status=None), Allow()),
    (Task.DELETE, dict(workspace_status=None), Skip("workspace_deleted")),
])
def test_guard_table(task, kw, expected):
    assert guard(task, state(**kw)) == expected


def test_every_task_has_rules():
    assert set(GUARD_RULES) == set(Task)


def test_first_failing_check_is_the_reason():
    """Причина — самая ранняя: деактивированному workspace не говорят «переподключите Директ»."""
    assert guard(Task.SYNC, state(workspace_status="deactivated", direct_status="token_expired")) == \
        Skip("workspace_inactive", "deactivated")


# --- Воркер синхронизации ------------------------------------------------------------------------

class Spy(DirectFixture):
    """Fixture Директа, которая считает запросы и может выполнить действие «пока идёт отчёт»."""

    def __init__(self, path, during_fetch=None, raise_first=None):
        super().__init__(path)
        self.calls, self.during_fetch, self.raise_first = 0, during_fetch, raise_first

    def fetch_report(self, *args):
        self.calls += 1
        if self.raise_first:
            exc, self.raise_first = self.raise_first, None
            raise exc
        if self.during_fetch:
            self.during_fetch()
        return super().fetch_report(*args)


@pytest.fixture
def ws(rw, chain, root, metrika):
    """Оплаченный workspace: Директ подключён, выбран счётчик 555 с целями 111, 222; отчёты — в fixtures."""
    rw.execute("""INSERT INTO subscriptions (workspace_id, plan, status, price, current_period_start, current_period_end)
                  VALUES (%s, 'start', 'active', 4990, %s, %s)""", (chain["ws"], NOW - timedelta(20), NOW + timedelta(10)))
    mconn = connected(rw, "metrika", chain["ws"], "owner")
    counter = one(rw, """INSERT INTO metrika_counters (metrika_connection_id, counter_id, is_selected, goal_ids)
                         VALUES (%s, 555, true, '{222,111}') RETURNING id""", mconn)
    login = one(rw, """SELECT c.yandex_login FROM direct_accounts a JOIN direct_connections c
                       ON c.id = a.direct_connection_id WHERE a.id = %s""", chain["account"])
    root(login)
    metrika()
    return {**chain, "counter": counter, "login": login, "root": root, "metrika": metrika}


def new_run(rw, ws, with_metrika=True) -> int:
    return one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, metrika_counter_id, kind)
                      VALUES (%s, %s, %s, 'scheduled') RETURNING id""",
               ws["ws"], ws["account"], ws["counter"] if with_metrika else None)


def work(rw, ws, run_id, direct=None, metrika_source="default"):
    return run_sync(rw, run_id, direct=direct or Spy(ws["root"].path),
                    metrika=ws["metrika"].source() if metrika_source == "default" else metrika_source,
                    release_id=ws["release"], period_to=TO, now=NOW)


def run_status(rw, run_id):
    return rw.execute("SELECT status, error_code, error_reason FROM sync_runs WHERE id = %s", (run_id,)).fetchone()


def snapshots(rw, run_id):
    return one(rw, "SELECT count(*) FROM snapshots WHERE sync_run_id = %s", run_id)


def test_sync_writes_snapshot_with_frozen_definition(rw, ws):
    run_id = new_run(rw, ws)
    out = work(rw, ws, run_id)
    assert isinstance(out, Done) and run_status(rw, run_id) == ("succeeded", None, None)
    sources, definition, status = rw.execute(
        "SELECT sources, conversion_definition, status FROM snapshots WHERE id = %s", (out.snapshot_id,)).fetchone()
    assert (sorted(sources), status) == (["yandex_direct", "yandex_metrika"], "complete")
    assert definition == {"provider": "yandex_metrika", "counter_id": 555, "goal_ids": [111, 222],
                          "attribution": "cross_device_last_significant"}


def test_retry_of_same_sync_run_is_one_snapshot_and_no_new_requests(rw, ws):
    run_id = new_run(rw, ws)
    first = work(rw, ws, run_id)
    spy = Spy(ws["root"].path)
    assert work(rw, ws, run_id, direct=spy) == first
    assert spy.calls == 0 and snapshots(rw, run_id) == 1


@pytest.mark.parametrize("change, reason, detail", [
    ("UPDATE workspaces SET status = 'deactivated', deactivated_at = now() WHERE id = %(ws)s",
     "workspace_inactive", "deactivated"),
    ("UPDATE subscriptions SET status = 'expired' WHERE workspace_id = %(ws)s", "subscription_inactive", "expired"),
    ("UPDATE direct_connections SET status = 'token_expired' WHERE workspace_id = %(ws)s",
     "direct_unavailable", "token_expired"),
    ("UPDATE direct_accounts SET status = 'unavailable', unavailable_reason = 'account_not_found' WHERE id = %(account)s",
     "direct_unavailable", "account_not_found"),
])
def test_state_changed_after_enqueue_means_no_side_effects(rw, ws, change, reason, detail):
    """enqueue → состояние изменилось → worker: ни запросов к API, ни снимка. Это Skipped, не Failed."""
    run_id = new_run(rw, ws)                       # задача поставлена, пока всё было в порядке
    rw.execute(change, {"ws": ws["ws"], "account": ws["account"]})
    spy = Spy(ws["root"].path)
    assert work(rw, ws, run_id, direct=spy) == Skipped(reason, detail)
    assert spy.calls == 0 and snapshots(rw, run_id) == 0
    assert run_status(rw, run_id) == ("skipped", reason, detail)


def test_deletion_started_during_fetch_blocks_the_write(rw, ws, db):
    """Отчёт уже скачан, но пока он шёл, workspace перевели в удаление: под блокировкой guard видит это —
    снимок не пишется."""
    def start_deletion():
        with db("app_rw") as other, other.transaction():  # запрос API пользователя: вход в свой workspace
            set_local_workspace(other, ws["ws"])
            workspace_exclusive(other, ws["ws"])
            other.execute("UPDATE workspaces SET status = 'deletion_pending', deactivated_at = now() WHERE id = %s",
                          (ws["ws"],))
    run_id = new_run(rw, ws)
    spy = Spy(ws["root"].path, during_fetch=start_deletion)
    assert work(rw, ws, run_id, direct=spy) == Skipped("workspace_inactive", "deletion_pending")
    assert spy.calls > 0 and snapshots(rw, run_id) == 0


def try_lock(conn, take, workspace_id) -> bool:
    """Взять блокировку с таймаутом 200 мс в отдельной транзакции: True — взята, False — пришлось бы ждать."""
    try:
        with conn.transaction():
            conn.execute("SET LOCAL lock_timeout = '200ms'")
            take(conn, workspace_id)
        return True
    except psycopg.errors.LockNotAvailable:
        return False


def test_sync_holds_shared_lock_so_deletion_waits(ws, db):
    with db("app_rw") as sync, db("app_rw") as deleter:
        with sync.transaction():
            workspace_shared(sync, ws["ws"])
            assert not try_lock(deleter, workspace_exclusive, ws["ws"])
        assert try_lock(deleter, workspace_exclusive, ws["ws"])  # запись закончилась — удаление проходит


def test_two_syncs_proceed_concurrently(ws, db):
    with db("app_rw") as a, db("app_rw") as b, a.transaction():
        workspace_shared(a, ws["ws"])
        assert try_lock(b, workspace_shared, ws["ws"])


def test_deletion_holds_exclusive_lock_so_sync_waits(ws, db):
    with db("app_rw") as deleter, db("app_rw") as sync:
        with deleter.transaction():
            workspace_exclusive(deleter, ws["ws"])
            assert not try_lock(sync, workspace_shared, ws["ws"])
        assert try_lock(sync, workspace_shared, ws["ws"])


def test_worker_waits_for_deletion_lock_before_writing(rw, ws, db):
    """Удаление держит исключительную блокировку — воркер не пишет снимок, пока она не снята."""
    run_id = new_run(rw, ws)
    with db("app_rw") as deleter:
        with deleter.transaction():
            workspace_exclusive(deleter, ws["ws"])
            rw.execute("SET lock_timeout = '200ms'")
            try:
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    work(rw, ws, run_id)
            finally:
                rw.execute("RESET lock_timeout")
            assert snapshots(rw, run_id) == 0
    assert isinstance(work(rw, ws, run_id), Done)  # блокировка снята — тот же sync_run дописывается


def test_report_not_ready_is_requeued_with_server_interval(rw, ws):
    run_id = new_run(rw, ws)
    spy = Spy(ws["root"].path, raise_first=RetryLater(45))
    assert work(rw, ws, run_id, direct=spy) == RetryAt(45, "report_not_ready")
    assert run_status(rw, run_id)[0] == "waiting_report" and snapshots(rw, run_id) == 0
    assert rw.execute("SELECT attempts, last_retry_at FROM sync_runs WHERE id = %s", (run_id,)).fetchone() == (1, NOW)
    assert isinstance(work(rw, ws, run_id, direct=spy), Done)  # повтор из очереди — тот же sync_run


def test_report_wait_is_bounded(rw, ws):
    """retryIn → retryIn → … не бесконечно: дольше MAX_REPORT_WAIT от первого запроса — Failed(report_timeout)."""
    from app.worker.sync import MAX_REPORT_WAIT
    run_id = new_run(rw, ws)
    spy = Spy(ws["root"].path, raise_first=RetryLater(600))
    assert isinstance(work(rw, ws, run_id, direct=spy), RetryAt)                  # первый запрос — в NOW
    spy.raise_first = RetryLater(600)
    late = run_sync(rw, run_id, direct=spy, metrika=None, release_id=ws["release"], period_to=TO,
                    now=NOW + MAX_REPORT_WAIT)
    assert late == Failed("report_timeout", "report_not_ready")
    assert run_status(rw, run_id) == ("failed", "report_timeout", "report_not_ready")


def test_direct_unavailable_fails_the_run_and_marks_the_account(rw, ws, tmp_path):
    """Ответ API — Failed для этого запуска и отметка на аккаунте: следующий запуск guard пропустит без запросов."""
    (tmp_path / "gone" / ws["login"]).mkdir(parents=True)
    (tmp_path / "gone" / ws["login"] / "unavailable").write_text("access_denied", encoding="utf-8")
    run_id = new_run(rw, ws)
    assert work(rw, ws, run_id, direct=Spy(tmp_path / "gone")) == Failed("access_denied")
    assert run_status(rw, run_id) == ("failed", "access_denied", None) and snapshots(rw, run_id) == 0
    assert rw.execute("SELECT status, unavailable_reason FROM direct_accounts WHERE id = %s",
                      (ws["account"],)).fetchone() == ("unavailable", "access_denied")
    assert work(rw, ws, run_id) == Skipped("already_finished")  # повтор завершённого — без запросов
    spy = Spy(ws["root"].path)
    assert work(rw, ws, new_run(rw, ws), direct=spy) == Skipped("direct_unavailable", "access_denied")
    assert spy.calls == 0


def test_format_error_fails_but_does_not_mark_the_account(rw, ws):
    """Битый отчёт — ошибка этого запуска, не недоступность аккаунта."""
    from test_direct_sync import campaign_tsv
    ws["root"]("broken", campaign=campaign_tsv(eval_cost="-1.00"))
    rw.execute("UPDATE direct_accounts SET client_login = 'broken' WHERE id = %s", (ws["account"],))
    assert work(rw, ws, new_run(rw, ws)) == Failed("invalid_report_format", "negative_value")
    assert one(rw, "SELECT status FROM direct_accounts WHERE id = %s", ws["account"]) == "active"


def test_metrika_unavailable_keeps_cpa(rw, ws, tmp_path):
    """Метрика отказала — снимок complete, отказ записан в нём, CPA по отчёту Директа считается."""
    from app.sources.metrika import MetrikaFixture
    run_id = new_run(rw, ws)
    out = work(rw, ws, run_id, metrika_source=MetrikaFixture(tmp_path / "no-counters"))
    assert isinstance(out, Done)
    assert one(rw, "SELECT source_failures FROM snapshots WHERE id = %s", out.snapshot_id) == \
        {"yandex_metrika": "counter_not_found"}
    findings = [f for r in CAMPAIGN_RULES for f in run(r, load_view(rw, out.snapshot_id), AuditSettings())]
    assert len(findings) == 1 and isinstance(findings[0], Finding)


def test_without_selected_counter_there_are_no_conversions(rw, ws):
    ws["root"]("plain", campaign="\t".join(("Date", "CampaignId", "Impressions", "Clicks", "Cost")) + "\n",
               query="\t".join(("Date", "CampaignId", "Query", "Impressions", "Clicks", "Cost")) + "\n")
    rw.execute("UPDATE direct_accounts SET client_login = 'plain' WHERE id = %s", (ws["account"],))
    out = work(rw, ws, new_run(rw, ws, with_metrika=False))
    assert isinstance(out, Done)
    assert one(rw, "SELECT conversion_definition FROM snapshots WHERE id = %s", out.snapshot_id) is None
    assert "direct_conversions" not in load_view(rw, out.snapshot_id).sources


def test_missing_sync_run_is_skipped(rw, ws):
    assert work(rw, ws, 10 ** 12) == Skipped("sync_run_not_found")


# --- Регрессии из ревью: запуск не зависает, здоровье не выдумывается ------------------------------

def test_invalid_conversion_settings_fail_the_run_instead_of_hanging(rw, ws):
    # БД допускает пустой список целей у невыбранного счётчика, а определение конверсии из него не построить
    rw.execute("UPDATE metrika_counters SET is_selected = false, goal_ids = '{}' WHERE id = %s", (ws["counter"],))
    run_id = new_run(rw, ws)
    assert work(rw, ws, run_id) == Failed("invalid_conversion_definition")
    assert run_status(rw, run_id)[:2] == ("failed", "invalid_conversion_definition")


def test_unexpected_error_marks_run_failed_and_propagates(rw, ws):
    class Broken(Spy):
        def fetch_report(self, *args):
            raise ValueError("bug")
    run_id = new_run(rw, ws)
    with pytest.raises(ValueError):
        work(rw, ws, run_id, direct=Broken(ws["root"].path))
    assert run_status(rw, run_id)[:2] == ("failed", "internal_error")
    assert work(rw, ws, run_id) == Skipped("already_finished")  # повтор из очереди не зацикливается


def test_metrika_health_untouched_when_metrika_not_queried(rw, ws):
    rw.execute("UPDATE metrika_connections SET status = 'permission_missing' WHERE workspace_id = %s", (ws["ws"],))
    assert isinstance(work(rw, ws, new_run(rw, ws), metrika_source=None), Done)
    assert one(rw, "SELECT status FROM metrika_connections WHERE workspace_id = %s", ws["ws"]) == "permission_missing"


def test_query_sighting_is_dated_by_last_occurrence_not_by_sync(rw, ws):
    out = work(rw, ws, new_run(rw, ws))
    seen = one(rw, """SELECT max(g.seen_on) FROM search_query_sightings g JOIN search_query_texts t ON t.id = g.query_id
                      WHERE t.workspace_id = %s""", ws["ws"])
    assert isinstance(out, Done) and seen == TO  # день из отчёта, а не момент синхронизации


def test_worker_requires_autocommit(ws, db):
    with db("app_rw") as conn:
        conn.autocommit = False
        with pytest.raises(AssertionError):
            work(conn, ws, 1)


def test_naive_now_is_rejected(rw, ws):
    with pytest.raises(ValueError):
        load_state(rw, ws["ws"], ws["account"], NOW.replace(tzinfo=None))


# --- Отчёт площадок РСЯ: включение переменной окружения ------------------------------------------------

class ReportLog(Spy):
    def __init__(self, path):
        super().__init__(path)
        self.reports = []

    def fetch_report(self, login, spec, *args):
        self.reports.append(spec.key)
        return super().fetch_report(login, spec, *args)


@pytest.mark.parametrize("value, enabled", [(None, False), ("0", False), ("", False), ("true", False), ("1", True),
                                            (" 1 ", True)])
def test_placements_report_only_with_explicit_env(rw, ws, monkeypatch, value, enabled):
    """По умолчанию выключен (поля отчёта — «проверить» на песочнице); DIRECT_PLACEMENTS_REPORT=1 — третий отчёт,
    строки уровня placement в снимке и имена площадок в справочнике."""
    from test_placements_sync import placement_tsv
    from app.sources.direct import PLACEMENT_REPORT
    if value is None:
        monkeypatch.delenv(PLACEMENTS_REPORT_ENV, raising=False)
    else:
        monkeypatch.setenv(PLACEMENTS_REPORT_ENV, value)
    (ws["root"].path / ws["login"] / f"{PLACEMENT_REPORT.key}.tsv").write_text(
        placement_tsv((("enabled-check.ru", "40", "1200.00", ("0", "0")),)), encoding="utf-8")
    direct = ReportLog(ws["root"].path)
    out = work(rw, ws, new_run(rw, ws), direct=direct)
    assert isinstance(out, Done)
    assert ("PLACEMENT_REPORT" in direct.reports) is enabled
    view = load_view(rw, out.snapshot_id)
    assert [d.placement for d in view.placement_days] == (["enabled-check.ru"] if enabled else [])
