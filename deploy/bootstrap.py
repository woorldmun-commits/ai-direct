"""Provision dedicated database roles and run the project's existing migration runner. No credentials are printed."""
import os

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


def provision(env):
    admin = env['BOOTSTRAP_DATABASE_URL']
    roles = ('app_migrator','app_rw','app_token','app_system','app_deleter')
    print('Database: connecting for startup checks.', flush=True)
    with psycopg.connect(admin, autocommit=True, connect_timeout=10) as conn:
        # Only one bootstrapper may initialize a shared database at a time.
        conn.execute('SELECT pg_advisory_lock(735891321)')
        try:
            database = conn.info.dbname
            for role in roles:
                password = env[role.upper()+'_PASSWORD']
                if len(password) < 32:
                    raise ValueError(f'{role}: password must have at least 32 characters')
                row = conn.execute('SELECT rolsuper,rolbypassrls,rolcanlogin FROM pg_roles WHERE rolname=%s', (role,)).fetchone()
                if row is None:
                    conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS').format(
                        sql.Identifier(role),sql.Literal(password)))
                elif row != (False,False,True):
                    raise ValueError(f'{role}: unsafe existing role; review manually')
            conn.execute('GRANT app_rw TO app_token,app_system')
            conn.execute(sql.SQL('GRANT CREATE ON DATABASE {} TO app_migrator').format(sql.Identifier(database)))
            # Only the schema owner can reliably revoke the legacy PUBLIC create privilege.
            conn.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
            conn.execute('GRANT CREATE,USAGE ON SCHEMA public TO app_migrator')
            conn.execute('GRANT USAGE ON SCHEMA public TO app_rw,app_token,app_system,app_deleter')
            if conn.execute("SELECT has_schema_privilege('app_rw','public','CREATE')").fetchone()[0]:
                raise ValueError('app_rw must not have schema CREATE privileges')
            urls = {role:make_conninfo(admin,user=role,password=env[role.upper()+'_PASSWORD']) for role in roles}
            from migrations import migrate
            print('Database: checking schema migrations.', flush=True)
            with psycopg.connect(urls['app_migrator'], connect_timeout=10) as migration_conn:
                migrate(migration_conn)
        finally:
            conn.execute('SELECT pg_advisory_unlock(735891321)')
    print('Database: startup checks complete.', flush=True)
    return {'API_DATABASE_URL':urls['app_rw'], 'WORKER_DATABASE_URL':urls['app_token'],
            'WORKER_QUEUE_DATABASE_URL':urls['app_system']}


if __name__ == '__main__':
    provision(os.environ)
    print('Database roles and migrations are ready.')
