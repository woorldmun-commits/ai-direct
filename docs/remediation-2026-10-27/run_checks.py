"""Reuse the existing audit receipt writer for the remediation checks."""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('audit_checks', ROOT/'docs/skills-audit-2026-10-27/checks.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
audit.OUT = OUT
before = audit.snapshot()
(OUT/'source-before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
audit.run('ruff',[audit.PYTHON,'-m','ruff','check','backend','deploy'])
audit.run('backend-harness',[audit.PYTHON,OUT/'verify.py','backend-full'])
web = ROOT/'designe 1.0'
audit.run('lint',['npm.cmd','run','lint'],cwd=web)
for name in ['check-auth-proxy','check-workspace-proxy','check-direct-proxy','check-insights','check-billing','check-site','check-ix','check-remediation','check-deep-audit','check-model','check-pilot','check-subscription']:
    audit.run(name,['node','--experimental-strip-types',f'scripts/{name}.mjs'],cwd=web)
built = audit.run('build',['npm.cmd','run','build'],cwd=web,env=dict(os.environ,NEXT_TELEMETRY_DISABLED='1')) == 0
if built:
    audit.run('headers',['npm.cmd','run','test:headers'],cwd=web,env=dict(os.environ,REQUIRE_BROWSER='1',NODE_PATH='C:/Users/woorl/.local/share/agent-tools/gstack/node_modules'))
after = audit.snapshot()
(OUT/'source-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
delta=[p for p in sorted(before.keys()|after.keys()) if before.get(p)!=after.get(p)]
(OUT/'source-delta.json').write_text(json.dumps(delta,indent=2),encoding='utf-8')
print('Source files:',len(before),'changed:',len(delta),flush=True)
