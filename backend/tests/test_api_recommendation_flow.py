"""Real PostgreSQL/RLS; accounts and numeric fixtures below are synthetic."""
from datetime import timedelta
from uuid import uuid4
import pytest
from app.api import create_app
from app.api.active import today_msk
from test_api_support import client_for, cookie, session, settings, world  # noqa: F401
from test_schema import one

@pytest.fixture
def api(db):
    app = create_app(settings(db))
    with client_for(app) as client:
        yield client

@pytest.fixture
def flow(api, rw, world):
    rw.execute("INSERT INTO subscriptions (workspace_id,plan,status,price,current_period_start,current_period_end) VALUES (%s,'start','active',1990,now()-interval '1 day',now()+interval '1 month')",(world['a1'],))
    return dict(api=api,rw=rw,ids=world,url=f"/api/v1/workspaces/ws_{world['a1']}/recommendations/rec_{world['rec_a1']['rec']}",headers={**cookie(session(rw,world['owner'])),'Origin':'https://app.example.test'})

def read(f):
    r=f['api'].get(f['url'],headers=f['headers'])
    assert r.status_code==200,r.text
    return r.json()

def body(f,**extra):
    d=read(f)
    return dict(expected_version_id=d['version_id'],expected_state_version=d['state_version'],idempotency_key=str(uuid4()),**extra)

def post(f,path,data,headers=None):
    return f['api'].post(f['url']+path,json=data,headers=headers or f['headers'])

def test_passport(flow):
    d=read(flow)
    assert d['evidence']['clicks']['amount']=='487'
    assert d['exposure']['amount']=='12500.00'
    assert d['history']==[] and d['latest_measurement'] is None
    assert set(d['allowed_actions'])=={'reject','postpone','mark_done_manually'}
    assert d['verification']['status']=='unavailable'

def test_manual_and_replay(flow):
    b=body(flow)
    r=post(flow,'/manual-execution',b)
    assert r.status_code==200,r.text
    d=read(flow)
    assert d['status']=='applied' and d['execution_mode']=='manual'
    assert d['verification_status']=='pending' and d['allowed_actions']==[]
    assert d['latest_measurement']['status']=='pending' and d['latest_measurement']['result'] is None
    assert post(flow,'/manual-execution',b).json()==r.json()
    assert one(flow['rw'],'SELECT count(*) FROM measurements WHERE recommendation_id=%s',flow['ids']['rec_a1']['rec'])==1
    bad=post(flow,'/manual-execution',{**b,'expected_state_version':d['state_version']})
    assert bad.status_code==409 and bad.json()['error']['code']=='idempotency_conflict'

def test_reject(flow):
    b=body(flow,action='reject',reason='too_risky',comment='Synthetic test note')
    r=post(flow,'/decisions',b)
    assert r.status_code==200,r.text
    d=read(flow)
    assert d['status']=='rejected' and d['history'][0]['reason']=='too_risky'
    assert d['latest_measurement'] is None
    assert post(flow,'/decisions',b).json()==r.json()

@pytest.mark.parametrize('extra',[dict(action='reject'),dict(action='reject',reason='other'),dict(action='reject',reason='invented'),dict(action='postpone',until='2000-01-01'),dict(action='postpone',until=(today_msk()+timedelta(days=91)).isoformat()),dict(action='check',comment='not allowed'),dict(action='check',surprise=True)])
def test_invalid(flow,extra):
    assert post(flow,'/decisions',body(flow,**extra)).status_code==400
    assert read(flow)['history']==[]

def test_postpone_then_manual_and_replay_old_receipt(flow):
    b=body(flow,action='postpone',until=(today_msk()+timedelta(days=7)).isoformat())
    r=post(flow,'/decisions',b)
    assert r.status_code==200,r.text
    assert read(flow)['status']=='postponed'
    assert post(flow,'/manual-execution',body(flow)).status_code==200
    assert [e['type'] for e in read(flow)['history']]==['postponed','done']
    assert post(flow,'/decisions',b).json()==r.json()

def test_stale(flow):
    b=body(flow)
    assert post(flow,'/decisions',{**b,'action':'postpone','until':(today_msk()+timedelta(days=2)).isoformat()}).status_code==200
    r=post(flow,'/manual-execution',{**b,'idempotency_key':str(uuid4())})
    assert r.status_code==409 and r.json()['error']['code']=='state_outdated'
    r=post(flow,'/manual-execution',{**body(flow),'expected_version_id':'rv_99999999'})
    assert r.status_code==409 and r.json()['error']['code']=='version_outdated'

@pytest.mark.parametrize('who',['viewer','member','owner_b'])
def test_isolation(flow,who):
    h={**cookie(session(flow['rw'],flow['ids'][who])),'Origin':'https://app.example.test'}
    r=flow['api'].get(flow['url'],headers=h)
    assert r.status_code==(200 if who=='viewer' else 404)
    if who=='viewer':
        assert r.json()['allowed_actions']==[]
    assert post(flow,'/manual-execution',body(flow),h).status_code==(403 if who=='viewer' else 404)
    assert read(flow)['history']==[]

