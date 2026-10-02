"""Воркер замера: done(конкретный вывод) → окна, зафиксированные БД → снимок с окончательными данными →
результат ровно по выполненной версии действия. «Сэкономлено» воспроизводимо из цепочки без текущих настроек."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import psycopg
import pytest

from app.sources.conversion import ConversionDefinition
from app.sync.parse import StatRow
from app.sync.snapshot import Snapshot
from app.sync.store import write_snapshot
from app.worker.measure import Measured, Pending, due_measurements, execution_date, run_measurement
from app.worker.sync import Skipped
from test_direct_sync import root  # noqa: F401 — фикстура
from test_metrika_sync import metrika  # noqa: F401 — фикстура
from test_schema import EVENT_AT, EXECUTED, chain, one  # noqa: F401 — фикстура
from test_snapshot_store import DATA_UNTIL
from test_worker_audit import audit, fresh, snapshot_like, sync  # noqa: F401 — fresh: autouse-фикстура
from test_worker_sync import ws  # noqa: F401 — фикстура

GOALS = ConversionDefinition(555, (111, 222))
CID = 12345


@pytest.fixture(autouse=True)
def long_subscription(rw, ws):
    """Окна замера считаются от часов БД — подписка должна покрывать их независимо от даты прогона."""
    rw.execute("UPDATE subscriptions SET current_period_end = now() + interval '1 year' WHERE workspace_id = %s",
               (ws["ws"],))
    # целевой CPA задан: вывод предлагает изменение (review) — только на нём возможен 'done' и замер.
    # Без цели вывод — inspect_only («проверить»): там 'checked', замера нет (test_safety_policy.py)
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws["ws"],))


def recommendation(rw, ws):
    return rw.execute("""SELECT r.id, r.finding_id FROM recommendations r JOIN issues i ON i.id = r.issue_id
                         WHERE i.workspace_id = %s AND i.closed_at IS NULL ORDER BY r.id DESC LIMIT 1""",
                      (ws["ws"],)).fetchone()


def done(rw, ws, rec, finding) -> dict:
    """Пользователь нажал «Выполнено» на конкретной версии действия → БД создала замер."""
    ev = one(rw, """INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, execution_date,
                                                       created_at)
                    VALUES (%s, 'done', %s, %s, %s, %s) RETURNING id""", rec, ws["user"], finding, EXECUTED, EVENT_AT)
    row = rw.execute("""SELECT id, finding_id, before_from, before_to, after_from, after_to, policy
                        FROM measurements WHERE done_event_id = %s""", (ev,)).fetchone()
    return dict(zip(("id", "finding", "before_from", "before_to", "after_from", "after_to", "policy"), row))


def test_execution_date_is_moscow_calendar_day():
    """День выполнения — по имени пояса данных: 21:30 UTC 30.09 — это уже 1.10 в Москве."""
    assert execution_date(datetime(2026, 9, 30, 20, 59, tzinfo=timezone.utc)) == date(2026, 9, 30)
    assert execution_date(datetime(2026, 9, 30, 21, 30, tzinfo=timezone.utc)) == date(2026, 10, 1)
    with pytest.raises(ValueError):
        execution_date(datetime(2026, 9, 30, 12))


def measurement_snapshot(rw, ws, m, before=(50000, 10), after=(35000, 10), definition=GOALS, settle=3) -> int:
    """Снимок, в котором оба окна целиком; settle=3 — окно «после» вне окна дозачёта (партиал — последние 3 дня)."""
    to = m["after_to"] + timedelta(settle)
    rows = (StatRow("campaign", CID, to - timedelta(36), 1, 0, Decimal(0), Decimal(0)),
            StatRow("campaign", CID, m["before_to"], 700, 70, Decimal(before[0]), Decimal(before[1])),
            StatRow("campaign", CID, m["after_to"], 700, 70, Decimal(after[0]), Decimal(after[1])),
            # чужая кампания того же аккаунта: в замер выполненной рекомендации попадать не должна
            StatRow("campaign", 999, m["after_to"], 700, 70, Decimal(1000), Decimal(50)))
    snap = Snapshot("x", to - timedelta(36), to, to - timedelta(2), frozenset({"yandex_direct"}), rows, definition)
    run_id = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, started_at)
                        VALUES (%s, %s, 'resync', 'running', now()) RETURNING id""", ws["ws"], ws["account"])
    return write_snapshot(rw, sync_run_id=run_id, workspace_id=ws["ws"], release_id=ws["release"], snapshot=snap,
                          data_until=DATA_UNTIL)


def after_window(m, days=1) -> datetime:
    """Момент, когда окно «после» уже закрыто (по Москве)."""
    return datetime.combine(m["after_to"] + timedelta(days), datetime.min.time(), tzinfo=timezone.utc) + \
        timedelta(hours=12)


def measure(rw, ws, m, when=None):
    return run_measurement(rw, m["id"], release_id=ws["release"], now=when or after_window(m))


