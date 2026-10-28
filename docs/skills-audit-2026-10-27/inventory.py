"""Read GitHub trees and compare real skill files with global skill locations."""
import json
import subprocess
from pathlib import Path

REPOS = ["awesomedata/awesome-public-datasets", "nutlope/hallmark", "bradtraversy/design-resources-for-developers", "mungell/awesome-for-beginners", "multica-ai/andrej-karpathy-skills", "ComposioHQ/composio", "vinta/awesome-python", "sindresorhus/awesome", "affaan-m/ECC"]
OUT = Path(__file__).parent


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], encoding="utf-8"))


def main():
    roots = [Path.home() / ".codex/skills", Path.home() / ".agents/skills", Path.home() / ".codex/plugins/cache/ecc/ecc/2.2.3/skills"]
    installed = {}
    for root in roots:
        if root.exists():
            for skill in root.glob("*/SKILL.md"):
                installed.setdefault(skill.parent.name.lower(), []).append(str(skill))
    results = []
    for repo in REPOS:
        meta = api(f"repos/{repo}")
        commit = api(f"repos/{repo}/commits/{meta['default_branch']}")["sha"]
        tree = api(f"repos/{repo}/git/trees/{commit}?recursive=1")
        assert not tree.get("truncated"), f"Incomplete tree: {repo}"
        skills = []
        for item in tree["tree"]:
            if item["path"].endswith("/SKILL.md") or item["path"] == "SKILL.md":
                path = str(Path(item["path"]).parent).replace("\\", "/")
                name = Path(path).name
                skills.append({"name": name, "path": path, "blob": item["sha"], "existing": installed.get(name.lower(), [])})
        results.append({"repo": repo, "branch": meta["default_branch"], "commit": commit, "description": meta["description"], "skills": skills})
        print(f"{repo}: {len(skills)} SKILL.md; {sum(not s['existing'] for s in skills)} names absent", flush=True)
    (OUT / "sources.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    assert len(results) == 9


if __name__ == "__main__":
    main()
