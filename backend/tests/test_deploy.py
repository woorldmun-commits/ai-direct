import importlib.util
from pathlib import Path
import secrets

import psycopg
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
        env={role+'_PASSWORD':'synthetic-test-password-1234567890' for role in
             ('APP_MIGRATOR','APP_RW','APP_TOKEN','APP_SYSTEM','APP_DELETER')}
        env['BOOTSTRAP_DATABASE_URL']=make_conninfo(admin,dbname=database)
        urls=bootstrap.provision(env)
        # Second start applies no destructive reset or duplicated migrations.
        assert urls==bootstrap.provision(env)
        with psycopg.connect(urls['API_DATABASE_URL']) as conn:
            assert conn.execute('SELECT current_user').fetchone()[0]=='app_rw'
            assert conn.execute("SELECT count(*) FROM sync_runs").fetchone()[0]==0
            assert conn.execute("SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()[0]
    finally:
        with psycopg.connect(admin,autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
