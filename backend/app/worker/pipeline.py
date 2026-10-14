"""Конвейер данных по расписанию (ARCHITECTURE.md §2.6): постановка sync_run → синхронизация → аудит workspace.

1. enqueue_syncs — выбранный кабинет (is_selected), у которого нет незавершённого запуска и не было запуска с
   последнего слота 06:00 МСК, получает sync_run (queued). Кабинет без единого запуска — сразу: только что
   подключённый клиент не ждёт утра. Допуск — тот же guard SYNC (подписка, статус workspace и Директа).
   Постановка — под транзакционной advisory-блокировкой: два воркера не поставят дубль.
2. run_due_syncs — захват пачки (FOR UPDATE SKIP LOCKED, как outbox) с арендой: queued; waiting_report, чей
   повтор созрел; running, чья аренда истекла (воркер упал). Каждый запуск — run_sync под app_token.
3. run_due_audits — workspace без незавершённых синхронизаций, у которого есть complete-снимок новее последнего
   аудита: run_audit на period_to этого снимка; task_key = sync:<snapshot_id> — повтор не создаст второй аудит.

Выборки по всем workspace — соединение app_system; сами задачи — соединение app_token (RLS по workspace).
ponytail: retryIn из RetryAt не хранится — waiting_report повторяется не раньше RETRY_DELAY; хранить срок в sync_runs,
когда фиксированной паузы станет мало. Пропущенный guard'ом аудит (нет подписки) перепроверяется каждый запуск."""

import logging
from datetime import date, datetime, time, timedelta
from typing import Callable

import psycopg

from app.sources.direct import DEFAULT_RETRY_IN, DirectSource
from app.sources.metrika import MetrikaSource
from app.worker.audit import run_audit
from app.worker.guard import Allow, Task, guard, load_state
from app.worker.measure import DATA_TIMEZONE
from app.worker.sync import run_sync

log = logging.getLogger("ai_direct.worker")

DAILY_AT = time(6, 0)  # основная синхронизация + аудит, МСК
LEASE = timedelta(minutes=30)  # дольше одного run_sync (отчёты по 60 с, ожидание retryIn — вне процесса)
RETRY_DELAY = timedelta(seconds=DEFAULT_RETRY_IN)
BATCH = 10

Sources = Callable[[int], tuple[DirectSource, MetrikaSource | None]]  # sync_run_id → источники с токенами


def last_slot(now: datetime) -> datetime:
    """Последний наступивший слот 06:00 МСК."""
    local = now.astimezone(DATA_TIMEZONE)
    slot = datetime.combine(local.date(), DAILY_AT, DATA_TIMEZONE)
    return slot if slot <= local else slot - timedelta(days=1)


def data_day(now: datetime) -> date:
    """Последний полный день данных — вчера по МСК."""
    return now.astimezone(DATA_TIMEZONE).date() - timedelta(days=1)


