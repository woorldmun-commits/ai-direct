"""Свежесть синхронизаций и счётчики sync_run по статусам — для мониторинга (GET /ops/health, api/ops.py).

Счётчики берутся из sync_runs, а не из памяти процесса: переживают перезапуск воркера и видны API. Выборка по всем
workspace — соединение системной роли app_system. Наружу — только числа, статусы и время: без ID workspace,
логинов и названий."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg

WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class SyncHealth:
    status: str                    # ok · stale (синхронизация не отработала дольше stale_after) · no_data
    last_success_at: datetime | None
    hours_since_success: float | None
    stale_after_hours: float
    runs_24h: dict[str, int]       # статус sync_run → число запусков, созданных за 24 часа


def freshness(last_success_at: datetime | None, now: datetime, stale_after: timedelta) -> str:
    if last_success_at is None:
        return "no_data"
    return "stale" if now - last_success_at > stale_after else "ok"


def sync_health(conn: psycopg.Connection, *, now: datetime, stale_after: timedelta) -> SyncHealth:
    last = conn.execute("SELECT max(finished_at) FROM sync_runs WHERE status = 'succeeded'").fetchone()[0]
    # created_at у sync_runs нет: запуск попадает в окно по началу или окончанию
    runs = dict(conn.execute("""SELECT status, count(*) FROM sync_runs
                                WHERE coalesce(finished_at, started_at, last_retry_at) >= %s
                                   OR status = 'queued'
                                GROUP BY status""", (now - WINDOW,)).fetchall())
    hours = None if last is None else round((now - last).total_seconds() / 3600, 2)
    return SyncHealth(freshness(last, now, stale_after), last, hours, stale_after.total_seconds() / 3600, runs)
