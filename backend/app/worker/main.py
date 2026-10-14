"""Точка запуска воркера: `python -m app.worker.main`. Расписание — schedule.py, интервалы — WORKER_<ЗАДАЧА>_EVERY.

Каждая задача — своя роль БД (ARCHITECTURE.md §2.3), строки подключения только из окружения:
  WORKER_DATABASE_URL          app_token  — задача одного workspace (синхронизация, аудит, замер) под RLS, токены;
  WORKER_SYSTEM_DATABASE_URL   app_system — выборки по всем workspace: очередь синхронизаций, аудиты и замеры
                                            к запуску, outbox → уведомления;
  WORKER_DELETER_DATABASE_URL  app_deleter — сроки хранения (только функции удаления).
Соединение открывается на запуск задачи: перезапуск БД не оставляет воркер с мёртвыми соединениями.

pipeline (pipeline.py): постановка sync_run (06:00 МСК и сразу для нового кабинета) → синхронизация → аудит.
Токены — YANDEX_API_CLIENT_ID/_CLIENT_SECRET/_REDIRECT_URI и TOKEN_ENCRYPTION_KEY_*; без них воркер не стартует.
Воркер — ОДНА реплика: лимиты API Директа (RateLimiter, ReportQueue в app/sources/direct.py) считаются в памяти
процесса, вторая реплика удвоила бы нагрузку на пользователя Яндекса. Recheck здесь не запускается."""

import asyncio
import logging
import os
import re
import signal
from datetime import datetime, timezone
from typing import Mapping

import psycopg

from app.api.services import API_SCOPES
from app.auth.phone import purge_phone_auth
from app.auth.tokens import ConnectionRef, EnvKeys, fresh_access_token
from app.auth.yandex_oauth import OAuthApp, ReauthorizationRequired
from app.obs.log import setup
from app.sources.direct import DirectApi
from app.sources.http import api_client
from app.sources.metrika import MetrikaApi
from app.tenancy import task_workspace, workspace_scope
from app.worker.measure import DATA_TIMEZONE, due_measurements, run_measurement
from app.worker.notify import run_notifications
from app.worker.pipeline import Sources, run_pipeline
from app.worker.retention import purge_personal_data, purge_search_queries, retention_cutoff
from app.worker.schedule import Job, ScheduleError, interval_from_env, run_jobs

log = logging.getLogger("ai_direct.worker")

DEFAULTS = {"notify": 60, "pipeline": 60, "measure": 3600, "retention": 86400}


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


def yandex_sources(token: psycopg.Connection, oauth: OAuthApp, keys: EnvKeys, now: datetime) -> Sources:
    """sync_run → DirectApi и MetrikaApi с действующими токенами подключений (обновление — fresh_access_token).
    Токен Директа не обновился → исключение: запуск повторит истёкшая аренда, guard пропустит (token_expired).
    Токен Метрики не обновился → снимок без Метрики; статус подключения уже token_expired — видно в «Свежести»."""
    http, direct_http, metrika_http = api_client("yandex_oauth"), api_client("yandex_direct"), api_client("yandex_metrika")

    def build(sync_run_id: int):
        ws = task_workspace(token, "sync_run", sync_run_id)
        with workspace_scope(token, ws):
            direct_conn, metrika_conn = token.execute("""
                SELECT a.direct_connection_id, mc.metrika_connection_id FROM sync_runs r
                JOIN direct_accounts a ON a.id = r.direct_account_id
                LEFT JOIN metrika_counters mc ON mc.id = r.metrika_counter_id WHERE r.id = %s""",
                (sync_run_id,)).fetchone()
        direct = DirectApi(direct_http, fresh_access_token(token, http, oauth, keys,
                                                           ConnectionRef("direct", ws, direct_conn), now),
                           run_key=str(sync_run_id))
        if metrika_conn is None:
            return direct, None
        try:
            access = fresh_access_token(token, http, oauth, keys, ConnectionRef("metrika", ws, metrika_conn), now)
        except ReauthorizationRequired:
            return direct, None
        return direct, MetrikaApi(metrika_http, access)
    return build


def pipeline(system_url: str, token_url: str, release: int, oauth: OAuthApp, keys: EnvKeys) -> int:
    now = _now()
    with psycopg.connect(system_url, autocommit=True) as system, psycopg.connect(token_url, autocommit=True) as token:
        return run_pipeline(system, token, yandex_sources(token, oauth, keys, now), release_id=release, now=now)


def _yandex(env: Mapping[str, str]) -> tuple[OAuthApp, EnvKeys]:
    try:
        return OAuthApp.from_env("YANDEX_API", API_SCOPES, env), EnvKeys(env)
    except (RuntimeError, ValueError) as e:  # ValueError: ключ не base64
        raise ScheduleError(str(e)) from None


def retention(deleter_url: str) -> int:
    now = _now()
    with psycopg.connect(deleter_url, autocommit=True) as conn:
        return (purge_search_queries(conn, cutoff=retention_cutoff(now)) + purge_personal_data(conn, now=now)
                + purge_phone_auth(conn, now=now))


def build_jobs(env: Mapping[str, str]) -> list[Job]:
    system, token = _url(env, "WORKER_SYSTEM_DATABASE_URL"), _url(env, "WORKER_DATABASE_URL")
    deleter, release = _url(env, "WORKER_DELETER_DATABASE_URL"), release_id(token, env)
    oauth, keys = _yandex(env)
    every = {name: interval_from_env(name, default, env) for name, default in DEFAULTS.items()}
    return [Job("notify", every["notify"], lambda: notify(system)),
            Job("pipeline", every["pipeline"], lambda: pipeline(system, token, release, oauth, keys)),
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
