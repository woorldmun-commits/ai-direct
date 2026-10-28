"""Run existing frontend gates; the full backend and restore have a separate receipt."""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('audit', ROOT / 'docs/skills-audit-2026-10-27/checks.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
audit.OUT = OUT
(OUT / 'source-before-checks.json').write_text(json.dumps(audit.snapshot(), indent=2), encoding='utf-8')
audit.run('ruff', [audit.PYTHON, '-m', 'ruff', 'check', 'backend', 'deploy'])
web = ROOT / 'designe 1.0'
audit.run('lint', ['npm.cmd', 'run', 'lint'], cwd=web)
for name in ['check-auth-proxy', 'check-workspace-proxy', 'check-direct-proxy', 'check-insights',
             'check-billing', 'check-site', 'check-ix', 'check-remediation', 'check-deep-audit',
             'check-model', 'check-pilot', 'check-subscription', 'check-intelligence']:
    audit.run(name, ['node', '--experimental-strip-types', f'scripts/{name}.mjs'], cwd=web)
if audit.run('build', ['npm.cmd', 'run', 'build'], cwd=web,
             env=dict(os.environ, NEXT_TELEMETRY_DISABLED='1')) == 0:
    audit.run('headers', ['npm.cmd', 'run', 'test:headers'], cwd=web,
              env=dict(os.environ, REQUIRE_BROWSER='1', NODE_PATH='C:/Users/woorl/.local/share/agent-tools/gstack/node_modules'))
(OUT / 'source-after-checks.json').write_text(json.dumps(audit.snapshot(), indent=2), encoding='utf-8')
assert all(row['exit_code'] == 0 for row in audit.RECEIPT), 'inspect checks.json'
