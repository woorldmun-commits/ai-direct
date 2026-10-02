"""Воркер синхронизации одного sync_run: guard → запросы к API (без блокировок) → блокировка workspace →
guard ещё раз → запись снимка. Бизнес-логики здесь нет — только порядок шагов и исходы.

Идемпотентность — по sync_run_id: повтор завершённого запуска ничего не делает и возвращает тот же результат.
Исходы: Done · Skipped (состояние не позволяет) · Failed (ошибка API/формата) · RetryAt (retryIn или временная
ошибка API: вернуть в очередь на N секунд, не спать в процессе)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import psycopg

from app.sources.conversion import ConversionDefinition
from app.sources.direct import DirectSource, RetryLater
from app.sources.metrika import MetrikaSource
from app.sync.snapshot import Snapshot, SyncFailure, sync_account, sync_metrika, with_metrika
from app.sync.store import SyncRunStateError, record_failure, write_snapshot
from app.tenancy import task_workspace, workspace_scope
from app.worker.guard import Skip, Task, guard, load_state
from app.worker.health import direct_failure, direct_success, metrika_result
from app.worker.locks import workspace_shared


# ponytail: предел ожидания офлайн-отчёта Директа от первого запроса; уточнить по реальным retryIn.
MAX_REPORT_WAIT = timedelta(hours=3)


@dataclass(frozen=True)
class Done:
    snapshot_id: int


@dataclass(frozen=True)
class Skipped:
    """Состояние не позволяет (решение guard). Не ошибка: API и данные тут ни при чём."""
    reason: str
    detail: str | None = None


@dataclass(frozen=True)
class Failed:
    """Попытка была и не удалась: API, формат отчёта, предел ожидания."""
    error_code: str
    reason: str | None = None


@dataclass(frozen=True)
class RetryAt:
    """Временная причина (отчёт строится, сервер недоступен, баллы): вернуть в очередь через seconds, тот же sync_run."""
    seconds: int
    reason: str


Outcome = Done | Skipped | Failed | RetryAt


@dataclass(frozen=True)
class _Run:
    id: int
    workspace_id: int
    direct_account_id: int
    status: str
    started_at: datetime | None
    login: str
    metrika_counter_id: int | None
    definition: ConversionDefinition | None
    definition_error: str | None = None  # настройки в БД не складываются в определение конверсии


def _load_run(conn: psycopg.Connection, sync_run_id: int) -> _Run | None:
    row = conn.execute("""
        SELECT r.id, r.workspace_id, r.direct_account_id, r.status, r.started_at,
               coalesce(a.client_login, c.yandex_login), r.metrika_counter_id,
               mc.counter_id, mc.goal_ids, coalesce(ws.attribution_model, 'cross_device_last_significant')
        FROM sync_runs r
        JOIN direct_accounts a ON a.id = r.direct_account_id
        JOIN direct_connections c ON c.id = a.direct_connection_id
        LEFT JOIN metrika_counters mc ON mc.id = r.metrika_counter_id
        LEFT JOIN workspace_settings ws ON ws.workspace_id = r.workspace_id
        WHERE r.id = %s""", (sync_run_id,)).fetchone()
    if row is None:
        return None
    *head, counter_id, goal_ids, attribution = row
    if not counter_id:
        return _Run(*head, None)
    # замораживается здесь: снимок получит определение, действовавшее в момент синхронизации
    try:
        return _Run(*head, ConversionDefinition(counter_id, tuple(sorted(set(goal_ids))), attribution))
    except ValueError:  # > 10 целей, пустой список, неизвестная атрибуция — ошибка настроек, а не вечный повтор
        return _Run(*head, None, "invalid_conversion_definition")


def _skip(conn: psycopg.Connection, run_id: int, d: Skip) -> Skipped:
    conn.execute("""UPDATE sync_runs SET status = 'skipped', finished_at = now(), error_code = %s, error_reason = %s
                    WHERE id = %s AND status IN ('queued', 'running', 'waiting_report')""", (d.reason, d.detail, run_id))
    return Skipped(d.reason, d.detail)


def _fail(conn: psycopg.Connection, run: _Run, failure: SyncFailure, now: datetime) -> Failed | Skipped:
    try:
        with conn.transaction():
            record_failure(conn, run.id, failure)
            # доступ/токен → статус аккаунта/подключения (следующие запуски пропустит guard); данные — только sync_run
            direct_failure(conn, run.direct_account_id, failure.error_code, now)
    except SyncRunStateError:
        return Skipped("already_finished")  # параллельный дубль задачи успел завершить запуск
    return Failed(failure.error_code, failure.reason)


def _record_health(conn: psycopg.Connection, run: _Run, snap: Snapshot, now: datetime) -> None:
    direct_success(conn, run.direct_account_id, now)
    queried = "yandex_metrika" in snap.sources or "yandex_metrika" in snap.source_failures
    if run.metrika_counter_id is not None and queried:  # без запроса к Метрике её здоровье не меняем
        metrika_result(conn, run.metrika_counter_id, snap.source_failures.get("yandex_metrika"), now)


def _retry(conn: psycopg.Connection, run: _Run, e: RetryLater, now: datetime) -> RetryAt | Failed | Skipped:
    """retryIn → в очередь; но не бесконечно: дольше MAX_REPORT_WAIT от первого запроса — отказ."""
    if now + timedelta(seconds=e.retry_in) - (run.started_at or now) > MAX_REPORT_WAIT:
        return _fail(conn, run, SyncFailure(run.login, "report_timeout", e.reason), now)
    conn.execute("""UPDATE sync_runs SET status = 'waiting_report', attempts = attempts + 1, last_retry_at = %s
                    WHERE id = %s""", (now, run.id))
    return RetryAt(e.retry_in, e.reason)


def _fetch(run: _Run, direct: DirectSource, metrika: MetrikaSource | None,
           period_to: date) -> Snapshot | SyncFailure:
    snap = sync_account(direct, run.login, run.definition, period_to)
    if isinstance(snap, Snapshot) and run.definition is not None and metrika is not None:
        snap = with_metrika(snap, sync_metrika(metrika, run.definition, snap.period_from, snap.period_to))
    return snap


def run_sync(conn: psycopg.Connection, sync_run_id: int, *, direct: DirectSource, metrika: MetrikaSource | None,
             release_id: int, period_to: date, now: datetime) -> Outcome:
    # без autocommit первый SELECT открыл бы транзакцию, и запрос к API шёл бы внутри неё — вместе с блокировкой
    assert conn.autocommit, "run_sync требует соединение с autocommit=True"
    workspace_id = task_workspace(conn, "sync_run", sync_run_id)
    if workspace_id is None:
        return Skipped("sync_run_not_found")  # удалён вместе с workspace
    with workspace_scope(conn, workspace_id):  # RLS: задача видит только свой workspace
        return _run_sync(conn, sync_run_id, direct=direct, metrika=metrika, release_id=release_id,
                         period_to=period_to, now=now)


def _run_sync(conn: psycopg.Connection, sync_run_id: int, *, direct: DirectSource, metrika: MetrikaSource | None,
              release_id: int, period_to: date, now: datetime) -> Outcome:
    run = _load_run(conn, sync_run_id)
    if run is None:
        return Skipped("sync_run_not_found")  # удалён вместе с workspace
    if run.status == "succeeded":
        row = conn.execute("SELECT id FROM snapshots WHERE sync_run_id = %s", (run.id,)).fetchone()
        return Done(row[0]) if row else Skipped("snapshot_missing")  # снимок удалён по сроку хранения
    if run.status in ("failed", "skipped"):
        return Skipped("already_finished")
    if isinstance(d := guard(Task.SYNC, load_state(conn, run.workspace_id, run.direct_account_id, now)), Skip):
        return _skip(conn, run.id, d)
    if run.definition_error:
        return _fail(conn, run, SyncFailure(run.login, run.definition_error), now)
    try:
        return _execute(conn, run, direct=direct, metrika=metrika, release_id=release_id, period_to=period_to, now=now)
    except psycopg.OperationalError:
        raise  # таймаут блокировки, deadlock, обрыв соединения — временное: запуск остаётся, очередь повторит
    except Exception:
        # непредвиденная ошибка: запуск не должен навсегда остаться running — отмечаем и пробрасываем для лога
        _fail(conn, run, SyncFailure(run.login, "internal_error"), now)
        raise


def _execute(conn: psycopg.Connection, run: _Run, *, direct: DirectSource, metrika: MetrikaSource | None,
             release_id: int, period_to: date, now: datetime) -> Outcome:
    conn.execute("UPDATE sync_runs SET status = 'running', started_at = coalesce(started_at, %s) WHERE id = %s",
                 (now, run.id))
    try:
        snap = _fetch(run, direct, metrika, period_to)  # сеть — без блокировок
    except RetryLater as e:
        return _retry(conn, run, e, now)
    if isinstance(snap, SyncFailure):
        return _fail(conn, run, snap, now)

    with conn.transaction():
        workspace_shared(conn, run.workspace_id)
        # пока шли запросы, workspace могли деактивировать или начать удалять — решаем по состоянию под блокировкой
        if isinstance(d := guard(Task.SYNC, load_state(conn, run.workspace_id, run.direct_account_id, now)), Skip):
            return _skip(conn, run.id, d)
        try:
            snapshot_id = write_snapshot(conn, sync_run_id=run.id, workspace_id=run.workspace_id,
                                         release_id=release_id, snapshot=snap, data_until=now)
        except SyncRunStateError:
            return Skipped("already_finished")
        _record_health(conn, run, snap, now)
        return Done(snapshot_id)
