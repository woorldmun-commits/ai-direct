"""Reuse the isolated PostgreSQL harness and keep new receipts in this directory."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('isolated', ROOT / 'docs/remediation-2026-10-27/verify.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.OUT = Path(__file__).resolve().parent
module.main()
