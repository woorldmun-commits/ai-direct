"""Воркер замера выполненной рекомендации. Работает только со снимками — к API не обращается.

Состояния: Pending (окно не закрыто или данные за окно ещё не окончательные) · Measured (результат записан:
effect / no_effect / insufficient) · Skipped (guard: подписка неактивна — событие measurement_skipped, в
«Сэкономлено» не входит; или замер уже завершён). Окна и методика взяты из measurements (зафиксированы при 'done'),
определение конверсии, ориентир CPA и список площадок — из выполненного вывода и его снимка; текущие настройки
клиента не читаются.

В сумму «Сэкономлено ≈» результат входит отдельным решением — counted_saved: ручное выполнение (execution_mode =
manual, в v1.0 это каждое 'done') только при verification_status = confirmed (сверка — API_CONTRACT §6.1)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from app.audit.measurement import METHODS, MeasureInput, counts_in_saved_total, family, measure
from app.audit.values import to_value
from app.rules.domain import DIRECT_PLACEMENTS, SnapshotView, Window
from app.sync.store import load_view
from app.tenancy import task_workspace, workspace_scope
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
    action: dict
    evidence: dict
    workspace_id: int
    account_id: int
    campaign_id: int


def _load(conn: psycopg.Connection, measurement_id: int) -> _M | None:
    # Определение конверсии — из снимка, на котором построен выполненный вывод, а не копия в замере: вся цепочка
    # append-only, расходиться нечему.
    row = conn.execute("""SELECT m.id, m.recommendation_id, m.issue_id, m.finding_id, m.done_event_id, m.policy,
                                 m.before_from, m.before_to, m.after_from, m.after_to, s.conversion_definition,
                                 f.action, f.evidence, i.workspace_id, i.direct_account_id, i.object_id
                          FROM measurements m
                          JOIN issues i ON i.id = m.issue_id
                          JOIN findings f ON f.id = m.finding_id
                          JOIN audit_run_snapshots a ON a.audit_run_id = f.audit_run_id
                                                    AND a.direct_account_id = i.direct_account_id
                          JOIN snapshots s ON s.id = a.snapshot_id
                          WHERE m.id = %s""", (measurement_id,)).fetchone()
    if row is None:
        return None
    mid, rec, issue, finding, done, policy, bf, bt, af, at, definition, action, evidence, ws, account, campaign = row
    return _M(mid, rec, issue, finding, done, policy, Window(bf, bt), Window(af, at), definition, action, evidence, ws,
              account, campaign)


def _finished(conn: psycopg.Connection, m: _M) -> Measured | Skipped | None:
    row = conn.execute("SELECT id, verdict FROM recommendation_results WHERE measurement_id = %s", (m.id,)).fetchone()
    if row:
        return Measured(*row)
    skipped = conn.execute("""SELECT 1 FROM recommendation_events WHERE recommendation_id = %s
                              AND type = 'measurement_skipped' AND id > %s""", (m.recommendation_id, m.done_event_id))
    return Skipped("already_skipped") if skipped.fetchone() else None


def _claim(conn: psycopg.Connection, m: _M) -> Measured | Skipped | None:
    """В транзакции записи: блокировка замера и повторная проверка — параллельный воркер, прошедший _finished
    одновременно с нами, уже мог записать итог; тогда возвращаем его, а не падаем на UNIQUE и не пишем дубль."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('measure:' || %s::text, 0))", (m.id,))
    return _finished(conn, m)


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
        if done := _claim(conn, m):
            return done
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


def _skip(conn: psycopg.Connection, m: _M, d: Skip) -> Measured | Skipped:
    with conn.transaction():  # событие и outbox — вместе
        if done := _claim(conn, m):
            return done
        conn.execute("INSERT INTO recommendation_events (recommendation_id, type, payload) "
                     "VALUES (%s, 'measurement_skipped', %s)",
                     (m.recommendation_id, Jsonb({"reason": d.reason, "detail": d.detail})))
        emit(conn, m.workspace_id, "measurement_skipped", "recommendation", m.recommendation_id,
             {"measurement_id": m.id, "reason": d.reason})
    return Skipped(d.reason, d.detail)


def run_measurement(conn: psycopg.Connection, measurement_id: int, *, release_id: int,
                    now: datetime) -> Measured | Pending | Skipped:
    assert conn.autocommit, "воркер требует соединение с autocommit=True"
    workspace_id = task_workspace(conn, "measurement", measurement_id)
    if workspace_id is None:
        return Skipped("measurement_not_found")
    with workspace_scope(conn, workspace_id):  # RLS: задача видит только свой workspace
        return _run_measurement(conn, measurement_id, release_id=release_id, now=now)


