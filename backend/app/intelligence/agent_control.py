"""Fail-closed, offline agent-role registry and *structural* handoff review.

This module does not start LLMs, read client data or publish recommendations.
Trusted manifests are supplied by the server/integrator, never by an agent.
A matching record is not proof of causality, reviewer independence or authenticity.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.agents.supervisor import Manifest, Submission, verify


@dataclass(frozen=True, slots=True)
class AgentRole:
    code: str
    duty: str
    implementation: Literal["foundation_only", "planned"]
    existing_basis: str | None = None
    depends_on: tuple[str, ...] = ()
    advertising_write: bool = False


CHIEF = AgentRole(
    "chief_analyst", "Координация анализа, выявление конфликтов и эскалация",
    "planned", depends_on=("evidence_verifier", "risk_guardian"),
)

# IMPORTANT: a foundation is not an autonomous runtime agent. Names here document
# intended ownership; they are not authorization to invoke tools or client APIs.
SPECIALISTS: tuple[AgentRole, ...] = (
    AgentRole("data_health", "Полнота, свежесть, качество и валюты источников",
              "foundation_only", "app.sync / app.worker.health"),
    AgentRole("direct_performance", "Расход, конверсии и рекламные аномалии",
              "foundation_only", "app.rules / app.audit", ("data_health",)),
    AgentRole("conversion_attribution", "Цели, счётчики, атрибуция и досчёт",
              "foundation_only", "app.sources.conversion / app.sync", ("data_health",)),
    AgentRole("finance", "Доказательные CPA, ROAS, CAC и маржинальность",
              "foundation_only", "app.intelligence.economics",
              ("data_health", "conversion_attribution")),
    AgentRole("industry", "Профиль бизнеса, знания ниш и неизвестные допущения",
              "foundation_only", "app.intelligence.knowledge / app.intelligence.profiles"),
    AgentRole("root_cause", "Арифметическая декомпозиция и гипотезы о причинах",
              "foundation_only", "app.intelligence.economics.compare_cpa",
              ("direct_performance", "conversion_attribution")),
    AgentRole("opportunity", "Возможности роста и приоритизация экспериментов",
              "planned", depends_on=("finance", "industry")),
    AgentRole("budget", "Сценарии бюджетов с рисками без изменения кабинета",
              "planned", depends_on=("finance", "direct_performance")),
    AgentRole("creative", "Гипотезы по креативам, только после проверки фактов",
              "planned", depends_on=("industry",)),
    AgentRole("experiment", "Тесты, окна сравнения, достоверность эффекта",
              "planned", depends_on=("finance", "root_cause")),
    AgentRole("evidence_verifier", "Независимая проверка структурированных evidence",
              "foundation_only", "app.agents.supervisor", ("data_health",)),
    AgentRole("risk_guardian", "Ограничение действий, стратегии, права и неизвестные риски",
              "foundation_only", "app.audit.policy", ("evidence_verifier",)),
)
REGISTRY: tuple[AgentRole, ...] = (CHIEF, *SPECIALISTS)
INDEX = {agent.code: agent for agent in REGISTRY}
PRODUCERS = frozenset(
    agent.code for agent in SPECIALISTS
    if agent.code not in ("evidence_verifier", "risk_guardian")
)


def validate_registry() -> None:
    """Reject registry drift before any integration can rely on this metadata."""
    if len(SPECIALISTS) != 12 or len(REGISTRY) != len(INDEX):
        raise ValueError("invalid_agent_roster")
    if CHIEF.code != "chief_analyst":
        raise ValueError("chief_missing")
    for agent in REGISTRY:
        if agent.advertising_write or agent.code in agent.depends_on:
            raise ValueError("unsafe_agent_capability")
        if any(dep not in INDEX for dep in agent.depends_on):
            raise ValueError("unregistered_dependency")
    visited: set[str] = set()
    active: set[str] = set()

    def walk(code: str) -> None:
        if code in active:
            raise ValueError("agent_dependency_cycle")
        if code in visited:
            return
        active.add(code)
        for dep in INDEX[code].depends_on:
            walk(dep)
        active.remove(code)
        visited.add(code)

    for agent in REGISTRY:
        walk(agent.code)


validate_registry()


class Handoff(BaseModel):
    """Structured candidate; review submissions are NOT authenticated attestations."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    specialist: str = Field(min_length=1, max_length=60)
    workspace_id: StrictInt = Field(gt=0)
    candidate: Submission
    evidence_review: Submission | None = None
    risk_review: Submission | None = None
    requests_advertising_write: StrictBool = False


def review_handoff(handoff: Handoff, trusted: Manifest, *, now: datetime | None = None) -> dict:
    """Route a candidate through two *structurally separate* checks.

    Outputs REVIEW_REQUIRED at best. Independent provenance, text semantics,
    business judgment, legal suitability, and human approval remain mandatory.
    No external write or publish capability is exposed here.
    """
    issues: list[str] = []
    if handoff.workspace_id != trusted.workspace_id:
        issues.append("workspace_mismatch")
    if handoff.specialist not in PRODUCERS:
        issues.append("invalid_producer")
    if handoff.requests_advertising_write:
        issues.append("advertising_write_forbidden")
    if not trusted.evidence:
        issues.append("empty_trusted_manifest")
    if handoff.evidence_review is None:
        issues.append("evidence_review_missing")
    if handoff.risk_review is None:
        issues.append("risk_review_missing")

    reports = {}
    submitted_ids = {item.id for item in handoff.candidate.claims}
    for role, submission in (
        ("producer", handoff.candidate),
        ("evidence_verifier", handoff.evidence_review),
        ("risk_guardian", handoff.risk_review),
    ):
        if submission is None:
            continue
        if role != "producer" and {
            item.id for item in submission.claims
        } != submitted_ids:
            issues.append(role + "_claim_set_mismatch")
        checked = verify(submission, trusted, now=now)
        reports[role] = checked["status"]
        if checked["status"] != "PASS":
            issues.append(role + "_" + checked["status"].lower())

    status = (
        "BLOCKED" if any(
            issue in issues for issue in (
                "workspace_mismatch", "invalid_producer",
                "advertising_write_forbidden", "empty_trusted_manifest",
                "evidence_review_missing", "risk_review_missing",
            )
        ) or "BLOCKED" in reports.values()
        else "NEEDS_WORK" if issues else "REVIEW_REQUIRED"
    )
    return {
        "schema_version": 1,
        "status": status,
        "producer": handoff.specialist,
        "review_route": ("evidence_verifier", "risk_guardian", "chief_analyst"),
        "structural_checks": reports,
        "issues": sorted(set(issues)),
        "authenticity_verified": False,
        "independent_review_verified": False,
        "causality_verified": False,
        "publication_allowed": False,
        "advertising_write_allowed": False,
    }
