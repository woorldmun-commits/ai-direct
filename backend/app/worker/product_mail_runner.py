"""Opt-in alerts, not marketing or scheduled digests. Delivery is at-least-once."""
import argparse
import logging
import os
import signal
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.parse import urlsplit

import psycopg

from app.auth.email_config import EmailAuthConfig, send_message
from app.worker.guard import Skip, Task, guard, load_state
from app.worker.progress import record
from app.worker.notify import run_notifications

log = logging.getLogger(__name__)


def finish(conn, identity, lease, *, status, now, error=None, available=None):
    return conn.execute('''UPDATE notifications SET status=%s,sent_at=CASE WHEN %s='sent' THEN %s END,
        locked_until=NULL,lease_token=NULL,last_error_code=%s,available_at=coalesce(%s,available_at)
        WHERE id=%s AND lease_token=%s''', (status, status, now, error, available, identity, lease)).rowcount


def process_one(conn, config, *, now=None, sender=None):
    assert conn.autocommit
    now, lease = now or datetime.now(timezone.utc), uuid4()
    with conn.transaction():
        row = conn.execute('''SELECT id,workspace_id,recipient_user_id,attempts FROM notifications
            WHERE channel='email' AND kind='new_problem' AND recipient_user_id IS NOT NULL
              AND status IN ('queued','failed') AND attempts<10 AND available_at<=%s
              AND (locked_until IS NULL OR locked_until<%s)
            ORDER BY available_at,id LIMIT 1 FOR UPDATE SKIP LOCKED''', (now, now)).fetchone()
        if row is None:
            return False
        identity, workspace, user, attempts = row
        conn.execute('UPDATE notifications SET lease_token=%s,locked_until=%s,attempts=attempts+1 WHERE id=%s',
                     (lease, now+timedelta(minutes=5), identity))
    recipient = conn.execute('SELECT email FROM product_email_recipients(%s) WHERE user_id=%s', (workspace, user)).fetchone()
    if recipient is None or isinstance(guard(Task.NOTIFY, load_state(conn, workspace, None, now)), Skip):
        finish(conn, identity, lease, status='skipped', now=now, error='access_or_preference_changed')
        return True
    text = ('В INROU появились рекомендации, требующие проверки. Основания и доступные действия — в кабинете:\n'
            + config.origin + f'/workspace/recommendations?workspace=ws_{workspace}'
            + '\nИзменения рекламы выполняются вручную. Настройки этих сервисных писем доступны в кабинете.')
    try:
        (sender or send_message)(config, recipient[0], 'INROU: новые рекомендации', text,
                                 f'<inrou-notification-{identity}@{urlsplit(config.origin).hostname}>')
    except Exception:
        finish(conn, identity, lease, status='failed', now=now, error='mail_unavailable',
               available=now+timedelta(seconds=min(3600, 60*2**min(attempts, 6))))
        log.warning('Product mail unavailable')
        return True
    finish(conn, identity, lease, status='sent', now=now)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config = EmailAuthConfig.from_env(os.environ)
    if config is None or os.environ.get('INROU_PRODUCT_EMAIL_ENABLED') != '1':
        raise SystemExit('Configure email and explicitly enable product alerts')
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            with psycopg.connect(os.environ['WORKER_QUEUE_DATABASE_URL'], autocommit=True, connect_timeout=5,
                                 options='-c statement_timeout=5000 -c lock_timeout=1000') as conn:
                role = conn.execute('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
                if role != ('app_system', False, False):
                    raise ValueError('Product mail requires app_system')
                tick(conn, config, stop)
        except Exception as exc:
            log.error('Product mail worker failed type=%s', type(exc).__name__)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            break
        stop.wait(2)


def tick(conn, config, stop):
    record(conn, 'product_mail', phase='mail')
    try:
        run_notifications(conn, now=datetime.now(timezone.utc), limit=25)
        for _ in range(25):
            record(conn, 'product_mail', phase='mail')
            if stop.is_set() or not process_one(conn, config):
                break
            record(conn, 'product_mail', phase='mail', success=True)
        record(conn, 'product_mail', success=True)
    except Exception:
        try:
            record(conn, 'product_mail', error='worker_failed')
        except psycopg.Error:
            pass  # a broken database leaves a stale heartbeat for the external monitor
        raise


if __name__ == '__main__':
    main()
