# Project instructions

For structural codebase exploration, use the installed `codebase-memory` skill.

Project roles and evidence requirements: [docs/project-agents/README.md](docs/project-agents/README.md).
The evidence supervisor checks structured claims against an independently supplied manifest;
it does not authenticate arbitrary files or replace human release approval.
Keep one writer per worktree and preserve changes owned by other tasks.

## Agent routing (2026-10-30)

For Codex and any other IDE agent runner, use [the exact responsibility map](docs/AGENT_TEAM_AND_ROADMAP_2026-10-30.md), not a guessed list of installed workers. There are **14 development profiles (1 read-only Evidence Supervisor + 13 subagents)**. Separate from these are **21 product roles (1 Chief Analyst + 20 specialists)** defined in `backend/app/intelligence/agent_control.py`. A limited Chief dispatcher and four specialist diagnostics now run on-demand; none is an autonomous LLM process. See `docs/CHIEF_EIGHT_SPECIALISTS_2026-10-30.md`.

- Source/metrics changes: integration and backend-metrics implement; data-contract-qa plus finance-audit independently verify.
- AI/agent behavior: integration owner implements, ai-safety independently checks model boundaries, provenance and prompt injection; supervisor makes a scoped verdict.
- User-facing pages: frontend implements and SEO checks search metadata; security/legal veto any unapproved real-data or marketing claims.
- Runtime: release-ops implements, runtime-reliability independently checks queue health and restore tests; QA reproduces negative E2E.
- Never claim a profile ran unless its actual invocation, revision, results and independent evidence are recorded.
- Do not automatically merge, deploy, enable LLM on real data, change advertising accounts, approve legal texts, or relax CI gates.
