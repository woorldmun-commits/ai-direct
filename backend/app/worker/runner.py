"""Durable pilot queue. Run separately: python -m app.worker.runner [--once]."""

import argparse
import logging
import os
import signal
import threading
from datetime import datetime, timezone

import psycopg

from app.auth.tokens import ConnectionRef, EnvKeys, fresh_access_token
from app.auth.yandex_oauth import OAuthApp, OAuthError
from app.sources.direct import DirectApi
from app.sources.http import api_client
from app.sources.metrika import MetrikaApi
from app.tenancy import workspace_scope
from app.worker.audit import run_audit
from app.worker.guard import Skip, Task, guard, load_state
from app.worker.sync import Done, run_sync

log = logging.getLogger("app.worker.runner")


def verify_role(conn, expected):
    row = conn.execute("SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
    if row != (expected, False, False):
        raise RuntimeError(f"worker requires dedicated {expected} role without superuser/BYPASSRLS")


def process(queue, token_conn, run_id, *, provider, keys, release_id, http, now):
    # A session lock survives the short DB transactions and is released on process/connection death.
    lock = (f"pilot-run:{run_id}",)
    if not token_conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))", lock).fetchone()[0]:
        return
    try:
        row = queue.execute("""SELECT r.workspace_id,c.id,r.period_to,r.status,r.direct_account_id
            FROM sync_runs r JOIN direct_accounts a ON a.id=r.direct_account_id
            JOIN direct_connections c ON c.id=a.direct_connection_id
            WHERE r.id=%s AND r.runner_managed AND r.available_at<=%s""", (run_id, now)).fetchone()
        if not row or row[3] not in ("queued", "running", "waiting_report", "succeeded"):
            return
        ws, connection, cutoff, status, account = row
        if cutoff is None:
            raise RuntimeError("runner-managed run must have a frozen period_to")
        with workspace_scope(token_conn, ws):
            decision = guard(Task.SYNC, load_state(token_conn, ws, account, now))
            if isinstance(decision, Skip):
                if status != "succeeded":
                    token_conn.execute("""UPDATE sync_runs SET status='skipped',finished_at=%s,error_code=%s,
                        error_reason=%s WHERE id=%s""", (now, decision.reason, decision.detail, run_id))
                return
        if status == "succeeded":
            outcome = Done(0)  # the immutable snapshot already exists; only resume the audit
        else:
            try:
                access = fresh_access_token(token_conn, http, provider, keys,
                                            ConnectionRef("direct", ws, connection), now)
            except OAuthError as exc:
                # No provider message, token or credential is written to logs/DB.
                queue.execute("""UPDATE sync_runs SET available_at=%s + interval '60 seconds'
                    WHERE id=%s""", (now, run_id))
                log.warning("token refresh unavailable run=%s code=%s", run_id, exc.code)
                return
            direct = DirectApi(http, access, f"sync-{run_id}")
            outcome = run_sync(token_conn, run_id, direct=direct, metrika=MetrikaApi(http, access),
                               release_id=release_id, period_to=cutoff, now=now)
        if isinstance(outcome, Done):
            run_audit(token_conn, workspace_id=ws, task_key=f"pilot-sync:{run_id}",
                      data_cutoff=cutoff, release_id=release_id, now=now)
        log.info("run=%s result=%s", run_id, type(outcome).__name__)
    finally:
        token_conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", lock)


def tick(queue, token_conn, *, provider, keys, release_id, http, now):
    rows = queue.execute("""SELECT r.id FROM sync_runs r WHERE r.runner_managed AND r.available_at<=%s
        AND (r.status IN ('queued','running','waiting_report') OR
            (r.status='succeeded' AND NOT EXISTS(SELECT 1 FROM audit_runs a
                WHERE a.workspace_id=r.workspace_id AND a.task_key='pilot-sync:'||r.id::text)))
        ORDER BY r.available_at,r.id LIMIT 25""", (now,)).fetchall()
    for (run_id,) in rows:
        try:
            process(queue, token_conn, run_id, provider=provider, keys=keys, release_id=release_id, http=http, now=now)
        except psycopg.OperationalError:
            raise  # service supervisor restarts a worker with a broken DB connection
        except Exception as exc:
            queue.execute("UPDATE sync_runs SET available_at=%s + interval '60 seconds' WHERE id=%s", (now, run_id))
            log.error("run=%s failed type=%s", run_id, type(exc).__name__)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    provider = OAuthApp.from_env("YANDEX_API", ("direct:api", "metrika:read"))
    keys = EnvKeys()
    # Source identity is supplied by the build, never fabricated by the worker.
    revision = os.environ["RELEASE_COMMIT_SHA"]
    build = os.environ["RELEASE_BUILD_ID"]
    with psycopg.connect(os.environ["WORKER_QUEUE_DATABASE_URL"], autocommit=True) as queue, \
            psycopg.connect(os.environ["WORKER_DATABASE_URL"], autocommit=True) as token_conn, \
            api_client("yandex_direct") as http:
        verify_role(queue, "app_system")
        verify_role(token_conn, "app_token")
        release_id = queue.execute("""INSERT INTO releases(commit_sha,build_id) VALUES(%s,%s)
            ON CONFLICT(commit_sha,build_id) DO NOTHING RETURNING id""", (revision, build)).fetchone()
        release_id = release_id[0] if release_id else queue.execute(
            "SELECT id FROM releases WHERE commit_sha=%s AND build_id=%s", (revision, build)).fetchone()[0]
        while not stop.is_set():
            tick(queue, token_conn, provider=provider, keys=keys, release_id=release_id, http=http,
                 now=datetime.now(timezone.utc))
            if args.once:
                break
            stop.wait(10)


if __name__ == "__main__":
    main()
