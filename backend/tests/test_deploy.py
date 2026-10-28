import importlib.util
from pathlib import Path
import secrets

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from conftest import _admin_uri


def test_bootstrap_creates_a_migrated_database_with_separate_roles():
    path=Path(__file__).parents[2]/'deploy/bootstrap.py'
    spec=importlib.util.spec_from_file_location('launch_bootstrap',path)
    bootstrap=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    database='inrou_bootstrap_test_'+secrets.token_hex(5)
    admin=_admin_uri()
    with psycopg.connect(admin,autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    try:
        with psycopg.connect(make_conninfo(admin,dbname=database),autocommit=True) as owner:
            owner.execute('GRANT CREATE ON SCHEMA public TO PUBLIC')
        env={role+'_PASSWORD':'synthetic-test-password-1234567890' for role in
             ('APP_MIGRATOR','APP_RW','APP_TOKEN','APP_SYSTEM','APP_DELETER')}
        env['BOOTSTRAP_DATABASE_URL']=make_conninfo(admin,dbname=database)
        urls=bootstrap.provision(env)
        # Second start applies no destructive reset or duplicated migrations.
        assert urls==bootstrap.provision(env)
        with psycopg.connect(urls['RETENTION_DATABASE_URL'],autocommit=True) as conn:
            assert conn.execute('SELECT current_user').fetchone()[0]=='app_deleter'
            assert conn.execute("SELECT has_function_privilege(current_user,'purge_personal_data(timestamptz)','EXECUTE')").fetchone()[0]
            assert not conn.execute("SELECT has_table_privilege(current_user,'sessions','SELECT')").fetchone()[0]
        with psycopg.connect(urls['API_DATABASE_URL']) as conn:
            assert conn.execute('SELECT current_user').fetchone()[0]=='app_rw'
            assert conn.execute("SELECT count(*) FROM sync_runs").fetchone()[0]==0
            assert conn.execute("SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()[0]
            assert not conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0]
    finally:
        with psycopg.connect(admin,autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))


def test_deployment_processes_receive_only_their_credentials():
    path=Path(__file__).parents[2]/'deploy/serve.py'
    spec=importlib.util.spec_from_file_location('launch_serve',path)
    serve=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    env={key:'synthetic-secret' for key in ('BOOTSTRAP_DATABASE_URL','APP_RW_PASSWORD','API_DATABASE_URL',
         'WORKER_DATABASE_URL','WORKER_QUEUE_DATABASE_URL','TOKEN_ENCRYPTION_KEY_1','YANDEX_API_CLIENT_SECRET',
         'INROU_SMTP_PASSWORD','INROU_MAIL_API_KEY','RENDER_API_KEY','RETENTION_DATABASE_URL','APP_DELETER_PASSWORD',
         'YOOKASSA_SECRET_KEY','YANDEX_LOGIN_CLIENT_SECRET','TOKEN_ENCRYPTION_KEY_VERSION','TOKEN_ENCRYPTION_KEY_2',
         'PILOT_WORKSPACE_IDS','PILOT_OPEN_ACCESS','PILOT_ACCESS_UNTIL','DIRECT_PLACEMENTS_REPORT')}
    env.update(PATH='test-path',NODE_ENV='production',INROU_API_URL='http://127.0.0.1:8081',
               API_PROXY_HMAC_KEY='synthetic-shared-hmac',INROU_APP_ORIGIN='https://example.test')
    web=serve.child_environment(env,'web')
    assert set(web)=={'PATH','NODE_ENV','INROU_API_URL','API_PROXY_HMAC_KEY','INROU_APP_ORIGIN'}
    api_env=serve.child_environment(env,'api')
    assert api_env['API_DATABASE_URL']=='synthetic-secret'
    assert 'WORKER_DATABASE_URL' not in api_env and 'WORKER_QUEUE_DATABASE_URL' not in api_env
    worker=serve.child_environment(env,'worker')
    assert worker['WORKER_DATABASE_URL']=='synthetic-secret' and 'API_DATABASE_URL' not in worker
    assert {'TOKEN_ENCRYPTION_KEY_1','TOKEN_ENCRYPTION_KEY_2','TOKEN_ENCRYPTION_KEY_VERSION',
            'PILOT_WORKSPACE_IDS','PILOT_OPEN_ACCESS','PILOT_ACCESS_UNTIL','DIRECT_PLACEMENTS_REPORT'} <= worker.keys()
    assert not {'YOOKASSA_SECRET_KEY','YANDEX_LOGIN_CLIENT_SECRET','INROU_SMTP_PASSWORD',
                'INROU_MAIL_API_KEY','RENDER_API_KEY'} & worker.keys()
    mail=serve.child_environment(env,'auth_mail')
    assert mail['WORKER_QUEUE_DATABASE_URL']=='synthetic-secret'
    assert mail['INROU_SMTP_PASSWORD']=='synthetic-secret'
    assert not {'YOOKASSA_SECRET_KEY','YANDEX_LOGIN_CLIENT_SECRET','TOKEN_ENCRYPTION_KEY_1',
                'API_DATABASE_URL','WORKER_DATABASE_URL','RENDER_API_KEY'} & mail.keys()
    retention=serve.child_environment(env,'retention')
    assert retention=={'PATH':'test-path','RETENTION_DATABASE_URL':'synthetic-secret'}
    for child in (web,api_env,worker):
        assert 'BOOTSTRAP_DATABASE_URL' not in child and 'APP_RW_PASSWORD' not in child
        assert 'RETENTION_DATABASE_URL' not in child and 'APP_DELETER_PASSWORD' not in child


