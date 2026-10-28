from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from app.tenancy import workspace_scope
from app.worker.guard import load_state
from test_email_auth import browser, verified  # noqa: F401
from test_schema import new_workspace, one


def test_email_confirmation_grants_seven_days_without_payment(browser, db, monkeypatch):
    verified(browser)
    workspace = browser.get('/api/v1/me').json()['organizations'][0]['workspaces'][0]['id']
    body = browser.get(f'/api/v1/workspaces/{workspace}/subscription').json()
    assert body['subscription'] is None and body['access']['paid'] is False
    assert body['access']['basis'] == 'trial' and body['access']['analysis_allowed'] is True
    trial = body['trial']
    assert trial['active'] is True
    start, end = (datetime.fromisoformat(trial[key]) for key in ('started_at', 'ends_at'))
    assert end-start == timedelta(days=7)
    uid = browser.get('/api/v1/me').json()['user']['id']
    with db('app_system') as conn:
        uid = int(uid.removeprefix('u_'))
        ws = int(workspace.removeprefix('ws_'))
        conn.execute('SELECT start_registration_trial(%s,%s)', (uid, ws))
        other = new_workspace(conn, 'second', user=uid)
        conn.execute('SELECT start_registration_trial(%s,%s)', (uid, other))
        assert not load_state(conn, other, None, start+timedelta(days=1)).has_analysis_access
        assert load_state(conn, ws, None, end-timedelta(microseconds=1)).has_analysis_access
        assert not load_state(conn, ws, None, end).has_analysis_access
        assert not load_state(conn, ws, None, start-timedelta(microseconds=1)).has_analysis_access
        assert conn.execute('SELECT * FROM workspace_trial(%s)', (ws,)).fetchone() == (start, end)
    from app.api import routes
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return end
    monkeypatch.setattr(routes, 'datetime', Clock)
    expired = browser.get(f'/api/v1/workspaces/{workspace}/subscription').json()
    assert expired['trial']['active'] is False
    assert expired['access']['analysis_allowed'] is False and expired['access']['basis'] == 'none'


def test_trial_is_private_and_cannot_be_reset_by_application(rw, db):
    ws = new_workspace(rw)
    uid = one(rw, "SELECT user_id FROM organization_memberships m JOIN workspaces w ON w.organization_id=m.organization_id WHERE w.id=%s", ws)
    rw.execute('SELECT start_registration_trial(%s,%s)', (uid, ws))
    with db('app_rw') as app:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute('SELECT * FROM registration_trials')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute('UPDATE registration_trials SET ends_at=now()+interval \'30 days\'')
        with workspace_scope(app, ws+100000):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute('SELECT * FROM workspace_trial(%s)', (ws,))


@pytest.mark.parametrize('role', ['app_rw', 'app_system', 'app_token', 'app_deleter'])
def test_trial_ledger_has_function_only_access(db, role):
    with db(role) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute('SELECT * FROM registration_trials')


def test_deleting_bound_workspace_preserves_user_trial_claim(db, rw):
    from test_schema import connected
    ws = new_workspace(rw)
    uid = one(rw, "SELECT user_id FROM organization_memberships m JOIN workspaces w ON w.organization_id=m.organization_id WHERE w.id=%s", ws)
    other = new_workspace(rw, user=uid)
    rw.execute('SELECT start_registration_trial(%s,%s)', (uid, ws))
    direct = connected(rw, 'direct', ws, 'bound-delete')
    metrika = connected(rw, 'metrika', ws, 'bound-delete')
    counter = one(rw, 'INSERT INTO metrika_counters(metrika_connection_id,counter_id,goal_ids,is_selected) VALUES(%s,555,\'{111}\',true) RETURNING id', metrika)
    rw.execute('INSERT INTO direct_accounts(direct_connection_id,metrika_counter_id,metrika_configured) VALUES(%s,%s,true)', (direct, counter))
    rw.execute("UPDATE workspaces SET status='deletion_pending',deactivated_at=now() WHERE id=%s", (ws,))
    with db('app_deleter') as deleter:
        deleter.execute('SELECT delete_workspace_data(%s)', (ws,))
    rw.execute('SELECT start_registration_trial(%s,%s)', (uid, other))
    assert not load_state(rw, other, None, datetime.now(timezone.utc)).has_analysis_access
    assert one(rw, 'SELECT count(*) FROM workspaces WHERE id=%s', ws) == 0
