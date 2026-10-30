"""Real database contracts; all users, payments and advertising data are synthetic."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest

from app.api.deps import Actor, Workspace
from app.api.errors import ApiError
from app.billing.routes import OrderInput
from app.billing.service import reserve, get_order, apply_payment
from app.tenancy import workspace_scope
from app.worker.guard import Allow, Skip, Task, guard, load_state
from test_billing import CONFIG, payment
from test_billing_db import confirmed
from test_schema import new_workspace, one, chain  # noqa: F401
from test_direct_sync import root  # noqa: F401
from test_api_support import api, cookie,session  # noqa: F401


def owner(conn, ws):
    return one(conn, 'SELECT m.user_id FROM organization_memberships m JOIN workspaces w ON w.organization_id=m.organization_id WHERE w.id=%s AND m.org_role=\'owner\'', ws)


def test_trial_pending_only_allows_bootstrap_sync(rw):
    ws = new_workspace(rw)
    rw.execute('SELECT start_registration_trial(%s,%s)', (owner(rw,ws),ws))
    s = load_state(rw,ws,None,datetime.now(timezone.utc))
    assert s.trial_pending and not s.trial_active and not s.has_analysis_access
    assert guard(Task.AUDIT,s) == Skip('subscription_inactive','none')
    assert guard(Task.SYNC,s).reason == 'direct_unavailable'


def test_trial_starts_after_sealed_snapshot_and_never_restarts(rw,chain,root):
    from test_snapshot_store import fetch, sync_run, write
    ws=chain['ws']
    rw.execute('SELECT start_registration_trial(%s,%s)',(owner(rw,ws),ws))
    assert load_state(rw,ws,None,datetime.now(timezone.utc)).trial_pending
    snap=fetch(root)
    write(rw,chain,sync_run(rw,chain),snap)
    first=rw.execute('SELECT * FROM workspace_trial(%s)',(ws,)).fetchone()
    assert first[1]-first[0]==timedelta(days=7)
    assert load_state(rw,ws,None,first[0]).trial_active
    assert not load_state(rw,ws,None,first[1]).has_analysis_access
    write(rw,chain,sync_run(rw,chain),snap)
    assert rw.execute('SELECT * FROM workspace_trial(%s)',(ws,)).fetchone()==first


def subscribe(conn, ws, plan='business_plus'):
    return one(conn, '''INSERT INTO subscriptions(workspace_id,plan,status,price,current_period_start,current_period_end)
        VALUES(%s,%s,'active',9990,now()-interval '1 second',now()+interval '30 days') RETURNING id''',ws,plan)


def test_agency_clients_share_only_subscription_and_enforce_five(rw,db):
    ws = new_workspace(rw)
    uid = owner(rw,ws)
    sid = subscribe(rw,ws)
    operation = uuid4()
    child = one(rw,"SELECT create_agency_client(%s,%s,'Client A',%s)",uid,ws,operation)
    assert child == one(rw,"SELECT create_agency_client(%s,%s,'Ignored retry',%s)",uid,ws,operation)
    for i in range(3):
        one(rw,'SELECT create_agency_client(%s,%s,%s,%s)',uid,ws,f'Client {i}',uuid4())
    with pytest.raises(psycopg.errors.CheckViolation):
        one(rw,"SELECT create_agency_client(%s,%s,'Sixth',%s)",uid,ws,uuid4())
    assert load_state(rw,child,None,datetime.now(timezone.utc)).paid
    assert one(rw,'SELECT organization_id FROM workspaces WHERE id=%s',child) != one(rw,'SELECT organization_id FROM workspaces WHERE id=%s',ws)
    with db('app_rw') as app, workspace_scope(app,child):
        assert one(app,'SELECT count(*) FROM workspaces WHERE id=%s',ws)==0
        assert one(app,'SELECT count(*) FROM effective_subscription(%s,now())',child)==1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute('SELECT * FROM agency_workspaces')
    rw.execute("UPDATE subscriptions SET status='expired' WHERE id=%s",(sid,))
    assert not load_state(rw,child,None,datetime.now(timezone.utc)).has_analysis_access


def test_agency_aggregate_accounts_cannot_be_bypassed_by_another_workspace(rw):
    from test_schema import connected
    ws = new_workspace(rw)
    uid = owner(rw,ws)
    subscribe(rw,ws)
    child = one(rw,"SELECT create_agency_client(%s,%s,'Client',%s)",uid,ws,uuid4())
    for target in (ws,child):
        connection=connected(rw,'direct',target,f'account-{target}')
        rw.execute('INSERT INTO direct_accounts(direct_connection_id,client_login,is_selected) VALUES(%s,%s,true)',(connection,f'account-{target}'))
    assert rw.execute('SELECT * FROM billing_scope(%s)',(child,)).fetchone() == (ws,2,2)
    assert rw.execute('SELECT * FROM billing_scope(%s,%s,true)',(child,f'account-{child}')).fetchone() == (ws,2,1)
    from types import SimpleNamespace
    from app.api.direct_connect import _save,Flow
    connection=one(rw,'SELECT id FROM direct_connections WHERE workspace_id=%s',ws)
    for i in range(13):
        rw.execute('INSERT INTO direct_accounts(direct_connection_id,client_login,is_selected) VALUES(%s,%s,true)',(connection,f'extra-{i}'))
    with pytest.raises(ApiError) as exc,rw.transaction():
        _save(rw,SimpleNamespace(),Flow(login='sixteenth',state='s'*40,user_id=uid,workspace_id=child),None)
    assert exc.value.code=='pilot_account_limit'


def test_agency_child_cannot_checkout_separate_plan(rw):
    ws=new_workspace(rw)
    uid=owner(rw,ws)
    subscribe(rw,ws)
    child=one(rw,"SELECT create_agency_client(%s,%s,'Separate',%s)",uid,ws,uuid4())
    payload=OrderInput(request_id=uuid4(),sku='control',terms_sha256=CONFIG.terms_sha256)
    with pytest.raises(ApiError) as exc,rw.transaction():
        reserve(rw,Workspace(child,'owner',Actor(uid)),payload,CONFIG)
    assert exc.value.code=='billing_bundle_managed'


def test_twenty_founder_slots_have_separate_test_and_live_capacity(rw):
    with rw.transaction(force_rollback=True):
        for i in range(20):
            ws=new_workspace(rw,f'Founder {i}')
            assert one(rw,'SELECT founder_offer(%s,%s,false,true)',owner(rw,ws),ws)==3
        ws=new_workspace(rw,'Founder 21')
        assert one(rw,'SELECT founder_offer(%s,%s,false,true)',owner(rw,ws),ws)==0
        assert one(rw,'SELECT founder_offer(%s,%s,true,false)',owner(rw,ws),ws)==3


def test_foreign_context_cannot_read_subscription_or_scope(db,rw):
    ws=new_workspace(rw)
    other=new_workspace(rw)
    with db('app_rw') as app,workspace_scope(app,other):
        for sql in ('SELECT * FROM effective_subscription(%s,now())','SELECT * FROM billing_scope(%s)'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(sql,(ws,))
    with db('app_rw') as app:
        for sql in ('SELECT * FROM effective_subscription(%s,now())','SELECT * FROM billing_scope(%s)'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(sql,(ws,))
    stranger=owner(rw,other)
    for uid in (stranger,None):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            rw.execute('SELECT founder_offer(%s,%s,true,true)',(uid,ws))


def test_pending_trial_api_allows_connection_bootstrap_but_not_analysis(api,rw):
    ws=new_workspace(rw)
    uid=owner(rw,ws)
    rw.execute('SELECT start_registration_trial(%s,%s)',(uid,ws))
    headers=cookie(session(rw,uid))
    result=api.get(f'/api/v1/workspaces/ws_{ws}/direct',headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['trial_pending'] is True and result.json()['analysis_access'] is False


@pytest.mark.parametrize('role',['app_rw','app_token','app_system','app_deleter'])
@pytest.mark.parametrize('table',['agency_workspaces','founder_enrollments'])
def test_billing_ledgers_are_function_only(db,role,table):
    with db(role) as conn,pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(f'SELECT * FROM {table}')


def test_offer_charges_exact_approved_price_and_counts_only_verified_success(rw):
    wsid = new_workspace(rw)
    uid=owner(rw,wsid)
    rw.execute("UPDATE users SET email='synthetic-founder@example.test' WHERE id=%s",(uid,))
    ws=Workspace(wsid,'owner',Actor(uid))
    for n in range(3):
        payload=OrderInput(request_id=uuid4(),sku='control',terms_sha256=CONFIG.terms_sha256,expected_amount_minor=199000)
        with rw.transaction():
            saved=reserve(rw,ws,payload,CONFIG)
            assert saved['amount_minor']==199000
            o=confirmed(rw,saved)
            p=payment(o)
            p['amount']['value']='1990.00'
            apply_payment(rw,CONFIG,o,p)
            apply_payment(rw,CONFIG,get_order(rw,wsid,o['id']),p)
        rw.execute("UPDATE subscriptions SET status='expired' WHERE workspace_id=%s",(wsid,))
        assert one(rw,'SELECT founder_offer(%s,%s,true,false)',uid,wsid)==2-n
    with pytest.raises(ApiError) as exc, rw.transaction():
        reserve(rw,ws,OrderInput(request_id=uuid4(),sku='control',terms_sha256=CONFIG.terms_sha256,expected_amount_minor=199000),CONFIG)
    assert exc.value.code=='billing_offer_changed'
    with rw.transaction():
        saved=reserve(rw,ws,OrderInput(request_id=uuid4(),sku='control',terms_sha256=CONFIG.terms_sha256,expected_amount_minor=299000),CONFIG)
    assert saved['amount_minor']==299000