@pytest.mark.parametrize('enabled', ['1','0'])
def test_retention_launch_is_independent_of_ingestion(monkeypatch, enabled):
    path=Path(__file__).parents[2]/'deploy/serve.py'
    spec=importlib.util.spec_from_file_location('retention_serve',path)
    serve=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    monkeypatch.setattr(serve.os,'environ',{'INROU_APP_ORIGIN':'https://example.test',
                        'RETENTION_ENABLED':enabled,'RETENTION_DATABASE_URL':'synthetic-deleter'})
    launched=[]
    class Child:
        def poll(self): return 0
        def wait(self, timeout): return 0
    def launch(command,**kwargs):
        launched.append((command,kwargs['env']))
        return Child()
    monkeypatch.setattr(serve.subprocess,'Popen',launch)
    monkeypatch.setattr(serve.signal,'signal',lambda *args: None)
    with pytest.raises(SystemExit,match='A service exited'):
        serve.main()
    if enabled=='1':
        assert launched[0][0][-1]=='app.worker.retention_runner'
        assert launched[0][1]=={'RETENTION_DATABASE_URL':'synthetic-deleter'}
    assert len(launched)==(2 if enabled=='1' else 1)


@pytest.mark.parametrize('enabled', ['1','true','yes','false'])
def test_auth_mail_launch_is_independent_of_direct_worker(monkeypatch, enabled):
    path=Path(__file__).parents[2]/'deploy/serve.py'
    spec=importlib.util.spec_from_file_location('mail_serve',path)
    serve=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    monkeypatch.setattr(serve.os,'environ',{'INROU_APP_ORIGIN':'https://example.test',
                        'INROU_EMAIL_ENABLED':enabled,'WORKER_QUEUE_DATABASE_URL':'synthetic-system'})
    launched=[]
    class Child:
        def poll(self): return 0
        def wait(self, timeout): return 0
    def launch(command,**kwargs):
        launched.append((command,kwargs['env']))
        return Child()
    monkeypatch.setattr(serve.subprocess,'Popen',launch)
    monkeypatch.setattr(serve.signal,'signal',lambda *args: None)
    with pytest.raises(SystemExit,match='A service exited'):
        serve.main()
    if enabled!='false':
        assert launched[0][0][-1]=='app.worker.auth_mail_runner'
        assert launched[0][1]['WORKER_QUEUE_DATABASE_URL']=='synthetic-system'
    assert len(launched)==(1 if enabled=='false' else 2)
