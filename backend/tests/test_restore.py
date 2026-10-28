"""A backup must restore populated evidence, not just an empty schema."""
import os
import shutil
import subprocess
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from conftest import _admin_uri, _with_user
from migrations import migrate
from test_migrations import _create_db
from test_schema import chain, value


def test_value_helpers_do_not_depend_on_caller_search_path(rw):
    with rw.transaction(force_rollback=True):
        rw.execute("SET LOCAL search_path = ''")
        assert rw.execute('SELECT public.value_is_valid(%s)', (Jsonb(value()),)).fetchone()[0]
        assert rw.execute('SELECT public.evidence_is_valid(%s)', (Jsonb({'cost': value()}),)).fetchone()[0]
        assert rw.execute('SELECT public.values_are_valid(%s)', (Jsonb([value()]),)).fetchone()[0]
        assert not rw.execute('SELECT public.value_is_valid(%s)', (Jsonb(value(amount='bad')),)).fetchone()[0]


def test_populated_dump_restore_preserves_evidence_and_rls(db, tmp_path):
    admin = _admin_uri()
    source, target = f'ai_direct_backup_{os.getpid()}', f'ai_direct_restore_{os.getpid()}'
    for name in (source, target):
        _create_db(admin, name)
    with psycopg.connect(_with_user(admin, 'app_migrator', source)) as conn:
        migrate(conn)
    with psycopg.connect(_with_user(admin, 'app_system', source), autocommit=True) as conn:
        ids = chain.__wrapped__(conn)
    bundled = Path(__file__).parents[1] / '.venv/Lib/site-packages/pgserver/pginstall/bin'
    def binary(name):
        local = bundled / (name + '.exe')
        return str(local) if local.exists() else shutil.which(name) or name
    backup = tmp_path / 'evidence.backup'
    for command in ([binary('pg_dump'), '-d', _with_user(admin, 'postgres', source), '-Fc', '-f', str(backup)],
                    [binary('pg_restore'), '--exit-on-error', '-d', _with_user(admin, 'postgres', target), str(backup)]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr
    with psycopg.connect(_with_user(admin, 'app_system', target), autocommit=True) as conn:
        for table, key in [('findings', 'finding'), ('explanations', 'explanation'), ('recommendations', 'rec')]:
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE id=%s', (ids[key],)).fetchone()[0] == 1
    with psycopg.connect(_with_user(admin, 'app_rw', target), autocommit=True) as conn:
        assert conn.execute('SELECT count(*) FROM findings').fetchone()[0] == 0
