from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from app.worker.progress import record, status

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def clean_progress(db):
    with db('app_migrator') as owner:
        owner.execute("DELETE FROM worker_heartbeats WHERE name='sync'")


def test_missing_and_stalled_progress_are_detected(rw):
    assert not status(rw, now=NOW)['healthy']
    record(rw, now=NOW, success=True)
    assert status(rw, now=NOW)['healthy']
    stale = status(rw, now=NOW+timedelta(minutes=4))
    assert not stale['healthy'] and stale['workers']['sync']['heartbeat_age_seconds'] == 240


def test_unfinished_phase_does_not_forge_success(rw):
    record(rw, now=NOW, phase='sync')
    result = status(rw, now=NOW)
    assert result['workers']['sync']['last_success_age_seconds'] is None
    assert result['workers']['sync']['phase'] == 'sync'


def test_fresh_heartbeat_does_not_hide_stale_success_or_error(rw):
    record(rw,now=NOW-timedelta(hours=2),success=True)
    record(rw,now=NOW,phase='sync')
    assert not status(rw,now=NOW)['healthy']
    record(rw,now=NOW,error='task_failed')
    record(rw,now=NOW+timedelta(seconds=1),phase='sync')
    assert status(rw,now=NOW+timedelta(seconds=1))['workers']['sync']['error_code']=='task_failed'
    record(rw,now=NOW+timedelta(seconds=2),success=True)
    assert status(rw,now=NOW+timedelta(seconds=2))['healthy']


@pytest.mark.parametrize('role',['app_rw','app_token','app_deleter'])
def test_operational_metadata_is_not_readable_by_customer_roles(db,role):
    with db(role) as conn,pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute('SELECT * FROM worker_heartbeats')