def audited(rw, ws):
    sync(rw, ws)
    audit(rw, ws, "d1")
    return recommendation(rw, ws)


# --- Главный сценарий: −15% → −25% → done(−25%) → замер именно −25% ------------------------------

def test_measurement_follows_the_version_that_was_done(rw, ws):
    snap = sync(rw, ws)
    audit(rw, ws, "d1")                                                     # CPA 5 250 → −15%
    rec, finding_a = recommendation(rw, ws)
    snapshot_like(rw, ws, ws["account"], snap, eval_cost=48000, eval_conv=8)
    audit(rw, ws, "d2")                                                     # CPA 6 000 → −25%, seen_again
    finding_b = one(rw, """SELECT finding_id FROM recommendation_events WHERE recommendation_id = %s
                           AND type = 'seen_again' ORDER BY id DESC LIMIT 1""", rec)
    assert one(rw, "SELECT action->>'change_pct' FROM findings WHERE id = %s", finding_b) == "-25"

    m = done(rw, ws, rec, finding_b)
    assert m["finding"] == finding_b and m["policy"] == "high_cpa_measure@2"
    # окна — от дня выполнения, который передало приложение; сам день — ни в одном окне
    assert (m["before_from"], m["before_to"]) == (EXECUTED - timedelta(7), EXECUTED - timedelta(1))
    assert (m["after_from"], m["after_to"]) == (EXECUTED + timedelta(1), EXECUTED + timedelta(7))

    measured_snap = measurement_snapshot(rw, ws, m)
    out = measure(rw, ws, m)
    assert isinstance(out, Measured) and out.verdict == "effect"
    finding, saved, snapshot_id = rw.execute("""SELECT finding_id, saved, snapshot_id FROM recommendation_results
                                                WHERE id = %s""", (out.result_id,)).fetchone()
    assert finding == finding_b and finding != finding_a
    # «Сэкономлено» воспроизводимо: 10 × (5 000 − 3 500), снимок, окно «после», методика и формула — в Value
    assert (Decimal(saved["amount"]), saved["snapshot_id"], saved["rule_version"]) == \
        (Decimal("15000.00"), measured_snap, "high_cpa_measure@2")
    assert (saved["period_from"], saved["period_to"]) == (m["after_from"].isoformat(), m["after_to"].isoformat())
    assert saved["formula"] == "conversions_after * (cpa_before - cpa_after)" and snapshot_id == measured_snap
    assert one(rw, "SELECT close_reason FROM issues i JOIN recommendations r ON r.issue_id = i.id WHERE r.id = %s",
               rec) == "measured"


def test_result_for_version_not_done_is_rejected(rw, ws):
    """done(A) → результат по B невозможен: база не даст замерить не ту версию действия."""
    rec, finding_a = audited(rw, ws)
    snapshot_like(rw, ws, ws["account"], one(rw, "SELECT max(id) FROM snapshots WHERE workspace_id = %s", ws["ws"]))
    audit(rw, ws, "d2")
    finding_b = one(rw, "SELECT finding_id FROM recommendation_events WHERE recommendation_id = %s "
                        "AND type = 'seen_again'", rec)
    m = done(rw, ws, rec, finding_a)
    snap = measurement_snapshot(rw, ws, m)
    with pytest.raises(psycopg.IntegrityError):
        rw.execute("""INSERT INTO recommendation_results (recommendation_id, finding_id, snapshot_id, release_id,
                        before, after, verdict) VALUES (%s, %s, %s, %s, '{}', '{}', 'no_effect')""",
                   (rec, finding_b, snap, ws["release"]))


# --- Ещё рано / невозможно / пропущено -----------------------------------------------------------

def test_pending_until_window_closes_and_data_is_final(rw, ws):
    rec, finding = audited(rw, ws)
    m = done(rw, ws, rec, finding)
    assert measure(rw, ws, m, when=after_window(m, days=0)) == Pending("window_open")
    assert measure(rw, ws, m) == Pending("data_not_final")                   # окно закрыто, снимка ещё нет
    assert m["id"] in due_measurements(rw, m["after_to"] + timedelta(1))   # список общий — для планировщика


def test_window_inside_attribution_lag_waits(rw, ws):
    """Снимок покрывает окно, но его конец ещё в окне дозачёта конверсий — ждём, а не меряем по неокончательным."""
    rec, finding = audited(rw, ws)
    m = done(rw, ws, rec, finding)
    measurement_snapshot(rw, ws, m, settle=1)
    assert measure(rw, ws, m) == Pending("data_not_final")


def test_no_data_long_after_window_is_insufficient(rw, ws):
    rec, finding = audited(rw, ws)
    m = done(rw, ws, rec, finding)
    out = measure(rw, ws, m, when=after_window(m, days=15))
    assert out.verdict == "insufficient"
    assert one(rw, "SELECT effect FROM recommendation_results WHERE id = %s", out.result_id) == \
        {"reason": "no_data_for_window"}


