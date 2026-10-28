"""Synthetic PostgreSQL evidence and MockTransport; no providers or secrets."""
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import httpx
import psycopg
import pytest
from app.tenancy import workspace_scope
from app.worker import verification
from test_schema import chain, one, EXECUTED, EVENT_AT, new_workspace
from test_api_support import recommendation
from test_direct_params import campaign, FakeDirect
from test_verification_membership import ACTION

@pytest.fixture
def execution(rw,chain):
    rec=recommendation(rw,chain['ws'],f"verify-{chain['ws']}",'100.00',action=ACTION)
    data={**chain,**rec}
    rw.execute("INSERT INTO subscriptions(workspace_id,plan,status,price,current_period_start,current_period_end) VALUES (%s,'start','active',1990,now()-interval '1 day',now()+interval '1 month')",(data['ws'],))
    done=one(rw,"""INSERT INTO recommendation_events(recommendation_id,type,actor_user_id,finding_id,execution_date,created_at)
        VALUES (%s,'done',%s,%s,%s,%s) RETURNING id""",data['rec'],data['user'],data['finding'],EXECUTED,EVENT_AT)
    return {**data,"done":done}

@pytest.fixture
def job(rw,execution):
    data=execution
    done=data["done"]
    jid=one(rw,"""INSERT INTO recommendation_verification_jobs(workspace_id,recommendation_id,finding_id,done_event_id,
        requested_by,idempotency_key,request_sha256,method) VALUES (%s,%s,%s,%s,%s,%s,%s,'excluded_sites_membership@1') RETURNING id""",
        data['ws'],data['rec'],data['finding'],done,data['user'],uuid4(),'a'*64)
    return {**data,'job':jid,'done':done}

def insert_read(conn,job,**changes):
    data=dict(job=job['job'],ws=job['ws'],release=job['release'],status='confirmed',target=2,matched=2,masked=0)
    data.update(changes)
    return conn.execute("""INSERT INTO recommendation_verification_reads(job_id,workspace_id,release_id,attempt,read_at,status,reason,
        params_hash,target_count,matched_count,masked_count) VALUES (%(job)s,%(ws)s,%(release)s,1,now(),%(status)s,'test',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',%(target)s,%(matched)s,%(masked)s) RETURNING id""",data).fetchone()[0]

def test_rw_cannot_fabricate_read(db,job):
    with db('app_rw') as conn,workspace_scope(conn,job['ws']):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            insert_read(conn,job)

def test_read_append_only_and_consistency(db,job):
    with db('app_token') as conn,workspace_scope(conn,job['ws']):
        with pytest.raises(psycopg.errors.CheckViolation):
            insert_read(conn,job,matched=1)
        rid=insert_read(conn,job)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE recommendation_verification_reads SET reason='forged' WHERE id=%s",(rid,))

def test_cross_workspace_read_rejected(db,rw,job):
    other=new_workspace(rw)
    with db('app_token') as conn,workspace_scope(conn,other):
        assert one(conn,'SELECT count(*) FROM recommendation_verification_jobs WHERE id=%s',job['job'])==0
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            insert_read(conn,job,ws=other)

def test_same_workspace_foreign_done_rejected(rw,job):
    other=recommendation(rw,job['ws'],'synthetic-other-verification','100.00')
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("""INSERT INTO recommendation_verification_jobs(workspace_id,recommendation_id,finding_id,done_event_id,
          requested_by,idempotency_key,request_sha256,method) VALUES (%s,%s,%s,%s,%s,%s,%s,'excluded_sites_membership@1')""",
          (job['ws'],other['rec'],other['finding'],job['done'],job['user'],uuid4(),'b'*64))

def run(db,job,monkeypatch,fake,when=None):
    monkeypatch.setattr(verification,'fresh_access_token',lambda *a:'synthetic')
    when=when or datetime.now(timezone.utc)+timedelta(seconds=1)
    with db('app_token') as conn,httpx.Client(transport=httpx.MockTransport(fake)) as http:
        verification.process(conn,job['job'],job['ws'],provider=None,keys=None,release_id=job['release'],http=http,now=when,clock=lambda:when)
    return when