def _run_measurement(conn: psycopg.Connection, measurement_id: int, *, release_id: int,
                     now: datetime) -> Measured | Pending | Skipped:
    m = _load(conn, measurement_id)
    if m is None:
        return Skipped("measurement_not_found")
    if done := _finished(conn, m):
        return done
    if m.policy not in METHODS:
        return Skipped("no_method_for_policy", m.policy)  # методики для этого семейства ещё нет
    if isinstance(d := guard(Task.MEASURE, load_state(conn, m.workspace_id, None, now)), Skip):
        return _skip(conn, m, d)
    today = now.astimezone(DATA_TIMEZONE).date()
    if today <= m.after.date_to:
        return Pending("window_open")
    snap = _snapshot(conn, m)
    if snap is None:
        if today <= m.after.date_to + timedelta(days=METHODS[m.policy]["final_data_wait_days"]):
            return Pending("data_not_final")
        return _write(conn, m, release_id=release_id, now=now, snapshot=None, verdict="insufficient",
                      before={}, after={}, saved=None, effect={"reason": "no_data_for_window"})
    if snap[2] != m.definition:  # сравнивать можно только одно и то же определение конверсии
        return _write(conn, m, release_id=release_id, now=now, snapshot=snap, verdict="insufficient",
                      before={}, after={}, saved=None, effect={"reason": "conversion_definition_changed"})
    r = measure(m.policy, _input(m, load_view(conn, snap[0])), m.before, m.after)

    def values(facts):
        return {k: to_value(f, snap[0], snap[1], m.policy).model_dump(mode="json") for k, f in facts.items()}
    saved = to_value(r.saved, snap[0], snap[1], m.policy).model_dump(mode="json") if r.saved else None
    return _write(conn, m, release_id=release_id, now=now, snapshot=snap, verdict=r.verdict,
                  before=values(r.before), after=values(r.after), saved=saved, effect=dict(r.effect))


# Ориентир CPA вывода zero_conv_campaign — ровно один из этих ключей evidence (rules/zero_conv_campaign.py: _reference);
# нет ни одного — порог был абсолютным, ориентира нет.
REFERENCE_KEYS = ("target_cpa", "baseline_cpa", "account_baseline_cpa")


def _input(m: _M, view: SnapshotView) -> MeasureInput:
    """Вход методики: дни кампании выполненного вывода из снимка замера + то, что зафиксировано в самом выводе."""
    kind = family(m.policy)
    data = MeasureInput(tuple(d for d in view.campaign_days if d.campaign_id == m.campaign_id))
    if kind == "zero_conv_placements":
        ids = frozenset(int(i) for i in m.action.get("placement_ids") or ())
        return MeasureInput(data.campaign_days,
                            tuple(p for p in view.placement_days if p.campaign_id == m.campaign_id),
                            DIRECT_PLACEMENTS in view.sources, ids)
    if kind == "zero_conv_campaign":
        ref = next((m.evidence[k]["amount"] for k in REFERENCE_KEYS if (m.evidence.get(k) or {}).get("amount")), None)
        return MeasureInput(data.campaign_days, reference_cpa=None if ref is None else Decimal(ref))
    return data


# --- «Сэкономлено ≈»: только подтверждённое выполнение --------------------------------------------

# Сверку ручного выполнения пишет другой воркер (API_CONTRACT §6.1) событиями рекомендации после 'done'.
# ОЖИДАЕМЫЙ ИНТЕРФЕЙС (в schema.sql этих типов событий пока нет — CHECK recommendation_events.type их не пускает):
#   recommendation_events.type ∈ {'verification_confirmed', 'verification_not_confirmed'}, системное (без actor),
#   id > id события 'done' этого выполнения; последнее из них — текущий статус. Нет ни одного — 'pending'.
VERIFICATION_EVENTS = {"verification_confirmed": "confirmed", "verification_not_confirmed": "not_confirmed"}
EXECUTION_MODE_OF_DONE = "manual"  # v1.0: 'done' = manual_claimed («Выполнено вручную»); API-исполнение — v1.1


def verification_status(conn: psycopg.Connection, recommendation_id: int, done_event_id: int) -> str:
    row = conn.execute("""SELECT type FROM recommendation_events WHERE recommendation_id = %s AND id > %s
                          AND type = ANY(%s) ORDER BY id DESC LIMIT 1""",
                       (recommendation_id, done_event_id, list(VERIFICATION_EVENTS))).fetchone()
    return VERIFICATION_EVENTS[row[0]] if row else "pending"


VerificationReader = Callable[[psycopg.Connection, int, int], str]


def counted_saved(conn: psycopg.Connection, result_id: int, *,
                  verification: VerificationReader = verification_status) -> dict | None:
    """saved результата, если он входит в «Сэкономлено ≈» (Value JSON), иначе None. Читается в момент показа, не
    при замере: сверка может прийти и позже замера, и тогда сумма меняется без пересчёта самого замера."""
    row = conn.execute("""SELECT r.saved, r.recommendation_id, m.done_event_id FROM recommendation_results r
                          JOIN measurements m ON m.id = r.measurement_id WHERE r.id = %s""", (result_id,)).fetchone()
    if row is None:
        return None
    saved, rec, done_event = row
    status = verification(conn, rec, done_event)
    return saved if counts_in_saved_total(saved, EXECUTION_MODE_OF_DONE, status) else None


def due_measurements(conn: psycopg.Connection, today: date) -> list[int]:
    """Замеры, у которых закрылось окно и ещё нет результата или пропуска — для планировщика. Выборка по всем
    workspace — системная задача (роль app_system); сам замер — run_measurement в своём workspace."""
    return [r[0] for r in conn.execute("""
        SELECT m.id FROM measurements m
        WHERE m.after_to < %s
          AND NOT EXISTS (SELECT 1 FROM recommendation_results r WHERE r.measurement_id = m.id)
          AND NOT EXISTS (SELECT 1 FROM recommendation_events e WHERE e.recommendation_id = m.recommendation_id
                          AND e.type = 'measurement_skipped' AND e.id > m.done_event_id)
        ORDER BY m.id""", (today,)).fetchall()]