def test_changed_conversion_definition_is_insufficient(rw, ws):
    rec, finding = audited(rw, ws)
    m = done(rw, ws, rec, finding)
    measurement_snapshot(rw, ws, m, definition=ConversionDefinition(555, (222,)))
    out = measure(rw, ws, m)
    assert out.verdict == "insufficient"
    assert one(rw, "SELECT saved FROM recommendation_results WHERE id = %s", out.result_id) is None


def test_expired_subscription_skips_measurement_once(rw, ws):
    rec, finding = audited(rw, ws)
    m = done(rw, ws, rec, finding)
    measurement_snapshot(rw, ws, m)
    rw.execute("UPDATE subscriptions SET status = 'expired' WHERE workspace_id = %s", (ws["ws"],))
    assert measure(rw, ws, m) == Skipped("subscription_inactive", "expired")
    assert measure(rw, ws, m) == Skipped("already_skipped")                 # пропуск — один раз и окончательно
    assert one(rw, "SELECT count(*) FROM recommendation_results WHERE recommendation_id = %s", rec) == 0
    assert m["id"] not in due_measurements(rw, m["after_to"] + timedelta(30))


# --- Идемпотентность и циклы проблемы ------------------------------------------------------------

def test_repeat_is_same_result(rw, ws):
    rec, finding = audited(rw, ws)
    m = done(rw, ws, rec, finding)
    measurement_snapshot(rw, ws, m)
    first = measure(rw, ws, m)
    assert measure(rw, ws, m) == first
    assert one(rw, "SELECT count(*) FROM recommendation_events WHERE recommendation_id = %s AND type = 'measured'",
               rec) == 1


def test_returning_problem_is_measured_independently(rw, ws):
    """Цикл 1 замерен и закрыт; проблема вернулась — новый цикл, новый замер. Старое «Сэкономлено» не наследуется."""
    snap = sync(rw, ws)
    audit(rw, ws, "d1")
    rec1, finding1 = recommendation(rw, ws)
    m1 = done(rw, ws, rec1, finding1)
    measurement_snapshot(rw, ws, m1)
    assert measure(rw, ws, m1).verdict == "effect"                          # цикл 1 замерен, проблема закрыта
    snapshot_like(rw, ws, ws["account"], snap)                              # CPA снова высокий
    audit(rw, ws, "d2")
    rec2, finding2 = recommendation(rw, ws)
    assert rec2 != rec1
    m2 = done(rw, ws, rec2, finding2)
    assert m2["id"] != m1["id"]
    out2 = measure(rw, ws, m2)                                              # свой замер → свой результат
    results = rw.execute("""SELECT r.recommendation_id, r.measurement_id FROM recommendation_results r
                            JOIN issues i ON i.id = r.issue_id WHERE i.workspace_id = %s ORDER BY r.id""",
                         (ws["ws"],)).fetchall()
    assert results == [(rec1, m1["id"]), (rec2, m2["id"])]                  # по результату на цикл, без наследования
    assert isinstance(out2, Measured)


def test_lifecycle_events_go_to_outbox_with_ids_only(rw, ws):
    """Каждое изменение жизненного цикла — событие outbox в той же транзакции; в payload только ID и числа."""
    rec, finding = audited(rw, ws)
    m = done(rw, ws, rec, finding)
    measurement_snapshot(rw, ws, m)
    out = measure(rw, ws, m)
    rows = rw.execute("""SELECT event_type, payload FROM outbox_events WHERE workspace_id = %s
                         AND aggregate_id = %s ORDER BY id""", (ws["ws"], rec)).fetchall()
    assert [r[0] for r in rows] == ["recommendation_created", "recommendation_measured"]
    assert rows[1][1] == {"result_id": out.result_id, "measurement_id": m["id"], "finding_id": finding,
                          "verdict": "effect"}
    allowed = {"issue_id", "finding_id", "rule_version", "result_id", "measurement_id", "verdict", "reason"}
    assert all(set(p) <= allowed for _, p in rows)


def test_worker_that_lost_the_race_returns_the_winner_without_duplicates(rw, ws):
    """Два воркера прошли проверку «уже замерено» до блокировки: опоздавший не падает на UNIQUE и не пишет дубль
    события пропуска — под блокировкой видит итог первого."""
    from app.worker import measure as measure_module
    from app.worker.guard import Skip
    rec, finding = audited(rw, ws)
    m = done(rw, ws, rec, finding)
    measurement_snapshot(rw, ws, m)
    first = measure(rw, ws, m)
    loaded = measure_module._load(rw, m["id"])
    late = measure_module._write(rw, loaded, release_id=ws["release"], now=after_window(m), snapshot=None,
                                 verdict="insufficient", before={}, after={}, saved=None, effect={})
    assert late == first
    assert measure_module._skip(rw, loaded, Skip("subscription_inactive", "expired")) == first
    assert one(rw, "SELECT count(*) FROM recommendation_events WHERE recommendation_id = %s "
                   "AND type IN ('measured', 'measurement_skipped')", rec) == 1
