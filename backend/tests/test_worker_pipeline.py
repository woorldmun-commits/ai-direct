"""Конвейер воркера: подключение → постановка sync_run по расписанию → синхронизация → аудит → GET /today.

БД общая для всех тестов: шаги конвейера идут по всем workspace, поэтому проверки — только по своему аккаунту.
finished_at пишет БД (now()), поэтому «сегодня уже синхронизирован» — относительно реального времени, а
«наступил следующий слот» — реальное время + сутки."""

from datetime import datetime, timedelta, timezone

import pytest

from app.worker.pipeline import claim_syncs, enqueue_syncs, last_slot, run_due_audits, run_due_syncs
from test_api_support import api, cookie, session  # noqa: F401 — api: фикстура
from test_direct_sync import TO, root  # noqa: F401 — root: фикстура
from test_metrika_sync import metrika  # noqa: F401 — metrika: фикстура
from test_schema import chain, connected, one  # noqa: F401 — chain: фикстура
from test_worker_sync import NOW, Spy, ws  # noqa: F401 — ws: фикстура

MSK = timezone(timedelta(hours=3))


def today() -> datetime:
    return datetime.now(timezone.utc)


def next_day() -> datetime:
    return today() + timedelta(days=1)


@pytest.fixture
def paid(rw, ws):
    """Подписка действует и в реальном времени (fixture ws оплачена до NOW + 10 дней)."""
    rw.execute("UPDATE subscriptions SET current_period_end = now() + interval '30 days' WHERE workspace_id = %s",
               (ws["ws"],))
    return ws


def active_runs(rw, account) -> list[tuple]:
    return rw.execute("""SELECT id, metrika_counter_id, kind FROM sync_runs WHERE direct_account_id = %s
                         AND status IN ('queued', 'running', 'waiting_report') ORDER BY id""", (account,)).fetchall()


def sources(ws):
    return lambda sync_run_id: (Spy(ws["root"].path), ws["metrika"].source())


def test_last_slot_is_daily_0600_msk():
    assert last_slot(datetime(2026, 10, 1, 6, 0, tzinfo=MSK)) == datetime(2026, 10, 1, 6, 0, tzinfo=MSK)
    assert last_slot(datetime(2026, 10, 1, 5, 59, tzinfo=MSK)) == datetime(2026, 9, 30, 6, 0, tzinfo=MSK)
    assert last_slot(datetime(2026, 10, 1, 23, 0, tzinfo=MSK)) == datetime(2026, 10, 1, 6, 0, tzinfo=MSK)


def test_connect_enqueue_sync_audit_today(api, rw, paid):  # noqa: F811
    enqueue_syncs(rw, now=next_day())
    [(run_id, counter, kind)] = active_runs(rw, paid["account"])
    assert (counter, kind) == (paid["counter"], "scheduled")  # выбранный счётчик — в запуск

    run_due_syncs(rw, rw, sources(paid), release_id=paid["release"], period_to=TO, now=NOW)
    status, snap = rw.execute("""SELECT r.status, s.id FROM sync_runs r JOIN snapshots s ON s.sync_run_id = r.id
                                 WHERE r.id = %s""", (run_id,)).fetchone()
    assert status == "succeeded"

    run_due_audits(rw, rw, release_id=paid["release"], now=NOW)
    cutoff = one(rw, "SELECT data_cutoff FROM audit_runs WHERE task_key = %s AND workspace_id = %s",
                 f"sync:{snap}", paid["ws"])
    assert cutoff == TO
    assert one(rw, "SELECT snapshot_id FROM audit_run_snapshots ars JOIN audit_runs a ON a.id = ars.audit_run_id "
                   "WHERE a.task_key = %s", f"sync:{snap}") == snap

    run_due_audits(rw, rw, release_id=paid["release"], now=NOW)  # новых данных нет — второго аудита нет
    assert one(rw, "SELECT count(*) FROM audit_runs WHERE task_key LIKE 'sync:%%' AND workspace_id = %s",
               paid["ws"]) == 1

    r = api.get(f"/api/v1/workspaces/ws_{paid['ws']}/today", headers=cookie(session(rw, paid["user"])))
    assert r.status_code == 200
    body = r.json()
    assert body["last_audit_at"] is not None
    assert body["audit_scope"]["ad_accounts"] == {"checked": 1, "excluded": 0}


