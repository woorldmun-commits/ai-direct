"""Детерминированные специалисты (§13–§14 ТЗ): находки правил из Evidence Bundle → отчёт по области.

Специалист ничего не считает и не утверждает: он владеет семействами правил (registry.SPECIALISTS) и отвечает,
что в его области — находки, проблем нет, данных мало или область не проверялась. «Не проверялась» (правила
области не запускались — data_health.rules_run) никогда не выдаётся за «проблем нет» (§6 ТЗ).
Находка правила, которого нет ни у одного специалиста, — ошибка сборки, а не молчаливый пропуск."""

from dataclasses import dataclass
from enum import Enum

from app.intelligence.agents.registry import SPECIALISTS, AgentSpec
from app.intelligence.contracts.evidence import EvidenceBundle
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


def _family(rule: str) -> str:
    try:
        return _FAMILY_OF[rule]
    except KeyError:
        raise ValueError(f"находка правила {rule!r}: нет в rules/, специалиста для неё нет") from None


def _report(spec: AgentSpec, bundle: EvidenceBundle, owned: dict[str, list[str]]) -> SpecialistReport:
    health = bundle.data_health
    insufficient = health.get("data_sufficiency") == "insufficient"  # нет оценки — не «мало данных»
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
