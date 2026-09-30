"""Воркер замера выполненной рекомендации. Работает только со снимками — к API не обращается.

Состояния: Pending (окно не закрыто или данные за окно ещё не окончательные) · Measured (результат записан:
effect / no_effect / insufficient) · Skipped (guard: подписка неактивна — событие measurement_skipped, в
«Сэкономлено» не входит; или замер уже завершён). Окна и методика взяты из measurements (зафиксированы при 'done'),
определение конверсии — из снимка выполненного вывода; текущие настройки клиента не читаются."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from app.audit.measurement import PARAMS, POLICY, measure_cpa
from app.audit.values import to_value
from app.rules.domain import Window
from app.sync.store import load_view
from app.worker.guard import Skip, Task, guard, load_state
from app.worker.locks import workspace_shared
from app.worker.outbox import emit
from app.worker.sync import Skipped

DATA_TIMEZONE = ZoneInfo("Europe/Moscow")


def execution_date(at: datetime) -> date:
    """День выполнения для 'done' — календарная дата в часовом поясе данных (даты отчётов Директа), по имени пояса,
    не по смещению. API передаёт её в recommendation_events.execution_date в той же транзакции, что и сам 'done'."""
    if at.tzinfo is None:
        raise ValueError("at: нужна дата с часовым поясом")
    return at.astimezone(DATA_TIMEZONE).date()


@dataclass(frozen=True)
class Pending:
    reason: str  # window_open · data_not_final


@dataclass(frozen=True)
class Measured:
    result_id: int
    verdict: str


@dataclass(frozen=True)
class _M:
    id: int
    recommendation_id: int
    issue_id: int
    finding_id: int
    done_event_id: int
    policy: str
    before: Window
    after: Window
    definition: dict | None
    workspace_id: int
    account_id: int
    campaign_id: int


def _load(conn: psycopg.Connection, measurement_id: int) -> _M | None:
    # Определение конверсии — из снимка, на котором построен выполненный вывод, а не копия в замере: вся цепочка
    # append-only, расходиться нечему.
    row = conn.execute("""SELECT m.id, m.recommendation_id, m.issue_id, m.finding_id, m.done_event_id, m.policy,
                                 m.before_from, m.before_to, m.after_from, m.after_to, s.conversion_definition,
                                 i.workspace_id, i.direct_account_id, i.object_id
                          FROM measurements m
                          JOIN issues i ON i.id = m.issue_id
                          JOIN findings f ON f.id = m.finding_id
                          JOIN audit_run_snapshots a ON a.audit_run_id = f.audit_run_id
                                                    AND a.direct_account_id = i.direct_account_id
                          JOIN snapshots s ON s.id = a.snapshot_id
                          WHERE m.id = %s""", (measurement_id,)).fetchone()
    if row is None:
        return None
    mid, rec, issue, finding, done, policy, bf, bt, af, at, definition, ws, account, campaign = row
    return _M(mid, rec, issue, finding, done, policy, Window(bf, bt), Window(af, at), definition, ws, account, campaign)


def _finished(conn: psycopg.Connection, m: _M) -> Measured | Skipped | None:
    row = conn.execute("SELECT id, verdict FROM recommendation_results WHERE measurement_id = %s", (m.id,)).fetchone()
    if row:
        return Measured(*row)
    skipped = conn.execute("""SELECT 1 FROM recommendation_events WHERE recommendation_id = %s
                              AND type = 'measurement_skipped' AND id > %s""", (m.recommendation_id, m.done_event_id))
    return Skipped("already_skipped") if skipped.fetchone() else None


def _snapshot(conn: psycopg.Connection, m: _M) -> tuple[int, date, dict | None] | None:
    """Снимок, в котором оба окна целиком и данные за окно «после» уже окончательные (вне окна дозачёта)."""
    return conn.execute("""SELECT s.id, s.partial_from, s.conversion_definition
                           FROM snapshots s JOIN sync_runs r ON r.id = s.sync_run_id
                           WHERE s.workspace_id = %s AND r.direct_account_id = %s AND s.status = 'complete'
                             AND s.period_from <= %s AND s.period_to >= %s AND s.partial_from > %s
                           ORDER BY s.sealed_at DESC, s.id DESC LIMIT 1""",
                        (m.workspace_id, m.account_id, m.before.date_from, m.after.date_to, m.after.date_to)).fetchone()


def _write(conn: psycopg.Connection, m: _M, *, release_id: int, now: datetime, snapshot: tuple | None,
           verdict: str, before: dict, after: dict, saved, effect: dict) -> Measured | Skipped:
    with conn.transaction():
        workspace_shared(conn, m.workspace_id)
        if isinstance(d := guard(Task.MEASURE, load_state(conn, m.workspace_id, None, now)), Skip):
            return _skip(conn, m, d)
        result_id = conn.execute(
            """INSERT INTO recommendation_results (recommendation_id, finding_id, snapshot_id, release_id, before,
                                                   after, saved, verdict, effect)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (m.recommendation_id, m.finding_id, snapshot[0] if snapshot else None, release_id, Jsonb(before),
             Jsonb(after), Jsonb(saved) if saved else None, verdict, Jsonb(effect))).fetchone()[0]
        conn.execute("""INSERT INTO recommendation_events (recommendation_id, type, finding_id, result_id)
                        VALUES (%s, 'measured', %s, %s)""", (m.recommendation_id, m.finding_id, result_id))
        conn.execute("UPDATE issues SET closed_at = %s, close_reason = 'measured' WHERE id = %s AND closed_at IS NULL",
                     (now, m.issue_id))
        emit(conn, m.workspace_id, "recommendation_measured", "recommendation", m.recommendation_id,
             {"result_id": result_id, "measurement_id": m.id, "finding_id": m.finding_id, "verdict": verdict})
    return Measured(result_id, verdict)


