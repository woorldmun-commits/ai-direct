"""Local test server: real FastAPI + RLS on a disposable PostgreSQL, synthetic accounts only."""
from pathlib import Path
import sys, os, tempfile, json
from datetime import timedelta

root = Path(__file__).resolve().parents[1]
backend = root.parent / 'backend'
if os.environ.get('TEST_DATABASE_URL') or os.environ.get('DATABASE_URL'):
    raise RuntimeError('External database configuration present; fixture refused')
runtime = root / 'artifacts/.runtime'
runtime.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = tempfile.mkdtemp(prefix='pilot-postgres-', dir=runtime)
sys.path[:0] = [str(backend/'tests'), str(backend)]
import uvicorn
from conftest import db as database_fixture
from test_api_support import world, session, settings, user
from test_schema import new_workspace
from app.api import create_app

database = database_fixture.__wrapped__()
with database('app_system') as conn:
    ids = world.__wrapped__(conn)
    conn.execute("INSERT INTO subscriptions(workspace_id,plan,status,price,current_period_start,current_period_end) VALUES(%s,'start','active',1990,now()-interval '1 day',now()+interval '1 month')",(ids['a1'],))
    empty_user = user(conn)
    empty_ws = new_workspace(conn, 'Пустой кабинет', user=empty_user)
    tokens = {name: session(conn, ids[name]) for name in ('owner', 'viewer', 'owner_b', 'member')}
    tokens['empty'] = session(conn, empty_user)
    tokens['expired'] = session(conn, ids['owner'], expires_in=timedelta(seconds=-1))
    tokens['revoked'] = session(conn, ids['owner'], revoked=True)
(runtime/'fixture.json').write_text(json.dumps({'tokens':tokens,'workspaces':{k:f'ws_{ids[k]}' for k in ('a1','a2','b1')},'empty_workspace':f'ws_{empty_ws}','recommendation':f"rec_{ids['rec_a1']['rec']}",'account':f"acc_{ids['rec_a1']['account']}"}),encoding='utf-8')
print('Synthetic local fixture ready on 127.0.0.1:3121; session values are not printed.',flush=True)
uvicorn.run(create_app(settings(database,allowed_origins=frozenset({'http://127.0.0.1:3130','https://app.example.test'}))), host='127.0.0.1', port=3121, access_log=False)
