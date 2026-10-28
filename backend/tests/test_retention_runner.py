from contextlib import contextmanager
from datetime import timezone
import threading

import psycopg
import pytest

from app.worker import retention_runner as runner
from app.worker.retention import purge_search_queries
from test_retention import CUTOFF, NOW, chain, exists, query_seen, session, session_exists, user  # noqa: F401


def test_runner_cleans_both_retention_scopes(db, rw, chain):
    query = query_seen(rw, chain, 'runner expired query', 61)
    uid = user(rw, 'runner-expired@example.test')
    token = session(rw, uid, ended_days_ago=31)
    with db('app_deleter') as conn:
        assert runner.run_once(conn, now=NOW, stop=threading.Event())
        assert runner.run_once(conn, now=NOW, stop=threading.Event())
    assert not exists(rw, query)
    assert not session_exists(rw, token)


@pytest.mark.parametrize('role', ['app_rw', 'app_token', 'app_system', 'app_migrator'])
def test_runner_rejects_other_roles(db, role):
    with db(role) as conn, pytest.raises(RuntimeError, match='dedicated app_deleter'):
        runner.run_once(conn, now=NOW, stop=threading.Event())


def test_concurrent_runner_skips_without_waiting_and_unlocks_after_failure(db, monkeypatch):
    with db('app_deleter') as first, db('app_deleter') as second:
        first.execute('SELECT pg_advisory_lock(%s)', (runner.LOCK_ID,))
        assert not runner.run_once(second, now=NOW, stop=threading.Event())
        first.execute('SELECT pg_advisory_unlock(%s)', (runner.LOCK_ID,))
        def fail(*args, **kwargs):
            raise ValueError('synthetic secret')
        monkeypatch.setattr(runner, 'purge_personal_data', fail)
        with pytest.raises(ValueError):
            runner.run_once(second, now=NOW, stop=threading.Event())
        assert first.execute('SELECT pg_try_advisory_lock(%s)', (runner.LOCK_ID,)).fetchone()[0]


def test_query_cleanup_is_bounded_and_stoppable(db, rw, chain):
    ids = [query_seen(rw, chain, f'bounded query {i}', 61) for i in range(3)]
    with db('app_deleter') as conn:
        assert purge_search_queries(conn, cutoff=CUTOFF, batch_size=1, max_batches=1) == 1
        assert sum(exists(rw, qid) for qid in ids) == 2
        assert purge_search_queries(conn, cutoff=CUTOFF, should_stop=lambda: True) == 0
        assert purge_search_queries(conn, cutoff=CUTOFF) == 2


@pytest.mark.parametrize('once,fail,complete', [(False,False,True),(False,False,False),
                         (False,True,False),(True,False,True),(True,False,False),(True,True,False)])
def test_service_due_retry_once_and_sanitized_errors(monkeypatch, caplog, once, fail, complete):
    monkeypatch.setenv('RETENTION_DATABASE_URL', 'synthetic-secret-dsn')
    monkeypatch.setattr('sys.argv', ['retention_runner'] + (['--once'] if once else []))
    event = threading.Event()
    waits = []
    def wait(seconds):
        waits.append(seconds)
        event.set()
    monkeypatch.setattr(event, 'wait', wait)
    monkeypatch.setattr(runner.threading, 'Event', lambda: event)
    signals = {}
    monkeypatch.setattr(runner.signal, 'signal', lambda sig, fn: signals.setdefault(sig, fn))
    @contextmanager
    def connect(dsn, **kwargs):
        assert dsn == 'synthetic-secret-dsn'
        assert kwargs['autocommit'] is True
        if fail:
            raise psycopg.OperationalError('synthetic-secret-dsn password=secret')
        yield object()
    monkeypatch.setattr(runner.psycopg, 'connect', connect)
    def tick(conn, *, now, stop):
        assert now.tzinfo == timezone.utc and stop is event
        return complete
    monkeypatch.setattr(runner, 'run_once', tick)
    if once and fail:
        with pytest.raises(SystemExit) as error:
            runner.main()
        assert error.value.code == 1
    elif once and not complete:
        with pytest.raises(SystemExit, match='Retention incomplete'):
            runner.main()
    else:
        runner.main()
    assert waits == ([] if once else [runner.INTERVAL_SECONDS if complete else runner.RETRY_SECONDS])
    assert 'synthetic-secret' not in caplog.text and 'password=' not in caplog.text
    signals[runner.signal.SIGTERM](None, None)
    assert event.is_set()
