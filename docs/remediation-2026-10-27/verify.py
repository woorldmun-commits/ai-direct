"""Run requested backend checks on a fresh local PostgreSQL and save their receipt."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PYTHON = ROOT / 'backend/.venv/Scripts/python.exe'
PG = ROOT / 'backend/.venv/Lib/site-packages/pgserver/pginstall/bin'


def main():
    label, *tests = sys.argv[1:]
    cluster = Path(tempfile.mkdtemp(prefix='inrou-remediation-pg-'))
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    def command(args, log):
        with (OUT / log).open('w', encoding='utf-8') as output:
            return subprocess.run([str(a) for a in args], stdout=output, stderr=subprocess.STDOUT,
                                  timeout=1800, cwd=ROOT / 'backend',
                                  env=dict(os.environ, PYTHONUTF8='1', TEST_DATABASE_URL=f'postgresql://postgres@127.0.0.1:{port}/postgres')).returncode
    assert command([PG / 'initdb.exe', '-D', cluster, '-A', 'trust', '-U', 'postgres', '--encoding=UTF8', '--no-locale'], label+'-pg-init.log') == 0
    assert command([PG / 'pg_ctl.exe', '-D', cluster, '-w', '-t', '60', '-l', cluster / 'server.log', '-o', f'-h 127.0.0.1 -p {port}', 'start'], label+'-pg-start.log') == 0
    started = datetime.now(timezone.utc).isoformat()
    try:
        code = command([PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *tests], label+'.log')
        if code == 0 and label in ('backend-full', 'restore-smoke'):
            recovery_started = time.monotonic()
            admin = f'postgresql://postgres@127.0.0.1:{port}/postgres'
            original = f'postgresql://postgres@127.0.0.1:{port}/audit_source'
            restored = f'postgresql://postgres@127.0.0.1:{port}/audit_restore'
            # Negative schema tests intentionally leave broken fixtures; recovery uses a clean valid chain.
            assert command([PG/'createdb.exe', '-h', '127.0.0.1', '-p', port, '-U', 'postgres', '-O', 'app_migrator', 'audit_source'], 'backup-source-create.log') == 0
            with psycopg.connect(original.replace('postgres@', 'app_migrator@'), autocommit=True) as conn:
                conn.execute((ROOT/'backend/db/schema.sql').read_text(encoding='utf-8'))
            sys.path.insert(0, str(ROOT/'backend'))
            sys.path.insert(0, str(ROOT/'backend/tests'))
            from test_schema import chain
            with psycopg.connect(original.replace('postgres@', 'app_system@'), autocommit=True) as conn:
                chain.__wrapped__(conn)
            backup = cluster / 'synthetic.backup'
            assert command([PG/'pg_dump.exe', '-d', original, '-Fc', '-f', backup], 'backup.log') == 0
            assert command([PG/'createdb.exe', '-h', '127.0.0.1', '-p', port, '-U', 'postgres', '-O', 'app_migrator', 'audit_restore'], 'restore-create.log') == 0
            assert command([PG/'pg_restore.exe', '-d', restored, backup], 'restore.log') == 0
            def counts(uri):
                with psycopg.connect(uri) as conn:
                    return {table: conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                            for table in ('workspaces', 'audit_runs', 'recommendations', 'intelligence_runs')}
            source_counts, restored_counts = counts(original), counts(restored)
            assert source_counts == restored_counts
            with psycopg.connect(restored.replace('postgres@', 'app_rw@')) as conn:
                assert conn.execute('SELECT count(*) FROM audit_runs').fetchone()[0] == 0
            (OUT/'recovery-receipt.json').write_text(json.dumps({'scope':'isolated_synthetic_cluster_only',
                'elapsed_seconds':time.monotonic()-recovery_started, 'fixture':'clean_valid_evidence_chain', 'source_counts':source_counts,
                'restored_counts':restored_counts, 'unscoped_app_rw_audits':0}, indent=2), encoding='utf-8')
    finally:
        stopped = command([PG / 'pg_ctl.exe', '-D', cluster, '-w', 'stop'], label+'-pg-stop.log')
    (OUT / (label+'-receipt.json')).write_text(json.dumps({'args': tests, 'started_utc': started,
        'finished_utc': datetime.now(timezone.utc).isoformat(), 'exit_code': code, 'pg_stop_exit_code': stopped}, indent=2), encoding='utf-8')
    print(label, 'exit', code)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
