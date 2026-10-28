"""Read-only subscription details use the same state as worker access checks."""
from datetime import datetime, timedelta, timezone

import pytest

from app.api import routes
from test_api_support import api, cookie, session, world  # noqa: F401

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(routes, 'datetime', Clock, raising=False)
    monkeypatch.delenv('PILOT_OPEN_ACCESS', raising=False)
    monkeypatch.delenv('PILOT_WORKSPACE_IDS', raising=False)
    monkeypatch.delenv('PILOT_ACCESS_UNTIL', raising=False)


def get(api, rw, world, who='owner', workspace='a1'):
    return api.get(f"/api/v1/workspaces/ws_{world[workspace]}/subscription",
                   headers=cookie(session(rw, world[who])))


def subscribe(rw, workspace, status='active', end=NOW+timedelta(days=10), start=NOW-timedelta(days=20)):
    rw.execute('''INSERT INTO subscriptions(workspace_id,plan,status,price,current_period_start,
                  current_period_end,auto_renew,renew_consent_at,payment_method_ref,canceled_at)
                  VALUES(%s,'start',%s,2990.10,%s,%s,false,%s,'provider-secret-token',%s)''',
               (workspace,status,start,end,NOW-timedelta(days=21),NOW-timedelta(days=1) if status=='canceled' else None))


def test_empty_subscription_is_not_trial(api, rw, world):
    response=get(api,rw,world)
    assert response.status_code==200, response.text
    body=response.json()
    assert body['subscription'] is None
    assert body['access']=={'paid':False,'analysis_allowed':False,'basis':'none','paid_until':None,'pilot_until':None}


@pytest.mark.parametrize('status,end_days,paid', [
    ('active',10,True),('active',-2,True),('active',-3,False),
    ('past_due',-2,True),('past_due',-3,False),
    ('canceled',1,True),('canceled',0,False),('expired',10,False),
])
def test_actual_subscription_and_access_boundaries(api,rw,world,status,end_days,paid):
    end=NOW+timedelta(days=end_days)
    subscribe(rw,world['a1'],status,end)
    response=get(api,rw,world)
    assert response.status_code==200,response.text
    body=response.json()
    assert body['subscription']['price_amount']=='2990.10'
    assert body['subscription']['currency']=='RUB'
    assert body['subscription']['status']==status
    assert body['subscription']['plan']=='start'
    assert body['access']['paid'] is paid
    assert body['access']['analysis_allowed'] is paid
    assert body['access']['basis']==('subscription' if paid else 'none')
    expected=end+(timedelta(days=3) if status in ('active','past_due') else timedelta(0))
    assert (datetime.fromisoformat(body['access']['paid_until'])==expected) if paid else body['access']['paid_until'] is None
    assert 'provider-secret-token' not in response.text
    assert 'payment_method_ref' not in response.text and 'renew_consent_at' not in response.text


def test_pilot_does_not_mark_subscription_paid(api,rw,world,monkeypatch):
    until=NOW+timedelta(days=1)
    monkeypatch.setenv('PILOT_WORKSPACE_IDS',str(world['a1']))
    monkeypatch.setenv('PILOT_ACCESS_UNTIL',until.isoformat())
    body=get(api,rw,world).json()
    assert body['subscription'] is None
    assert body['access']['basis']=='pilot' and body['access']['analysis_allowed']
    assert not body['access']['paid']
    monkeypatch.setenv('PILOT_ACCESS_UNTIL',NOW.isoformat())
    assert get(api,rw,world).json()['access']['basis']=='none'


def test_future_subscription_is_ignored_and_current_beats_history(api,rw,world):
    subscribe(rw,world['a1'],start=NOW+timedelta(seconds=1))
    assert get(api,rw,world).json()['subscription'] is None
    rw.execute("UPDATE subscriptions SET status='expired' WHERE workspace_id=%s",(world['a1'],))
    subscribe(rw,world['a1'])
    subscribe(rw,world['a1'],'expired',NOW+timedelta(days=30))
    assert get(api,rw,world).json()['subscription']['status']=='active'


def test_deactivated_workspace_retains_paid_entitlement_but_blocks_analysis(api,rw,world):
    subscribe(rw,world['a1'])
    rw.execute("UPDATE workspaces SET status='deactivated',deactivated_at=now() WHERE id=%s",(world['a1'],))
    body=get(api,rw,world).json()
    assert body['workspace_status']=='deactivated'
    assert body['access']['paid'] and not body['access']['analysis_allowed']


def test_manager_scope_and_auth(api,rw,world):
    subscribe(rw,world['a1'])
    assert get(api,rw,world,'admin').status_code==200
    assert get(api,rw,world,'viewer').status_code==403
    assert get(api,rw,world,'member').status_code==404
    assert get(api,rw,world,workspace='b1').status_code==404
    assert api.get(f"/api/v1/workspaces/ws_{world['a1']}/subscription").status_code==401


def test_real_renewal_flag_and_last_expired_record(api,rw,world):
    subscribe(rw,world['a1'])
    rw.execute('UPDATE subscriptions SET auto_renew=true WHERE workspace_id=%s',(world['a1'],))
    assert get(api,rw,world).json()['subscription']['auto_renew'] is True
    rw.execute("UPDATE subscriptions SET auto_renew=false,status='expired' WHERE workspace_id=%s",(world['a1'],))
    subscribe(rw,world['a1'],'expired',NOW-timedelta(days=5))
    body=get(api,rw,world).json()
    assert datetime.fromisoformat(body['subscription']['period_end'])==NOW+timedelta(days=10)
    assert not body['access']['paid']
