"""Loopback-only synthetic QA server. Never consumes an external database or advertising API."""
import os
import sys
import json
import tempfile
from pathlib import Path

if os.environ.get('TEST_DATABASE_URL') or os.environ.get('DATABASE_URL'):
    raise RuntimeError('External database configuration refused')
root=Path(__file__).resolve().parents[1]
backend=root.parent/'backend'
sys.path[:0]=[str(backend/'tests'),str(backend)]
import pgserver
import uvicorn
server=pgserver.get_server(Path(tempfile.mkdtemp(prefix='inrou-pricing-browser-')),cleanup_mode='stop')
os.environ['TEST_DATABASE_URL']=server.get_uri()
from conftest import db as database_fixture
from test_api_support import session,settings,user
from test_schema import new_workspace
from app.api import create_app

database=database_fixture.__wrapped__()
with database('app_system') as conn:
    owner=user(conn)
    agency=new_workspace(conn,'Синтетическое агентство · QA',user=owner)
    conn.execute("INSERT INTO subscriptions(workspace_id,plan,status,price,current_period_start,current_period_end) VALUES(%s,'business_plus','active',9990,now()-interval '1 second',now()+interval '30 days')",(agency,))
    pending_user=user(conn)
    pending=new_workspace(conn,'Пробный кабинет · QA',user=pending_user)
    conn.execute('SELECT start_registration_trial(%s,%s)',(pending_user,pending))
    fixture={'synthetic':True,'agency':f'ws_{agency}','pending':f'ws_{pending}',
        'tokens':{'agency':session(conn,owner),'pending':session(conn,pending_user)}}
runtime=root/'artifacts/.runtime/pricing-upgrade'
runtime.mkdir(parents=True,exist_ok=True)
(runtime/'fixture.json').write_text(json.dumps(fixture),encoding='utf-8')
print('Synthetic pricing fixture ready: 127.0.0.1:3129. No external APIs or live payments.',flush=True)
uvicorn.run(create_app(settings(database,allowed_origins=frozenset({'http://127.0.0.1:3140','http://127.0.0.1:3141'}))),
    host='127.0.0.1',port=3129,access_log=False)
