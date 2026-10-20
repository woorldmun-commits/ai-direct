"""Candidate DB regressions; copy into backend/tests and run on disposable DB only."""
import pytest
import app.worker.sync as sync
from app.sources.direct import RetryLater
from test_worker_sync import NOW, Spy, new_run, run_status, snapshots, work, ws  # noqa: F401
from test_direct_sync import root  # noqa: F401
from test_metrika_sync import metrika  # noqa: F401
from test_schema import chain  # noqa: F401


@pytest.mark.parametrize('terminal', ['succeeded', 'failed', 'skipped'])
def test_late_retry_does_not_resurrect_terminal_run(rw, ws, terminal):
    run_id = new_run(rw, ws)
    class LateRetry(Spy):
        def fetch_report(self, *args):
            if terminal == 'succeeded':
                assert isinstance(work(rw, ws, run_id), sync.Done)
            else:
                rw.execute("UPDATE sync_runs SET status=%s, finished_at=%s, error_code='synthetic_terminal' "
                           "WHERE id=%s", (terminal, NOW, run_id))
            raise RetryLater(45)
    result = work(rw, ws, run_id, direct=LateRetry(ws['root'].path))
    assert isinstance(result, (sync.Skipped, sync.Done))
    assert run_status(rw, run_id)[0] == terminal
    assert snapshots(rw, run_id) == (1 if terminal == 'succeeded' else 0)
    assert rw.execute('SELECT attempts FROM sync_runs WHERE id=%s', (run_id,)).fetchone()[0] == 0


@pytest.mark.parametrize('terminal', ['succeeded', 'failed', 'skipped'])
def test_duplicate_finishing_after_load_cannot_restart_run(rw, ws, monkeypatch, terminal):
    run_id = new_run(rw, ws)
    original = sync._load_run
    intercepted = False
    def stale_load(conn, identity):
        nonlocal intercepted
        loaded = original(conn, identity)
        if not intercepted:
            intercepted = True
            if terminal == 'succeeded':
                assert isinstance(work(rw, ws, run_id), sync.Done)
            else:
                rw.execute("UPDATE sync_runs SET status=%s, finished_at=%s, error_code='synthetic_terminal' "
                           "WHERE id=%s", (terminal, NOW, run_id))
        return loaded
    monkeypatch.setattr(sync, '_load_run', stale_load)
    source = Spy(ws['root'].path)
    result = work(rw, ws, run_id, direct=source)
    assert isinstance(result, (sync.Skipped, sync.Done))
    assert run_status(rw, run_id)[0] == terminal
    assert snapshots(rw, run_id) == (1 if terminal == 'succeeded' else 0)
    assert source.calls == 0
