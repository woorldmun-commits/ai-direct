"""Точка запуска воркера: `python -m app.worker.main`. Расписание — schedule.py, интервалы — WORKER_<ЗАДАЧА>_EVERY.

Каждая задача — своя роль БД (ARCHITECTURE.md §2.3), строки подключения только из окружения:
  WORKER_DATABASE_URL          app_token  — задача одного workspace (замер) под RLS;
  WORKER_SYSTEM_DATABASE_URL   app_system — выборки по всем workspace: замеры к запуску, outbox → уведомления;
  WORKER_DELETER_DATABASE_URL  app_deleter — сроки хранения (только функции удаления).
Соединение открывается на запуск задачи: перезапуск БД не оставляет воркер с мёртвыми соединениями.

Синхронизация, аудит и recheck здесь не запускаются: нет постановки sync_run по расписанию и чтения токенов
в воркере — следующий срез (свежесть синхронизаций видна в GET /ops/health)."""

import asyncio
import logging
import os
import re
import signal
from datetime import datetime, timezone
from typing import Mapping

import psycopg

from app.auth.phone import purge_phone_auth
from app.obs.log import setup
from app.worker.measure import DATA_TIMEZONE, due_measurements, run_measurement
from app.worker.notify import run_notifications
from app.worker.retention import purge_personal_data, purge_search_queries, retention_cutoff
from app.worker.schedule import Job, ScheduleError, interval_from_env, run_jobs

log = logging.getLogger("ai_direct.worker")

DEFAULTS = {"notify": 60, "measure": 3600, "retention": 86400}


def _url(env: Mapping[str, str], key: str) -> str:
    if not env.get(key):
        raise ScheduleError(f"{key} не задан")
    return env[key]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def release_id(url: str, env: Mapping[str, str]) -> int:
    """Версия кода, которой воркер пишет результаты (releases): RELEASE_COMMIT_SHA (40 hex) + RELEASE_BUILD_ID."""
    sha, build = env.get("RELEASE_COMMIT_SHA", ""), env.get("RELEASE_BUILD_ID", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not build:
        raise ScheduleError("RELEASE_COMMIT_SHA (40 hex) и RELEASE_BUILD_ID обязательны")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("""INSERT INTO releases (commit_sha, build_id) VALUES (%s, %s)
                        ON CONFLICT (commit_sha, build_id) DO NOTHING""", (sha, build))
        return conn.execute("SELECT id FROM releases WHERE commit_sha = %s AND build_id = %s",
                            (sha, build)).fetchone()[0]


def notify(system_url: str) -> int:
    with psycopg.connect(system_url, autocommit=True) as conn:
        return run_notifications(conn, now=_now())


def measure(system_url: str, token_url: str, release: int) -> int:
    now = _now()
    with psycopg.connect(system_url, autocommit=True) as conn:
        due = due_measurements(conn, now.astimezone(DATA_TIMEZONE).date())
    done = 0
    with psycopg.connect(token_url, autocommit=True) as conn:
        for measurement_id in due:  # сбой одного замера не останавливает остальные
            try:
                run_measurement(conn, measurement_id, release_id=release, now=now)
                done += 1
            except psycopg.OperationalError:
                raise  # соединение потеряно — остальные повторит следующий запуск
            except Exception:
                log.exception("measurement failed", extra={"result": measurement_id})
    return done


def retention(deleter_url: str) -> int:
    now = _now()
    with psycopg.connect(deleter_url, autocommit=True) as conn:
        return (purge_search_queries(conn, cutoff=retention_cutoff(now)) + purge_personal_data(conn, now=now)
                + purge_phone_auth(conn, now=now))


def build_jobs(env: Mapping[str, str]) -> list[Job]:
    system, token = _url(env, "WORKER_SYSTEM_DATABASE_URL"), _url(env, "WORKER_DATABASE_URL")
    deleter, release = _url(env, "WORKER_DELETER_DATABASE_URL"), release_id(token, env)
    every = {name: interval_from_env(name, default, env) for name, default in DEFAULTS.items()}
    return [Job("notify", every["notify"], lambda: notify(system)),
            Job("measure", every["measure"], lambda: measure(system, token, release)),
            Job("retention", every["retention"], lambda: retention(deleter))]


async def _main(env: Mapping[str, str]) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    jobs = build_jobs(env)
    log.info("worker started", extra={"result": len(jobs)})
    await run_jobs(jobs, stop)
    log.info("worker stopped")


def main() -> None:
    setup()
    try:
        asyncio.run(_main(os.environ))
    except ScheduleError as e:  # ошибка конфигурации — понятное сообщение и код выхода, без трассировки
        log.error("worker config error: %s", e)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
