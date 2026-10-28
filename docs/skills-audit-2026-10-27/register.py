"""Create a complete skill applicability register from verified installation receipts."""
import csv
import hashlib
import json
import re
from pathlib import Path

OUT = Path(__file__).parent
APPLIED = {"hallmark", "karpathy-guidelines", "security-review", "python-testing", "frontend-a11y", "production-audit", "market-research", "competitive-platform-analysis", "good-docs-audit", "good-docs-writing"}


def main():
    records = json.loads((OUT / "installation.json").read_text(encoding="utf-8"))
    rows = []
    for record in records:
        path = Path(record["destination"]) / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["skill_md_sha256"]
        frontmatter = content.split("---", 2)[1] if content.startswith("---") else ""
        assert re.search(r"^name:\s*\S", frontmatter, re.M), path
        description = re.search(r"^description:\s*(.*)", frontmatter, re.M)
        description = description.group(1).strip().strip('"\'') if description else ""
        is_applied = record["name"] in APPLIED and not (record["repo"] == "ComposioHQ/composio" and record["name"] == "python-testing")
        if is_applied:
            status, reason = "applied", "Использован в профильном аудите; конкретные проверки перечислены в REPORT.md"
        elif record["repo"] == "ComposioHQ/composio":
            status, reason = "available_not_applicable", "SDK/CLI или внутренний workflow Composio; INROU не является его монорепозиторием"
        elif record["repo"] == "vinta/awesome-python":
            status, reason = "available_not_applicable", "Поддержка каталога awesome-python и его PR; не аудит SaaS"
        elif "example" in record["name"]:
            status, reason = "template", "Шаблон проектных инструкций; не заменяет действующий AGENTS.md"
        else:
            status, reason = "available_not_invoked", "Оценён по метаданным; отдельный стек/этап работы или перекрытие выбранными профилями; выполнение не заявляется"
        refs = []
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if re.match(r"(?:https?://|#|mailto:|<)", target):
                continue
            target = target.split("#", 1)[0]
            if target and not (path.parent / target).exists():
                refs.append(target)
        rows.append({**record, "description": description, "applicability": status, "reason": reason, "unresolved_relative_links": "; ".join(refs)})
    with (OUT / "skills-register.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "skill-checks.json").write_text(json.dumps({"verified_skill_md": len(rows), "applied": [r["name"] for r in rows if r["applicability"] == "applied"], "relative_link_warnings": [{"name": r["name"], "links": r["unresolved_relative_links"]} for r in rows if r["unresolved_relative_links"]]}, ensure_ascii=False, indent=2), encoding="utf-8")
    assert len(rows) == 340
    print(f"Verified {len(rows)} frontmatters and SHA256; {sum(bool(r['unresolved_relative_links']) for r in rows)} skills have unresolved relative links")


if __name__ == "__main__":
    main()
