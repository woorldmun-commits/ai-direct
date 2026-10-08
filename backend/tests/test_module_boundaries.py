"""Границы модулей: rules/ и audit/ не знают об AI-слое и LLM SDK; реестр метрик чист (CLAUDE.md проекта)."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).parents[1] / "app"
BACKEND = APP.parent
FORBIDDEN = ("app.ai", "app.intelligence.llm", "app.intelligence.agents", "anthropic", "openai", "google.genai",
             "litellm")
REGISTRY_FORBIDDEN = FORBIDDEN + ("psycopg", "os", "httpx", "requests", "urllib", "socket")


def package_of(path: Path) -> list[str]:
    """Пакет файла: app/audit/x.py → ["app", "audit"]; app/rules/__init__.py → ["app", "rules"]."""
    return list(path.relative_to(BACKEND).parent.parts)


def imports_in(source: str, package: list[str]) -> list[str]:
    """Все импортируемые имена: относительные приведены к абсолютным, importlib / __import__ с литералом учтены."""
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = ".".join(package[:len(package) - node.level + 1] + ([node.module] if node.module else []))
            names.append(base)
            names += [f"{base}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Call):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if called in ("import_module", "__import__") and node.args and isinstance(node.args[0], ast.Constant):
                names.append(str(node.args[0].value))
    return names


def forbidden_in(source: str, package: list[str], forbidden=FORBIDDEN) -> list[str]:
    return [n for n in imports_in(source, package) if any(n == m or n.startswith(m + ".") for m in forbidden)]


def file_hits(path: Path, forbidden=FORBIDDEN) -> list[str]:
    return forbidden_in(path.read_text(encoding="utf-8"), package_of(path), forbidden)


@pytest.mark.parametrize("package", ["rules", "audit"])
def test_package_does_not_import_ai_or_llm(package):
    files = sorted((APP / package).rglob("*.py"))
    assert files
    for path in files:
        assert not file_hits(path), (path.name, file_hits(path))


@pytest.mark.parametrize("source", [
    "from app.intelligence.llm import client\n",
    "import anthropic\n",
    "from app.intelligence import llm\n",                      # подмодуль через имя из пакета
    "import importlib\nimportlib.import_module('openai')\n",
    "__import__('google.genai')\n",
    "import litellm\n",
    "from ..ai import x\n",                                    # относительные импорты из app/audit
    "from .. import ai\n",
    "from ..intelligence.llm import y\n",
])
def test_the_check_catches_violations(source):
    assert forbidden_in(source, ["app", "audit"])


def test_the_check_has_no_false_positive_on_local_imports():
    assert not forbidden_in("from . import policy\nfrom ..rules.domain import Finding\nimport os\n", ["app", "audit"])


def test_metric_registry_is_pure():
    files = sorted((APP / "intelligence").rglob("*.py"))
    assert files
    for path in files:
        assert not file_hits(path, REGISTRY_FORBIDDEN), (path.name, file_hits(path, REGISTRY_FORBIDDEN))


@pytest.mark.parametrize("source", ["import requests\n", "import urllib.request\n", "import socket\n"])
def test_registry_check_catches_network_modules(source):
    assert forbidden_in(source, ["app", "intelligence"], REGISTRY_FORBIDDEN)


def test_importing_rules_and_audit_loads_no_llm_sdk():
    code = ("import sys, app.rules, app.audit.policy, app.audit.templates, app.audit.persist, app.audit.measurement\n"
            "bad = [m for m in sys.modules if m.split('.')[0] in ('anthropic', 'openai', 'litellm') "
            "or m == 'app.ai' or m.startswith(('app.ai.', 'app.intelligence.llm'))]\n"
            "print(bad)\nsys.exit(1 if bad else 0)\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
