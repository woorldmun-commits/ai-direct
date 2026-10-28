"""Durable authentication mail: python -m app.worker.auth_mail_runner [--once]."""
import argparse
import logging
import os
import signal
import threading

import psycopg

from app.auth.email_config import EmailAuthConfig, send
from app.auth.email_password import mail_token, token_hash

log = logging.getLogger(__name__)


def process_one(conn, config, *, sender=None):
    """One leased request; at-least-once delivery can repeat the same link after an uncertain send."""
    assert conn.autocommit
    row = conn.execute('SELECT * FROM claim_email_reset_mail()').fetchone()
    if row is None:
        return False
    job_id, lease, purpose = row
    token = mail_token(config.hmac_key, job_id, purpose)
    with conn.transaction():
        prepared = conn.execute('SELECT * FROM prepare_email_reset_mail(%s,%s,%s)',
                                (job_id, lease, token_hash(token))).fetchone()
    if prepared is None:
        return True
    address, should_send = prepared
    if should_send:
        try:
            path = '/verify-email' if purpose == 'verify' else '/reset-password'
            url = config.origin + path + '#token=' + token
            if sender:
                sender(address, purpose, url)
            else:
                send(config, address, purpose, url)
        except Exception:
            conn.execute('SELECT finish_email_reset_mail(%s,%s,false)', (job_id, lease))
            log.warning('auth mail unavailable job=%s', job_id)
            return True
    conn.execute('SELECT finish_email_reset_mail(%s,%s,true)', (job_id, lease))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    config = EmailAuthConfig.from_env(os.environ)
    dsn = os.environ.get('WORKER_QUEUE_DATABASE_URL')
    if config is None or not dsn:
        raise SystemExit('Configure email and WORKER_QUEUE_DATABASE_URL for app_system')
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            with psycopg.connect(dsn, autocommit=True, connect_timeout=5,
                                 options='-c statement_timeout=5000 -c lock_timeout=1000') as conn:
                role = conn.execute('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
                if role != ('app_system', False, False):
                    raise RuntimeError('auth mail requires app_system without superuser/BYPASSRLS')
                for _ in range(25):
                    if stop.is_set() or not process_one(conn, config):
                        break
        except Exception as exc:
            log.error('auth mail worker failed type=%s', type(exc).__name__)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            break
        stop.wait(2)


if __name__ == '__main__':
    main()
