"""Границы LLM-шлюза: rules/ и audit/ не импортируют intelligence.llm; сам шлюз не ходит в БД и правила;
Chief Analyst, Privacy Guard и Judge получают шлюз инъекцией и сеть не загружают."""

import subprocess
import sys

import pytest

from test_module_boundaries import APP, BACKEND, file_hits

LLM = ("app.intelligence.llm",)


@pytest.mark.parametrize("package", ["rules", "audit"])
def test_rules_and_audit_do_not_import_llm_gateway(package):
    files = sorted((APP / package).rglob("*.py"))
    assert files
    assert not [p.name for p in files if file_hits(p, LLM)]


def test_gateway_does_not_touch_db_rules_or_audit():
    files = sorted((APP / "intelligence" / "llm").rglob("*.py"))
    assert files
    banned = ("psycopg", "app.db", "app.rules", "app.audit", "app.sync", "app.worker", "app.api")
    assert not [(p.name, file_hits(p, banned)) for p in files if file_hits(p, banned)]


@pytest.mark.parametrize("module", ["privacy.py", "judge.py", "agents/chief.py"])
def test_guard_judge_and_chief_do_not_import_gateway(module):
    assert not file_hits(APP / "intelligence" / module, LLM + ("httpx", "os"))


def test_importing_chief_loads_no_network_modules():
    code = ("import sys, app.intelligence.agents.chief, app.intelligence.judge, app.intelligence.privacy\n"
            "bad = [m for m in sys.modules if m.split('.')[0] in ('httpx', 'psycopg', 'requests') "
            "or m.startswith('app.intelligence.llm')]\nprint(bad)\nsys.exit(1 if bad else 0)\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
