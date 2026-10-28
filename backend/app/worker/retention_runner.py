"""Dedicated retention service: python -m app.worker.retention_runner [--once]."""

import argparse
from datetime import datetime, timezone
import logging
import os
import signal
import threading

import psycopg

from app.worker.retention import BATCH_SIZE, purge_billing_snapshots, purge_personal_data, purge_search_queries, retention_cutoff

log = logging.getLogger(__name__)
LOCK_ID = 735891322
MAX_BATCHES = 100
INTERVAL_SECONDS = 24 * 60 * 60
RETRY_SECONDS = 60


def run_once(conn, *, now, stop):
    """Return whether cleanup drained; a competing service retries without doing work."""
    row = conn.execute("SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
    if row != ("app_deleter", False, False):
        raise RuntimeError("retention requires dedicated app_deleter without superuser/BYPASSRLS")
    if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
        return False
    try:
        if stop.is_set():
            return False
        personal = purge_personal_data(conn, now=now)
        queries = purge_search_queries(conn, cutoff=retention_cutoff(now), max_batches=MAX_BATCHES,
                                       should_stop=stop.is_set)
        billing = purge_billing_snapshots(conn, now=now, max_batches=MAX_BATCHES, should_stop=stop.is_set)
        log.info("retention completed personal=%s queries=%s billing=%s", personal, queries, billing)
        return max(queries, billing) < BATCH_SIZE * MAX_BATCHES and not stop.is_set()
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    dsn = os.environ.get("RETENTION_DATABASE_URL")
    if not dsn:
        raise SystemExit("Configure RETENTION_DATABASE_URL for app_deleter")
    while not stop.is_set():
        delay = RETRY_SECONDS
        try:
            with psycopg.connect(dsn, autocommit=True, connect_timeout=5,
                                 options="-c statement_timeout=5000 -c lock_timeout=1000") as conn:
                complete = run_once(conn, now=datetime.now(timezone.utc), stop=stop)
                if complete:
                    delay = INTERVAL_SECONDS
        except Exception as exc:
            # Connection errors can contain credentials and server details.
            log.error("retention failed type=%s", type(exc).__name__)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            if not complete:
                raise SystemExit("Retention incomplete; retry before reopening restored data")
            break
        stop.wait(delay)


if __name__ == "__main__":
    main()
