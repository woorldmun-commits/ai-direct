"""Progress/queue monitor, separate from API liveness. JSON contains no client identifiers."""
import argparse
import json
import os
from datetime import datetime, timezone

import psycopg


def record(conn, name='sync', *, phase='idle', success=False, error=None, now=None):
    now = now or datetime.now(timezone.utc)
    conn.execute('''INSERT INTO worker_heartbeats(name,heartbeat_at,last_success_at,phase,last_error_code)
        VALUES(%s,%s,CASE WHEN %s THEN %s END,%s,%s)
        ON CONFLICT(name) DO UPDATE SET heartbeat_at=EXCLUDED.heartbeat_at,
        last_success_at=coalesce(EXCLUDED.last_success_at,worker_heartbeats.last_success_at),
        phase=EXCLUDED.phase,last_error_code=CASE WHEN %s THEN NULL ELSE
          coalesce(EXCLUDED.last_error_code,worker_heartbeats.last_error_code) END''',
        (name, now, success, now, phase, error, success))


def status(conn, *, now, expected=('sync',), max_age=180, max_queue_age=900):
    role = conn.execute('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
    if role != ('app_system', False, False):
        raise ValueError('monitor requires app_system without elevated roles')
    if now.utcoffset() is None or max_age <= 0 or max_queue_age <= 0:
        raise ValueError('aware clock and positive limits required')
    workers = {}
    for name in expected:
        row = conn.execute('SELECT heartbeat_at,last_success_at,phase,last_error_code,started_at FROM worker_heartbeats WHERE name=%s',
                           (name,)).fetchone()
        age = max(0, (now-row[0]).total_seconds()) if row else None
        success_age = max(0, (now-(row[1] or row[4])).total_seconds()) if row else None
        workers[name] = {'heartbeat_age_seconds': age, 'healthy': age is not None and age <= max_age
                            and success_age <= max_age and row[3] is None,
                         'last_success_age_seconds': max(0, (now-row[1]).total_seconds()) if row and row[1] else None,
                         'phase': row[2] if row else None, 'error_code': row[3] if row else None}
    queue = conn.execute('''SELECT count(*),min(r.available_at) FROM sync_runs r
        WHERE r.runner_managed AND r.available_at<=%s AND (r.status IN ('queued','running','waiting_report')
        OR (r.status='succeeded' AND NOT EXISTS(SELECT 1 FROM audit_runs a
            WHERE a.workspace_id=r.workspace_id AND a.task_key='pilot-sync:'||r.id::text)))''', (now,)).fetchone()
    age = max(0, (now-queue[1]).total_seconds()) if queue[1] else 0
    mail = conn.execute('''SELECT count(*) FILTER(WHERE attempts<10),min(available_at) FILTER(WHERE attempts<10),
        count(*) FILTER(WHERE attempts>=10) FROM notifications WHERE channel='email' AND recipient_user_id IS NOT NULL
        AND status IN ('queued','failed') AND available_at<=%s''', (now,)).fetchone() if 'product_mail' in expected else (0,None,0)
    mail_age = max(0, (now-mail[1]).total_seconds()) if mail[1] else 0
    return {'healthy': all(worker['healthy'] for worker in workers.values()) and age <= max_queue_age
                and mail_age <= max_queue_age and mail[2] == 0,
            'workers': workers, 'sync_queue': {'due': queue[0], 'oldest_due_age_seconds': age},
            'product_mail_queue': {'due': mail[0], 'oldest_due_age_seconds': mail_age, 'exhausted': mail[2]},
            'limits': {'heartbeat_seconds': max_age, 'queue_seconds': max_queue_age}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-age', type=int, default=180)
    parser.add_argument('--max-queue-age', type=int, default=900)
    parser.add_argument('--worker', action='append', choices=['sync','product_mail'])
    args = parser.parse_args()
    try:
        with psycopg.connect(os.environ['WORKER_QUEUE_DATABASE_URL'], autocommit=True, connect_timeout=5,
                             options='-c statement_timeout=5000 -c lock_timeout=1000') as conn:
            result = status(conn, now=datetime.now(timezone.utc), expected=tuple(args.worker or ['sync']),
                            max_age=args.max_age, max_queue_age=args.max_queue_age)
    except Exception:
        result = {'healthy': False, 'error_code': 'monitor_unavailable'}
    print(json.dumps(result))
    return 0 if result['healthy'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