def _skip(conn: psycopg.Connection, m: _M, d: Skip) -> Skipped:
    with conn.transaction():  # событие и outbox — вместе
        conn.execute("INSERT INTO recommendation_events (recommendation_id, type, payload) "
                     "VALUES (%s, 'measurement_skipped', %s)",
                     (m.recommendation_id, Jsonb({"reason": d.reason, "detail": d.detail})))
        emit(conn, m.workspace_id, "measurement_skipped", "recommendation", m.recommendation_id,
             {"measurement_id": m.id, "reason": d.reason})
    return Skipped(d.reason, d.detail)


def run_measurement(conn: psycopg.Connection, measurement_id: int, *, release_id: int,
                    now: datetime) -> Measured | Pending | Skipped:
    assert conn.autocommit, "воркер требует соединение с autocommit=True"
    m = _load(conn, measurement_id)
    if m is None:
        return Skipped("measurement_not_found")
    if done := _finished(conn, m):
        return done
    if m.policy != POLICY:
        return Skipped("no_method_for_policy", m.policy)  # методики для этого семейства ещё нет
    if isinstance(d := guard(Task.MEASURE, load_state(conn, m.workspace_id, None, now)), Skip):
        return _skip(conn, m, d)
    today = now.astimezone(DATA_TIMEZONE).date()
    if today <= m.after.date_to:
        return Pending("window_open")
    snap = _snapshot(conn, m)
    if snap is None:
        if today <= m.after.date_to + timedelta(days=PARAMS["final_data_wait_days"]):
            return Pending("data_not_final")
        return _write(conn, m, release_id=release_id, now=now, snapshot=None, verdict="insufficient",
                      before={}, after={}, saved=None, effect={"reason": "no_data_for_window"})
    if snap[2] != m.definition:  # сравнивать можно только одно и то же определение конверсии
        return _write(conn, m, release_id=release_id, now=now, snapshot=snap, verdict="insufficient",
                      before={}, after={}, saved=None, effect={"reason": "conversion_definition_changed"})
    days = [d for d in load_view(conn, snap[0]).campaign_days if d.campaign_id == m.campaign_id]
    r = measure_cpa(days, m.before, m.after)

    def values(facts):
        return {k: to_value(f, snap[0], snap[1], POLICY).model_dump(mode="json") for k, f in facts.items()}
    saved = to_value(r.saved, snap[0], snap[1], POLICY).model_dump(mode="json") if r.saved else None
    return _write(conn, m, release_id=release_id, now=now, snapshot=snap, verdict=r.verdict,
                  before=values(r.before), after=values(r.after), saved=saved, effect=dict(r.effect))


def due_measurements(conn: psycopg.Connection, today: date) -> list[int]:
    """Замеры, у которых закрылось окно и ещё нет результата или пропуска — для планировщика."""
    return [r[0] for r in conn.execute("""
        SELECT m.id FROM measurements m
        WHERE m.after_to < %s
          AND NOT EXISTS (SELECT 1 FROM recommendation_results r WHERE r.measurement_id = m.id)
          AND NOT EXISTS (SELECT 1 FROM recommendation_events e WHERE e.recommendation_id = m.recommendation_id
                          AND e.type = 'measurement_skipped' AND e.id > m.done_event_id)
        ORDER BY m.id""", (today,)).fetchall()]
