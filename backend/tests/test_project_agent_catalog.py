"""Catalog checks for IDE profiles; never asserts that they ran as autonomous agents."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = ROOT / ".claude" / "agents" / "inrou"
DOCS = ROOT / "docs" / "project-agents"

PROFILES = {
    "backend-metrics", "data-contract-qa", "frontend", "integrations-data",
    "legal", "product", "qa", "release-ops", "runtime-reliability",
    "security", "seo", "supervisor", "finance-audit", "ai-safety",
}
READ_ONLY = {
    "data-contract-qa", "runtime-reliability", "security", "supervisor",
    "finance-audit", "ai-safety",
}
DOC_NAME = {
    "frontend": "design-frontend",
    "integrations-data": "integrations-data",
    "legal": "legal-readiness",
    "product": "product-economics",
    "security": "security-privacy",
    "supervisor": "supervisor",
    "seo": "seo",
    "qa": "qa",
    "release-ops": "release-ops",
    "backend-metrics": "backend-metrics",
    "data-contract-qa": "data-contract-qa",
    "runtime-reliability": "runtime-reliability",
    "finance-audit": "finance-audit",
    "ai-safety": "ai-safety",
}


def test_all_ide_profiles_present_with_matching_name_and_document():
    actual = {path.stem for path in AGENT_DIR.glob("*.md")}
    assert actual == PROFILES
    for code in sorted(PROFILES):
        text = (AGENT_DIR / (code + ".md")).read_text(encoding="utf-8")
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert re.search(r"(?m)^name: inrou-" + re.escape(code) + r"$", frontmatter)
        assert re.search(r"(?m)^tools: ", frontmatter)
        assert (DOCS / (DOC_NAME[code] + ".md")).is_file()


def test_read_only_profiles_cannot_write_from_manifest():
    for code in READ_ONLY:
        text = (AGENT_DIR / (code + ".md")).read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        tools = next(line.removeprefix("tools: ").strip() for line in frontmatter.splitlines()
                     if line.startswith("tools: "))
        enabled = {tool.strip() for tool in tools.split(",")}
        assert "Edit" not in enabled and "Write" not in enabled


def test_team_readme_explicitly_distinguishes_runtime_from_ide_profiles():
    readme = (DOCS / "README.md").read_text(encoding="utf-8")
    assert "Всего 14 профилей" in readme
    assert "не являются автономными сотрудниками" in readme
    for code in ("finance-audit", "ai-safety"):
        assert code in readme
    roster = (ROOT / "docs" / "AGENT_TEAM_AND_ROADMAP_2026-10-30.md").read_text(encoding="utf-8")
    assert "1 Chief Analyst + 20" in roster
    assert "1 главный проверяющий + 13" in roster
