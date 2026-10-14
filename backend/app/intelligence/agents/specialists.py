"""Детерминированные специалисты (§13–§14 ТЗ): находки правил из Evidence Bundle → отчёт по области.

Специалист ничего не считает и не утверждает: он владеет семействами правил (registry.SPECIALISTS) и отвечает,
что в его области — находки, проблем нет, данных мало или область не проверялась. «Не проверялась» (правила
области не запускались — data_health.rules_run) никогда не выдаётся за «проблем нет» (§6 ТЗ).
Находка правила, которого нет ни у одного специалиста, — ошибка сборки, а не молчаливый пропуск."""

from dataclasses import dataclass
from enum import Enum

from app.intelligence.agents.registry import SPECIALISTS, AgentSpec
from app.intelligence.contracts.evidence import EvidenceBundle
from app.intelligence.metrics.contribution import Period
from app.intelligence.root_cause import Status as CauseStatus
from app.intelligence.root_cause import explain
from app.rules import ALL_RULES

_FAMILY_OF = {r.rule_version: r.family for r in ALL_RULES}


class Status(str, Enum):
    ISSUE_FOUND = "issue_found"
    NO_MATERIAL_ISSUE = "no_material_issue"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_SUPPORTED = "not_supported"


@dataclass(frozen=True)
class SpecialistReport:
    agent_id: str
    status: Status
    finding_ids: tuple[str, ...]
    missing: tuple[str, ...] = ()
    details: tuple = ()  # root_cause: Cause по каждому факту campaign_periods


def _family(rule: str) -> str:
    try:
        return _FAMILY_OF[rule]
    except KeyError:
        raise ValueError(f"находка правила {rule!r}: нет в rules/, специалиста для неё нет") from None


def _goals(spec: AgentSpec, goals) -> SpecialistReport:
    """data_health.goals: {metrika: connected|missing, selected_goals: N, source_failure: код|None}. Нет — не проверялось."""
    if not goals:
        return SpecialistReport(spec.agent_id, Status.NOT_SUPPORTED, ())
    if goals.get("metrika") != "connected":
        return SpecialistReport(spec.agent_id, Status.INSUFFICIENT_DATA, (), ("metrika_missing",))
    if not goals.get("selected_goals"):
        return SpecialistReport(spec.agent_id, Status.ISSUE_FOUND, (), ("conversion_definition_missing",))
    if goals.get("source_failure"):
        return SpecialistReport(spec.agent_id, Status.ISSUE_FOUND, (), (goals["source_failure"],))
    return SpecialistReport(spec.agent_id, Status.NO_MATERIAL_ISSUE, ())


def _period(values, side: str) -> Period:
    return Period(values[f"{side}_cost"], values.get(f"{side}_clicks"), values.get(f"{side}_conversions"))


def _root_cause(spec: AgentSpec, bundle: EvidenceBundle) -> SpecialistReport:
    facts = [f for f in bundle.facts if f.get("kind") == "campaign_periods"]
    if not facts:
        return SpecialistReport(spec.agent_id, Status.NOT_SUPPORTED, ())
    causes = tuple((f["id"], explain(_period(f["values"], "before"), _period(f["values"], "after"))) for f in facts)
    ids = tuple(fid for fid, c in causes if c.status is CauseStatus.ASSOCIATED)
    unclear = any(c.status in (CauseStatus.NOT_ESTABLISHED, CauseStatus.INSUFFICIENT_DATA) for _, c in causes)
    status = Status.ISSUE_FOUND if ids else Status.INSUFFICIENT_DATA if unclear else Status.NO_MATERIAL_ISSUE
    return SpecialistReport(spec.agent_id, status, ids, details=tuple(c for _, c in causes))


def _report(spec: AgentSpec, bundle: EvidenceBundle, owned: dict[str, list[str]]) -> SpecialistReport:
    health = bundle.data_health
    insufficient = health.get("data_sufficiency") == "insufficient"  # нет оценки — не «мало данных»
    if spec.agent_id == "goals_attribution":
        return _goals(spec, health.get("goals"))
    if spec.agent_id == "root_cause":
        return _root_cause(spec, bundle)
    if not spec.rule_families:  # качество данных: область — сам data_health
        missing = tuple(health.get("missing", ()))
        status = (Status.INSUFFICIENT_DATA if insufficient else Status.ISSUE_FOUND if missing
                  else Status.NO_MATERIAL_ISSUE)
        return SpecialistReport(spec.agent_id, status, (), missing)
    ids = tuple(fid for family in spec.rule_families for fid in owned.get(family, ()))
    ran = {_FAMILY_OF.get(r) for r in health.get("rules_run", ())}
    if ids:
        status = Status.ISSUE_FOUND
    elif not ran & set(spec.rule_families):
        status = Status.NOT_SUPPORTED
    else:
        status = Status.INSUFFICIENT_DATA if insufficient else Status.NO_MATERIAL_ISSUE
    return SpecialistReport(spec.agent_id, status, ids)


def route(bundle: EvidenceBundle) -> tuple[SpecialistReport, ...]:
    owned: dict[str, list[str]] = {}
    for f in bundle.findings:
        owned.setdefault(_family(f["rule"]), []).append(f["id"])
    return tuple(_report(spec, bundle, owned) for spec in SPECIALISTS)