def test_worker_success_and_replay(db,rw,job,monkeypatch):
    fake=FakeDirect([campaign(cid=job['object_id'],sites=('a.ru','b.ru'))])
    run(db,job,monkeypatch,fake)
    run(db,job,monkeypatch,fake)
    assert len(fake.requests)==1
    assert rw.execute('SELECT status,target_count,matched_count FROM recommendation_verification_reads WHERE job_id=%s',(job['job'],)).fetchone()==('confirmed',2,2)
    assert one(rw,'SELECT attempts FROM recommendation_verification_jobs WHERE id=%s',job['job'])==1
    assert one(rw,"SELECT count(*) FROM recommendation_events WHERE recommendation_id=%s AND type NOT IN ('done')",job['rec'])==0

def test_transient_retries_bounded(db,rw,job,monkeypatch):
    fake=FakeDirect(status=503,error=1000)
    when=None
    for attempt in range(5):
        when=run(db,job,monkeypatch,fake,when)
        when=one(rw,'SELECT available_at FROM recommendation_verification_jobs WHERE id=%s',job['job'])+timedelta(seconds=1)
    assert one(rw,'SELECT attempts FROM recommendation_verification_jobs WHERE id=%s',job['job'])==5
    assert one(rw,'SELECT finished_at IS NOT NULL FROM recommendation_verification_jobs WHERE id=%s',job['job'])
    assert one(rw,'SELECT reason FROM recommendation_verification_reads WHERE job_id=%s ORDER BY attempt DESC LIMIT 1',job['job'])=='retries_exhausted'

def test_worker_rechecks_selection(db,rw,job,monkeypatch):
    rw.execute('UPDATE direct_accounts SET is_selected=false WHERE id=%s',(job['account'],))
    fake=FakeDirect()
    run(db,job,monkeypatch,fake)
    assert fake.requests==[]
    assert one(rw,'SELECT status FROM recommendation_verification_reads WHERE job_id=%s',job['job'])=='unavailable'

def test_competing_worker_does_not_read(db,job,monkeypatch):
    fake=FakeDirect()
    with db('app_token') as lock:
        lock.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))",(f"verification:{job['job']}",))
        run(db,job,monkeypatch,fake)
    assert fake.requests==[]


def test_enqueue_and_replay(rw,execution):
    from app.api.verification import enqueue,status
    from app.api.recommendation_flow import _load,Mutation
    from app.api.deps import Workspace,Actor
    ws=Workspace(execution['ws'],'owner',Actor(execution['user']))
    data=_load(rw,ws,f"rec_{execution['rec']}")
    payload=Mutation(expected_version_id=f"rv_{execution['finding']}",expected_state_version=data['state'],idempotency_key=uuid4())
    with rw.transaction():
        receipt=enqueue(rw,ws,data,payload)
    with rw.transaction():
        assert enqueue(rw,ws,data,payload)==receipt
    assert status(rw,data,ws)['status']=='pending'
    assert one(rw,'SELECT count(*) FROM recommendation_verification_jobs WHERE done_event_id=%s',execution['done'])==1
    assert one(rw,'SELECT count(*) FROM recommendation_verification_reads WHERE job_id=%s',int(receipt['request_id'].split('_')[1]))==0

@pytest.mark.parametrize('change,code',[(dict(expected_version_id='rv_999999'),'version_outdated'),(dict(expected_state_version='initial'),'state_outdated')])
def test_enqueue_stale(rw,execution,change,code):
    from app.api.verification import enqueue
    from app.api.recommendation_flow import _load,Mutation
    from app.api.deps import Workspace,Actor
    from app.api.errors import ApiError
    ws=Workspace(execution['ws'],'owner',Actor(execution['user']))
    data=_load(rw,ws,f"rec_{execution['rec']}")
    body=dict(expected_version_id=f"rv_{execution['finding']}",expected_state_version=data['state'],idempotency_key=uuid4())
    with rw.transaction(),pytest.raises(ApiError) as error:
        enqueue(rw,ws,data,Mutation(**(body|change)))
    assert error.value.code==code