def test_foreign_rec_and_auth(flow):
    url=flow['url'].rsplit('/',1)[0]+'/rec_'+str(flow['ids']['rec_b1']['rec'])
    assert flow['api'].get(url,headers=flow['headers']).status_code==404
    assert flow['api'].get(flow['url']).status_code==401

@pytest.mark.parametrize('role',['admin','analyst','approver'])
def test_deciders(flow,role):
    ids=flow['ids']
    who=ids['admin'] if role=='admin' else ids['member']
    if role!='admin':
        flow['rw'].execute('SELECT set_workspace_member(%s,%s,%s,%s)',(ids['owner'],ids['a1'],who,role))
    h={**cookie(session(flow['rw'],who)),'Origin':'https://app.example.test'}
    assert post(flow,'/manual-execution',body(flow),h).status_code==200

@pytest.mark.parametrize('mode',['expired','future','none'])
def test_access(flow,mode):
    sql={ 'expired':"current_period_start=now()-interval '2 months', current_period_end=now()-interval '1 month'", 'future':"current_period_start=now()+interval '1 day', current_period_end=now()+interval '1 month'",'none':"status='expired'"}[mode]
    flow['rw'].execute('UPDATE subscriptions SET '+sql+' WHERE workspace_id=%s',(flow['ids']['a1'],))
    assert read(flow)['allowed_actions']==[]
    r=post(flow,'/manual-execution',body(flow))
    assert r.status_code==403 and r.json()['error']['reason']=='access_inactive'

def test_csrf_and_no_fake_verification(flow):
    b=body(flow)
    assert post(flow,'/manual-execution',b,cookie(session(flow['rw'],flow['ids']['owner']))).status_code==403
    r=post(flow,'/verification',b)
    assert r.status_code==503 and r.json()['error']['code']=='verification_unavailable'
    assert read(flow)['history']==[]

def test_inactive_evidence(flow):
    flow['rw'].execute('UPDATE direct_accounts SET is_selected=false WHERE id=%s',(flow['ids']['rec_a1']['account'],))
    assert read(flow)['evidence_current'] is False
    r=post(flow,'/manual-execution',body(flow))
    assert r.status_code==409 and r.json()['error']['reason']=='evidence_not_current'

def test_inspect_only_checked_has_no_measurement(flow):
    rw=flow['rw']
    rec=flow['ids']['rec_a1']
    audit=one(rw,"""INSERT INTO audit_runs(workspace_id,release_id,kind,task_key,data_cutoff,settings,rules_run)
      SELECT workspace_id,release_id,kind,gen_random_uuid()::text,data_cutoff,settings,rules_run FROM audit_runs WHERE id=%s RETURNING id""",rec['audit'])
    finding=one(rw,"""INSERT INTO findings (audit_run_id,issue_id,rule_version,lost,recoverable,data_quality,evidence,action,safety_policy,candidate_level,action_level,policy_reasons)
      SELECT %s,issue_id,rule_version,lost,recoverable,data_quality,evidence,action,safety_policy,candidate_level,'inspect_only',ARRAY['synthetic_policy_downgrade'] FROM findings WHERE id=%s RETURNING id""",audit,rec['finding'])
    explanation=one(rw,"INSERT INTO explanations(finding_id,source,text,release_id) VALUES (%s,'template','Synthetic inspected evidence',%s) RETURNING id",finding,rec['release'])
    rw.execute("INSERT INTO recommendation_events(recommendation_id,type,finding_id,explanation_id) VALUES (%s,'seen_again',%s,%s)",(rec['rec'],finding,explanation))
    assert set(read(flow)['allowed_actions'])=={'check','postpone'}
    assert post(flow,'/manual-execution',body(flow)).status_code==409
    r=post(flow,'/decisions',body(flow,action='check'))
    assert r.status_code==200,r.text
    d=read(flow)
    assert d['execution_mode']=='none' and d['verification_status']=='not_required'
    assert d['latest_measurement'] is None


def test_passport_cannot_mutate_evidence_and_invalid_ids(flow):
    before=one(flow['rw'],'SELECT evidence FROM findings WHERE id=%s',flow['ids']['rec_a1']['finding'])
    assert post(flow,'/manual-execution',{**body(flow),'evidence':{}}).status_code==400
    assert one(flow['rw'],'SELECT evidence FROM findings WHERE id=%s',flow['ids']['rec_a1']['finding'])==before
    for recid in ['rec_0','rec_9223372036854775808','random']:
        assert flow['api'].get(flow['url'].rsplit('/',1)[0]+'/'+recid,headers=flow['headers']).status_code==404
