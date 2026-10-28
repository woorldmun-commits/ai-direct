"""Install source-pinned skills without replacing existing global skill directories."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).parent
INSTALLER = Path.home() / ".codex/skills/.system/skill-installer/scripts/install-skill-from-github.py"
DEST = Path.home() / ".codex/skills"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(skills):
    def priority(item):
        path = item["path"]
        return (0 if path.startswith("skills/") else 1 if path.startswith(".agents/") else 2 if not path.startswith("docs/") else 3, path)
    selected = {}
    for item in sorted(skills, key=priority):
        selected.setdefault(item["name"], item)
    return list(selected.values())


def main():
    sources = json.loads((OUT / "sources.json").read_text(encoding="utf-8"))
    receipt = []
    for source in sources:
        skills = canonical(source["skills"])
        if not skills:
            continue
        stage = Path(tempfile.mkdtemp(prefix="inrou-skills-"))
        command = [sys.executable, str(INSTALLER), "--repo", source["repo"], "--ref", source["commit"], "--dest", str(stage), "--path", *[item["path"] for item in skills]]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        (OUT / (source["repo"].replace("/", "-") + "-installer.log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Installer failed: {source['repo']}; see log")
        prefix = {"ComposioHQ/composio": "composio", "vinta/awesome-python": "awesome-python", "affaan-m/ECC": "ecc"}.get(source["repo"], source["repo"].split("/")[-1])
        for skill in skills:
            staged = stage / skill["name"]
            skill_hash = digest(staged / "SKILL.md")
            existing = [Path(p) for p in skill["existing"] if Path(p).is_file()]
            matched = next((p.parent for p in existing if digest(p) == skill_hash), None)
            if matched:
                target, status = matched, "already_present_same_skill_md"
            else:
                target = DEST / skill["name"]
                if target.exists() or existing:
                    target = DEST / f"{prefix}-{skill['name']}"
                if target.exists():
                    assert digest(target / "SKILL.md") == skill_hash, f"Conflicting version: {target}"
                    status = "already_present_namespaced"
                else:
                    shutil.copytree(staged, target)
                    status = "installed"
            receipt.append({"repo": source["repo"], "commit": source["commit"], "path": skill["path"], "name": skill["name"], "destination": str(target), "status": status, "skill_md_sha256": skill_hash})
        print(f"{source['repo']}: verified {len(skills)} unique skills", flush=True)
        (OUT / "installation.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    assert len(receipt) == sum(len(canonical(s["skills"])) for s in sources)
    assert all((Path(item["destination"]) / "SKILL.md").is_file() for item in receipt)
    print(f"Verified {len(receipt)} source skills; newly installed {sum(i['status'] == 'installed' for i in receipt)}")


if __name__ == "__main__":
    main()
