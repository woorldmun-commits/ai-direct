"""Audit receipt; test PostgreSQL is isolated from the existing local cluster."""
import hashlib
import json
import os
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PYTHON = ROOT / "backend/.venv/Scripts/python.exe"
PG = ROOT / "backend/.venv/Lib/site-packages/pgserver/pginstall/bin"
RECEIPT = []


def snapshot():
    folders = ["backend/app", "backend/tests", "backend/migrations", "backend/db", "deploy", "designe 1.0/app", "designe 1.0/components", "designe 1.0/lib", "designe 1.0/scripts", ".github/workflows"]
    files = [p for folder in folders for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".sql", ".ts", ".tsx", ".css", ".mjs", ".yml"}]
    files += [ROOT / p for p in ["Dockerfile", "render.yaml", "designe 1.0/package.json", "designe 1.0/package-lock.json", "designe 1.0/next.config.ts", "designe 1.0/proxy.ts", "backend/requirements.lock.txt", "backend/requirements-dev.txt"]]
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.exists()}


def run(name, args, cwd=ROOT, env=None, timeout=1200):
    started = datetime.now(timezone.utc).isoformat()
    with (OUT / f"{name}.log").open("w", encoding="utf-8") as output:
        try:
            result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    RECEIPT.append({"name": name, "args": [str(a) for a in args], "cwd": str(cwd), "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "exit_code": code, "log_sha256": hashlib.sha256((OUT / f"{name}.log").read_bytes()).hexdigest()})
    (OUT / "checks.json").write_text(json.dumps(RECEIPT, indent=2), encoding="utf-8")
    print(f"{name}: exit {code}", flush=True)
    return code


def main():
    before = snapshot()
    (OUT / "source-before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    run("ruff", [PYTHON, "-m", "ruff", "check", "backend", "deploy"])
    data = Path(tempfile.mkdtemp(prefix="inrou-audit-pg-"))
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    if run("pg-init", [PG / "initdb.exe", "-D", data, "-A", "trust", "-U", "postgres", "--encoding=UTF8", "--no-locale"], timeout=120) == 0:
        started = run("pg-start", [PG / "pg_ctl.exe", "-D", data, "-l", data / "audit.log", "-w", "-t", "60", "-o", f"-h 127.0.0.1 -p {port}", "start"], timeout=90) == 0
        try:
            if started:
                test_env = dict(os.environ, TEST_DATABASE_URL=f"postgresql://postgres@127.0.0.1:{port}/postgres", PYTHONUTF8="1")
                run("pytest", [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT / "backend", env=test_env)
        finally:
            if started:
                run("pg-stop", [PG / "pg_ctl.exe", "-D", data, "-w", "stop"], timeout=90)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    web = ROOT / "designe 1.0"
    run("lint", [npm, "run", "lint"], cwd=web)
    scripts = ["check-auth-proxy", "check-workspace-proxy", "check-direct-proxy", "check-insights", "check-billing", "check-site", "check-ix", "check-remediation", "check-deep-audit", "check-model", "check-pilot", "check-subscription"]
    for script in scripts:
        run(script, ["node", "--experimental-strip-types", f"scripts/{script}.mjs"], cwd=web)
    run("npm-audit-production", [npm, "audit", "--audit-level=high", "--package-lock-only", "--omit=dev"], cwd=web)
    run("npm-audit-all", [npm, "audit", "--audit-level=high", "--package-lock-only"], cwd=web)
    run("pip-audit", [PYTHON, "-m", "pip_audit", "-r", "backend/requirements.lock.txt"])
    built = run("build", [npm, "run", "build"], cwd=web, env=dict(os.environ, NEXT_TELEMETRY_DISABLED="1")) == 0
    if built:
        run("headers", [npm, "run", "test:headers"], cwd=web, env=dict(os.environ, REQUIRE_BROWSER="1"))
    after = snapshot()
    (OUT / "source-after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    delta = [p for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
    (OUT / "source-delta.json").write_text(json.dumps(delta, indent=2), encoding="utf-8")
    assert RECEIPT and all((OUT / f"{r['name']}.log").exists() for r in RECEIPT)
    print(f"Source files {len(before)}; changed {len(delta)}", flush=True)


if __name__ == "__main__":
    main()
