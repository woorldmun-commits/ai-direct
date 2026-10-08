"""Границы модулей: rules/ и audit/ не знают об AI-слое и LLM SDK; реестр метрик чист (CLAUDE.md проекта)."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).parents[1] / "app"
FORBIDDEN = ("app.ai", "app.intelligence.llm", "app.intelligence.agents", "anthropic", "openai")


def imports(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
            names += [f"{node.module}.{a.name}" for a in node.names if node.module]
    return names


@pytest.mark.parametrize("package", ["rules", "audit"])
def test_package_does_not_import_ai_or_llm(package):
    files = sorted((APP / package).glob("*.py"))
    assert files
    for path in files:
        for name in imports(path):
            assert not any(name == m or name.startswith(m + ".") for m in FORBIDDEN), (path.name, name)


def test_the_check_would_catch_a_violation(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from app.intelligence.llm import client\nimport anthropic\n", encoding="utf-8")
    assert [n for n in imports(bad) if any(n == m or n.startswith(m + ".") for m in FORBIDDEN)]


def test_metric_registry_is_pure():
    for path in (APP / "intelligence").rglob("*.py"):
        for name in imports(path):
            assert not any(name == m or name.startswith(m + ".") for m in FORBIDDEN + ("psycopg", "os", "httpx")), (
                path.name, name)