def test_enqueue_role_and_key_conflict(rw,execution):
    from app.api.verification import enqueue
    from app.api.recommendation_flow import _load,Mutation
    from app.api.deps import Workspace,Actor
    from app.api.errors import ApiError
    ws=Workspace(execution['ws'],'owner',Actor(execution['user']))
    data=_load(rw,ws,f"rec_{execution['rec']}")
    payload=Mutation(expected_version_id=f"rv_{execution['finding']}",expected_state_version=data['state'],idempotency_key=uuid4())
    with rw.transaction(),pytest.raises(ApiError) as error:
        enqueue(rw,Workspace(ws.id,'viewer',ws.actor),data,payload)
    assert error.value.status==403
    with rw.transaction():
        enqueue(rw,ws,data,payload)
    with rw.transaction(),pytest.raises(ApiError) as error:
        enqueue(rw,ws,data,payload.model_copy(update={'expected_state_version':'initial'}))
    assert error.value.code=='idempotency_conflict'

def test_worker_does_not_enable_saved_total(db,rw,job,monkeypatch):
    from app.worker.measure import verification_status
    fake=FakeDirect([campaign(cid=job['object_id'],sites=('a.ru','b.ru'))])
    run(db,job,monkeypatch,fake)
    assert verification_status(rw,job['rec'],job['done'])=='pending'

def test_workspace_deletion_removes_evidence(db,rw,job):
    with db('app_token') as token,workspace_scope(token,job['ws']):
        insert_read(token,job)
    rw.execute("UPDATE workspaces SET status='deletion_pending',deactivated_at=now() WHERE id=%s",(job['ws'],))
    with db('app_deleter') as conn:
        counts=one(conn,'SELECT delete_workspace_data(%s)',job['ws'])
    assert counts['recommendation_verification_reads']==1
    assert counts['recommendation_verification_jobs']==1


def test_worker_crash_releases_lock_and_remains_retryable(db,rw,job,monkeypatch):
    fake=FakeDirect([campaign(cid=job['object_id'],sites=('a.ru','b.ru'))])
    original=verification.read_object_params
    def broken(*args):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(verification,'read_object_params',broken)
    with pytest.raises(RuntimeError):
        run(db,job,monkeypatch,fake)
    assert one(rw,'SELECT attempts FROM recommendation_verification_jobs WHERE id=%s',job['job'])==1
    assert one(rw,'SELECT finished_at FROM recommendation_verification_jobs WHERE id=%s',job['job']) is None
    monkeypatch.setattr(verification,'read_object_params',original)
    when=one(rw,'SELECT available_at FROM recommendation_verification_jobs WHERE id=%s',job['job'])+timedelta(seconds=1)
    run(db,job,monkeypatch,fake,when)
    assert one(rw,'SELECT status FROM recommendation_verification_reads WHERE job_id=%s',job['job'])=='confirmed'

def test_later_finding_does_not_inherit_confirmation(db,rw,job,monkeypatch):
    from app.api.verification import status
    from app.api.recommendation_flow import _load
    from app.api.deps import Workspace,Actor
    fake=FakeDirect([campaign(cid=job['object_id'],sites=('a.ru','b.ru'))])
    run(db,job,monkeypatch,fake)
    audit=one(rw,"""INSERT INTO audit_runs(workspace_id,release_id,kind,task_key,data_cutoff,settings,rules_run)
        SELECT workspace_id,release_id,kind,gen_random_uuid()::text,data_cutoff,settings,rules_run
        FROM audit_runs WHERE id=%s RETURNING id""",job['audit'])
    finding=one(rw,"""INSERT INTO findings(audit_run_id,issue_id,rule_version,lost,recoverable,data_quality,evidence,action,safety_policy,candidate_level,action_level)
        SELECT %s,issue_id,rule_version,lost,recoverable,data_quality,evidence,action,safety_policy,candidate_level,action_level
        FROM findings WHERE id=%s RETURNING id""",audit,job['finding'])
    explanation=one(rw,"INSERT INTO explanations(finding_id,source,text,release_id) VALUES (%s,'template','Synthetic new version',%s) RETURNING id",finding,job['release'])
    rw.execute("INSERT INTO recommendation_events(recommendation_id,type,finding_id,explanation_id) VALUES (%s,'seen_again',%s,%s)",(job['rec'],finding,explanation))
    ws=Workspace(job['ws'],'owner',Actor(job['user']))
    data=_load(rw,ws,f"rec_{job['rec']}")
    assert status(rw,data,ws)['reason']=='execution_version_outdated'