def test_enqueue_is_idempotent_and_daily(rw, paid):
    enqueue_syncs(rw, now=next_day())
    enqueue_syncs(rw, now=next_day())  # запуск уже стоит в очереди — дубля нет
    assert len(active_runs(rw, paid["account"])) == 1

    run_due_syncs(rw, rw, sources(paid), release_id=paid["release"], period_to=TO, now=NOW)
    assert active_runs(rw, paid["account"]) == []
    enqueue_syncs(rw, now=today())  # сегодня уже синхронизирован — до следующих 06:00 ничего
    assert active_runs(rw, paid["account"]) == []
    enqueue_syncs(rw, now=next_day())  # наступил следующий слот
    assert len(active_runs(rw, paid["account"])) == 1


def test_new_account_is_synced_immediately(rw, paid):
    """Только что подключённый кабинет не ждёт 06:00: синхронизаций не было — запуск ставится сразу."""
    enqueue_syncs(rw, now=next_day())
    run_due_syncs(rw, rw, sources(paid), release_id=paid["release"], period_to=TO, now=NOW)  # первый — сегодня
    conn = connected(rw, "direct", paid["ws"], f"new{paid['ws']}")
    new = one(rw, "INSERT INTO direct_accounts (direct_connection_id, is_selected) VALUES (%s, true) RETURNING id", conn)
    enqueue_syncs(rw, now=today())
    assert len(active_runs(rw, new)) == 1
    assert active_runs(rw, paid["account"]) == []


@pytest.mark.parametrize("change", [
    "UPDATE subscriptions SET status = 'expired' WHERE workspace_id = %(ws)s",
    "UPDATE direct_connections SET status = 'token_expired' WHERE workspace_id = %(ws)s",
    "UPDATE direct_accounts SET is_selected = false WHERE id = %(account)s",
])
def test_enqueue_respects_guard_and_selection(rw, paid, change):
    rw.execute(change, {"ws": paid["ws"], "account": paid["account"]})
    enqueue_syncs(rw, now=next_day())
    assert active_runs(rw, paid["account"]) == []


def test_audit_waits_for_all_syncs_of_workspace(rw, paid):
    """Аудит — когда в workspace не осталось незавершённых синхронизаций: иначе второй кабинет выпал бы из него."""
    enqueue_syncs(rw, now=next_day())
    run_due_syncs(rw, rw, sources(paid), release_id=paid["release"], period_to=TO, now=NOW)
    rw.execute("""INSERT INTO sync_runs (workspace_id, direct_account_id, kind) VALUES (%s, %s, 'scheduled')""",
               (paid["ws"], paid["account"]))  # досинхронизация ещё в очереди
    run_due_audits(rw, rw, release_id=paid["release"], now=NOW)
    assert one(rw, "SELECT count(*) FROM audit_runs WHERE task_key LIKE 'sync:%%' AND workspace_id = %s",
               paid["ws"]) == 0


def test_claim_skips_locked_and_leased_runs(rw, paid, db):
    """Два воркера не берут один sync_run: строку под чужой блокировкой пропускают, взятую — держит аренда."""
    enqueue_syncs(rw, now=next_day())
    [(run_id, _, _)] = active_runs(rw, paid["account"])
    with db("app_system") as other, other.transaction():
        other.execute("SELECT id FROM sync_runs WHERE id = %s FOR UPDATE", (run_id,))
        assert run_id not in claim_syncs(rw, now=NOW, limit=10_000)
    assert run_id in claim_syncs(rw, now=NOW, limit=10_000)
    assert run_id not in claim_syncs(rw, now=NOW, limit=10_000)  # уже взят: аренда не истекла
    assert run_id in claim_syncs(rw, now=NOW + timedelta(hours=1), limit=10_000)  # воркер упал — аренда истекла