def enqueue_syncs(conn: psycopg.Connection, *, now: datetime) -> int:
    """app_system. Возвращает число поставленных запусков."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('sync_enqueue', 0))")
        due = conn.execute("""
            SELECT c.workspace_id, a.id,
                   (SELECT mc.id FROM metrika_counters mc JOIN metrika_connections m ON m.id = mc.metrika_connection_id
                    WHERE m.workspace_id = c.workspace_id AND mc.is_selected ORDER BY mc.id LIMIT 1)
            FROM direct_accounts a JOIN direct_connections c ON c.id = a.direct_connection_id
            WHERE a.is_selected AND NOT EXISTS (
                SELECT 1 FROM sync_runs r WHERE r.direct_account_id = a.id
                  AND (r.status IN ('queued', 'running', 'waiting_report') OR r.finished_at >= %s))
            ORDER BY a.id""", (last_slot(now),)).fetchall()
        allowed = [r for r in due if isinstance(guard(Task.SYNC, load_state(conn, r[0], r[1], now)), Allow)]
        for workspace_id, account_id, counter_id in allowed:
            conn.execute("""INSERT INTO sync_runs (workspace_id, direct_account_id, metrika_counter_id, kind)
                            VALUES (%s, %s, %s, 'scheduled')""", (workspace_id, account_id, counter_id))
    return len(allowed)


def claim_syncs(conn: psycopg.Connection, *, now: datetime, limit: int = BATCH) -> list[int]:
    """app_system. Захват — короткая транзакция; аренда — started_at (первый захват) или last_retry_at (повтор)."""
    with conn.transaction():
        ids = [r[0] for r in conn.execute("""
            SELECT id FROM sync_runs
            WHERE status = 'queued'
               OR (status = 'waiting_report' AND last_retry_at <= %s)
               OR (status = 'running' AND coalesce(last_retry_at, started_at) < %s)
            ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""", (now - RETRY_DELAY, now - LEASE, limit)).fetchall()]
        if ids:
            conn.execute("""UPDATE sync_runs SET status = 'running', started_at = coalesce(started_at, %s),
                                   last_retry_at = CASE WHEN status = 'queued' THEN NULL ELSE %s END
                            WHERE id = ANY(%s)""", (now, now, ids))
    return ids


def run_due_syncs(system: psycopg.Connection, token: psycopg.Connection, sources: Sources, *, release_id: int,
                  period_to: date, now: datetime) -> int:
    """Пачками до пустой очереди: взятый запуск до конца аренды повторно не захватывается — цикл конечен."""
    done = 0
    while ids := claim_syncs(system, now=now):
        for sync_run_id in ids:  # сбой одного запуска не останавливает остальные; запуск повторит истёкшая аренда
            try:
                direct, metrika = sources(sync_run_id)
                run_sync(token, sync_run_id, direct=direct, metrika=metrika, release_id=release_id,
                         period_to=period_to, now=now)
                done += 1
            except psycopg.OperationalError:
                raise  # соединение потеряно — остальные повторит следующий запуск
            except Exception:
                log.exception("sync failed", extra={"result": sync_run_id})
    return done


def due_audits(conn: psycopg.Connection) -> list[tuple[int, int, date]]:
    """app_system. (workspace, последний complete-снимок, его period_to) — новые данные, синхронизации завершены."""
    return conn.execute("""
        SELECT s.workspace_id, s.id, s.period_to FROM (
            SELECT DISTINCT ON (workspace_id) workspace_id, id, period_to, sealed_at FROM snapshots
            WHERE status = 'complete' ORDER BY workspace_id, id DESC) s
        WHERE NOT EXISTS (SELECT 1 FROM sync_runs r WHERE r.workspace_id = s.workspace_id
                            AND r.status IN ('queued', 'running', 'waiting_report'))
          AND NOT EXISTS (SELECT 1 FROM audit_runs a WHERE a.workspace_id = s.workspace_id
                            AND (a.created_at >= s.sealed_at OR a.task_key = 'sync:' || s.id))
        ORDER BY s.workspace_id""").fetchall()


def run_due_audits(system: psycopg.Connection, token: psycopg.Connection, *, release_id: int, now: datetime) -> int:
    done = 0
    for workspace_id, snapshot_id, period_to in due_audits(system):
        try:
            run_audit(token, workspace_id=workspace_id, task_key=f"sync:{snapshot_id}", data_cutoff=period_to,
                      release_id=release_id, now=now)
            done += 1
        except psycopg.OperationalError:
            raise
        except Exception:
            log.exception("audit failed", extra={"result": workspace_id})
    return done


def run_pipeline(system: psycopg.Connection, token: psycopg.Connection, sources: Sources, *, release_id: int,
                 now: datetime) -> int:
    """Один проход: постановка → синхронизации → аудиты. Возвращает число обработанных синхронизаций и аудитов."""
    enqueue_syncs(system, now=now)
    synced = run_due_syncs(system, token, sources, release_id=release_id, period_to=data_day(now), now=now)
    return synced + run_due_audits(system, token, release_id=release_id, now=now)
