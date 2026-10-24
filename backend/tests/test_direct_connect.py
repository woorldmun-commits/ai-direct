"""Real PostgreSQL/RLS and worker pipeline; Yandex HTTP is the only replaced boundary."""
import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.api import create_app, direct_connect
from app.auth.tokens import ConnectionRef, EnvKeys, load
from app.auth.yandex_oauth import OAuthApp
from app.sources.direct import DirectFixture
from app.tenancy import workspace_scope
from app.worker import runner
from app.worker.guard import Allow, Skip, Task, guard, load_state, pilot_until
from test_api_support import ORIGIN, client_for, session, settings, user
from test_direct_sync import GOALS, TO, root  # noqa: F401
from test_schema import one

PROVIDER = OAuthApp("pilot-client", "synthetic-secret-for-tests-only", ORIGIN+"/api/direct/callback", direct_connect.SCOPES)
KEYS = EnvKeys({"TOKEN_ENCRYPTION_KEY_VERSION":"1", "TOKEN_ENCRYPTION_KEY_1":base64.b64encode(b"k"*32).decode()})


@pytest.fixture
def pilot(db, rw, monkeypatch):
    owner = user(rw)
    with rw.transaction():
        org = one(rw, "SELECT create_organization(%s,'Pilot','business')", owner)
    ws = one(rw, "SELECT create_workspace(%s,%s,'Pilot')", owner, org)
    monkeypatch.setenv("PILOT_WORKSPACE_IDS", f"ws_{ws}")
    monkeypatch.setenv("PILOT_ACCESS_UNTIL", (datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    app = create_app(settings(db, oauth_direct=PROVIDER, token_keys=KEYS))
    with client_for(app) as client:
        client.cookies.set("session", session(rw, owner))
        yield client, ws, owner


def begin(client, ws, **extra):
    return client.post(f"/api/v1/workspaces/ws_{ws}/direct/start",
                       json={"login":"pilot-account", **extra}, headers={"Origin":ORIGIN})


def finish(client, state):
    return client.get("/api/v1/direct/callback", params={"state":state,"code":"synthetic-code"}, follow_redirects=False)


def fake_yandex(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/token":
            return httpx.Response(200,json={"access_token":"synthetic-access","refresh_token":"synthetic-refresh", "expires_in":31536000})
        if request.url.path == "/json/v5/campaigns":
            return httpx.Response(200,json={"result":{"Campaigns":[]}})
        if request.url.path == "/management/v1/counter/555/goals":
            return httpx.Response(200,json={"goals":[{"id":111},{"id":222}]})
        raise AssertionError(request.url.path)
    original = httpx.Client
    monkeypatch.setattr(direct_connect.httpx,"Client",lambda **kw:original(transport=httpx.MockTransport(handler), **kw))
    return calls


def test_pilot_grant_fails_closed_and_never_marks_subscription_paid(pilot, rw, monkeypatch):
    _, ws, _ = pilot
    now = datetime.now(timezone.utc)
    state = load_state(rw, ws, None, now)
    assert not state.paid and state.has_analysis_access
    assert isinstance(guard(Task.AUDIT,state), Allow)
    assert isinstance(guard(Task.SYNC,state), Skip)  # access does not bypass a missing Direct connection
    monkeypatch.setenv("PILOT_ACCESS_UNTIL", now.isoformat())
    assert not load_state(rw,ws,None,now).has_analysis_access
    for value in ("bad", "2026-10-20"):
        monkeypatch.setenv("PILOT_ACCESS_UNTIL",value)
        assert pilot_until(ws) is None
    monkeypatch.setenv("PILOT_WORKSPACE_IDS",str(ws+100000))
    assert pilot_until(ws) is None


def test_start_checks_session_role_origin_access_and_goal_pair(pilot, db, rw, monkeypatch):
    client, ws, owner = pilot
    response = begin(client,ws,counter_id=555)
    assert response.status_code==400
    assert client.post(f"/api/v1/workspaces/ws_{ws}/direct/start",json={"login":"pilot-account"},
                       headers={"Origin":"https://attacker.example"}).status_code==403
    viewer=user(rw)
    org=one(rw,"SELECT organization_id FROM workspaces WHERE id=%s",ws)
    rw.execute("SELECT set_organization_member(%s,%s,%s,'member')",(owner,org,viewer))
    rw.execute("SELECT set_workspace_member(%s,%s,%s,'viewer')",(owner,ws,viewer))
    original=client.cookies.get("session")
    client.cookies.clear()
    client.cookies.set("session",session(rw,viewer))
    assert begin(client,ws).status_code==403
    client.cookies.clear()
    client.cookies.set("session",original)
    monkeypatch.delenv("PILOT_WORKSPACE_IDS")
    assert begin(client,ws).status_code==403
    client.cookies.clear()
    assert begin(client,ws).status_code==401


def test_callback_state_and_actor_are_bound_before_network(pilot, monkeypatch, rw):
    client,ws,_=pilot
    calls=fake_yandex(monkeypatch)
    r=begin(client,ws)
    assert r.status_code==200
    assert all(value in r.headers["set-cookie"] for value in ("HttpOnly","Secure","Max-Age=600","SameSite=lax"))
    state=parse_qs(urlsplit(r.json()["authorize_url"]).query)["state"][0]
    assert "direct=failed" in finish(client,"x"*43).headers["location"]
    assert calls==[]
    r=begin(client,ws)
    state=parse_qs(urlsplit(r.json()["authorize_url"]).query)["state"][0]
    flow=client.cookies.get(direct_connect.FLOW_COOKIE)
    client.cookies.clear()
    client.cookies.set(direct_connect.FLOW_COOKIE,flow)
    client.cookies.set("session",session(rw,user(rw)))
    assert "direct=failed" in finish(client,state).headers["location"]
    assert calls==[]


def test_oauth_encryption_queue_worker_and_audit_resume(pilot, db, rw, monkeypatch, root):
    client,ws,_=pilot
    calls=fake_yandex(monkeypatch)
    r=begin(client,ws,counter_id=GOALS.counter_id,goal_ids=list(GOALS.goal_ids))
    state=parse_qs(urlsplit(r.json()["authorize_url"]).query)["state"][0]
    r=finish(client,state)
    assert r.status_code==303 and "direct=connected" in r.headers["location"]
    assert calls==["/token","/json/v5/campaigns","/management/v1/counter/555/goals"]
    run_id,account=rw.execute("SELECT id,direct_account_id FROM sync_runs WHERE workspace_id=%s",(ws,)).fetchone()
    encrypted=rw.execute("SELECT has_token FROM direct_connections WHERE workspace_id=%s",(ws,)).fetchone()[0]
    assert encrypted
    # duplicate enqueue is idempotent while the worker is pending
    assert client.post(f"/api/v1/workspaces/ws_{ws}/direct/sync",json={},headers={"Origin":ORIGIN}).json()["run_id"]==run_id
    root("pilot-account")
    monkeypatch.setattr(runner,"DirectApi",lambda *args:DirectFixture(root.path))
    # Metrika is optional for rules that use Direct conversion columns; use an unavailable fixture.
    monkeypatch.setattr(runner,"MetrikaApi",lambda *args:None)
    rw.execute("UPDATE sync_runs SET period_to=%s WHERE id=%s",(TO,run_id))
    release=one(rw,"INSERT INTO releases(commit_sha,build_id) VALUES(%s,%s) RETURNING id","b"*40,f"pilot-{ws}")
    with db("app_token") as token_conn, db("app_system") as queue:
        runner.verify_role(token_conn,"app_token")
        runner.verify_role(queue,"app_system")
        with workspace_scope(token_conn,ws):
            connection=one(token_conn,"SELECT direct_connection_id FROM direct_accounts WHERE id=%s",account)
            assert load(token_conn,KEYS,ConnectionRef("direct",ws,connection)).access_token=="synthetic-access"
        # the worker uses the frozen cutoff instead of today's date
        runner.process(queue,token_conn,run_id,provider=PROVIDER,keys=KEYS,release_id=release,http=None,
                       now=datetime.now(timezone.utc))
        assert one(rw,"SELECT status FROM sync_runs WHERE id=%s",run_id)=="succeeded"
        assert one(rw,"SELECT count(*) FROM audit_runs WHERE workspace_id=%s",ws)==1
        runner.process(queue,token_conn,run_id,provider=PROVIDER,keys=KEYS,release_id=release,http=None,
                       now=datetime.now(timezone.utc))
        assert one(rw,"SELECT count(*) FROM audit_runs WHERE workspace_id=%s",ws)==1
    assert one(rw,"SELECT count(*) FROM recommendations r JOIN issues i ON i.id=r.issue_id WHERE i.workspace_id=%s",ws)>0


def test_unconfigured_direct_is_disabled(db,rw):
    with client_for(create_app(settings(db))) as client:
        assert client.get("/api/v1/direct/callback").status_code==401


def test_invalid_goals_do_not_save_a_connection(pilot,rw,monkeypatch):
    client,ws,_=pilot
    fake_yandex(monkeypatch)
    r=begin(client,ws,counter_id=555,goal_ids=[999])
    state=parse_qs(urlsplit(r.json()["authorize_url"]).query)["state"][0]
    assert 'direct=failed' in finish(client,state).headers['location']
    assert one(rw,'SELECT count(*) FROM direct_connections WHERE workspace_id=%s',ws)==0


@pytest.mark.parametrize('document',['privacy','cookies','requisites'])
def test_public_legal_documents_have_a_draft_state(pilot,document):
    client,_,_=pilot
    r=client.get(f'/api/v1/legal/documents/{document}?version=2026-10-01')
    assert r.status_code==200 and r.json()['approved'] is False


def test_worker_rejects_api_role(db):
    with db("app_rw") as conn:
        with pytest.raises(RuntimeError):
            runner.verify_role(conn,"app_token")


def test_daily_runner_refresh_is_idempotent_and_requires_access(pilot,db,rw,monkeypatch):
    client,ws,_=pilot
    fake_yandex(monkeypatch)
    response=begin(client,ws)
    state=parse_qs(urlsplit(response.json()['authorize_url']).query)['state'][0]
    assert 'direct=connected' in finish(client,state).headers['location']
    run_id,account=rw.execute('SELECT id,direct_account_id FROM sync_runs WHERE workspace_id=%s',(ws,)).fetchone()
    now=datetime.now(timezone.utc)
    cutoff=now.astimezone(runner.DATA_TIMEZONE).date()-timedelta(days=1)
    rw.execute("UPDATE sync_runs SET status='failed',started_at=now(),finished_at=now(),error_code='synthetic_failure',period_to=%s WHERE id=%s",(cutoff-timedelta(days=1),run_id))
    with db('app_system') as queue,db('app_token') as worker:
        runner.schedule_syncs(queue,worker,now)
        runner.schedule_syncs(queue,worker,now)
    assert one(rw,'SELECT count(*) FROM sync_runs WHERE workspace_id=%s AND period_to=%s',ws,cutoff)==1
    pending=one(rw,"SELECT id FROM sync_runs WHERE workspace_id=%s AND status='queued'",ws)
    rw.execute("UPDATE sync_runs SET status='failed',started_at=now(),finished_at=now(),error_code='synthetic_failure' WHERE id=%s",(pending,))
    monkeypatch.setenv('PILOT_ACCESS_UNTIL',now.isoformat())
    with db('app_system') as queue,db('app_token') as worker:
        runner.schedule_syncs(queue,worker,now+timedelta(days=1))
    assert one(rw,'SELECT count(*) FROM sync_runs WHERE workspace_id=%s',ws)==2
