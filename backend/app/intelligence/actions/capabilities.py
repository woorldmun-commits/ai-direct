"""Capability Resolver (docs/INTELLIGENCE_V2_CONTRACTS.md §3): что система вправе утверждать и делать при текущих данных.

Чистый: без БД и сети. Матрица рычагов по стратегиям не дублируется — берётся STRATEGY_ACTIONS (sources/campaigns.py;
app/sources/strategy.py чистый). `unknown` в рекомендациях не используется."""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from app.intelligence.contracts.action_types import (  # noqa: F401  (ActionCandidate и др. — часть API модуля)
    NO_EVIDENCE_NEEDED, ActionCandidate, ActionType, RejectedAction)
from app.intelligence.contracts.sufficiency import ActionLevel, from_legacy_action_level, lowered
from app.sources.strategy import STRATEGY_ACTIONS, Strategy


class CapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


S = CapabilityStatus


def usable_in_recommendation(status: CapabilityStatus) -> bool:
    return status in (S.SUPPORTED, S.PARTIAL)


@dataclass(frozen=True)
class CapabilityResult:
    status: CapabilityStatus
    reasons: tuple[str, ...] = ()
    max_level: ActionLevel | None = None  # потолок уровня действия; по умолчанию: usable → без потолка, иначе NO_ACTION

    def __post_init__(self):
        if self.max_level is None:
            usable = usable_in_recommendation(self.status)
            object.__setattr__(self, "max_level", ActionLevel.CHANGE_CANDIDATE if usable else ActionLevel.NO_ACTION)


# --- Анализ по данным -----------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalysisInputs:
    """has_*: True/False — известно; None — неизвестно (даёт UNKNOWN, а не «нет»)."""
    sources: frozenset[str]
    has_conversion_definition: bool | None = None
    has_revenue: bool | None = None
    has_search_query_stats: bool | None = None
    has_placement_stats: bool | None = None
    has_experiment_control: bool | None = None


def _needs(present: bool | None, missing_reason: str, *, partial_if_absent: bool = False) -> CapabilityResult:
    if present is None:
        return CapabilityResult(S.UNKNOWN, (missing_reason,))
    if present:
        return CapabilityResult(S.SUPPORTED)
    return CapabilityResult(S.PARTIAL if partial_if_absent else S.UNSUPPORTED, (missing_reason,))


def resolve_analysis(i: AnalysisInputs) -> dict[str, CapabilityResult]:
    no_direct = CapabilityResult(S.UNSUPPORTED, ("source_missing",))
    direct = "yandex_direct" in i.sources
    revenue = _needs(i.has_revenue, "revenue_missing")
    roas = revenue if revenue.status is not S.SUPPORTED else CapabilityResult(S.SUPPORTED)
    return {
        "cpa": _needs(i.has_conversion_definition, "conversion_definition_missing") if direct else no_direct,
        "revenue": revenue,
        "roas": (roas if direct else no_direct),
        "search_analysis": (_needs(i.has_search_query_stats, "search_query_stats_missing", partial_if_absent=True)
                            if direct else no_direct),
        "placement_analysis": _needs(i.has_placement_stats, "placement_stats_missing") if direct else no_direct,
        "experiment": _needs(i.has_experiment_control, "experiment_control_missing"),
    }


# --- Действия по стратегии кампании ---------------------------------------------------------------

_STRATEGY_LEVERS = (ActionType.CHANGE_BID, ActionType.CHANGE_TARGET_CPA)
_AUTO = frozenset({Strategy.AUTO_CLICKS, Strategy.AUTO_CPC, Strategy.AUTO_CPA, Strategy.PAY_FOR_CONVERSION,
                   Strategy.MAX_CONVERSIONS})


def _lever_reason(strategy: Strategy) -> str:
    return "auto_strategy" if strategy in _AUTO else "manual_strategy" if strategy is Strategy.MANUAL_BIDDING \
        else "strategy_no_lever"


def action_capabilities(strategy: Strategy | None) -> dict[str, CapabilityResult]:
    """Рычаги ставки и целевого CPA для стратегии. None / UNKNOWN — UNKNOWN: ставку трогать нельзя."""
    if strategy is None or strategy is Strategy.UNKNOWN:
        return {a.value: CapabilityResult(S.UNKNOWN, ("strategy_unknown",)) for a in _STRATEGY_LEVERS}
    entry = STRATEGY_ACTIONS.get(strategy)
    if entry is None:  # стратегия не описана в матрице — не угадываем
        return {a.value: CapabilityResult(S.UNKNOWN, ("strategy_not_in_matrix",)) for a in _STRATEGY_LEVERS}
    lever, ceiling = entry
    max_level = from_legacy_action_level(ceiling)
    return {a.value: CapabilityResult(S.SUPPORTED, (), max_level) if a.value == lever
            else CapabilityResult(S.UNSUPPORTED, (_lever_reason(strategy),)) for a in _STRATEGY_LEVERS}


# --- Разрешение действия --------------------------------------------------------------------------

_REQUIRED_CAPABILITY = {
    ActionType.CHANGE_BID: "change_bid", ActionType.CHANGE_TARGET_CPA: "change_target_cpa",
    ActionType.EXCLUDE_PLACEMENT: "placement_analysis", ActionType.ADD_NEGATIVE_KEYWORD: "search_analysis",
    ActionType.RUN_EXPERIMENT: "experiment",
}
# Не меняют кабинет: возможность не нужна.
_FREE_ACTIONS = NO_EVIDENCE_NEEDED | {ActionType.INVESTIGATE, ActionType.FIX_TRACKING, ActionType.FIX_GOAL}


def resolve_action(candidate: ActionCandidate, capabilities: Mapping[str, CapabilityResult],
                   level: ActionLevel) -> tuple[ActionLevel, tuple[str, ...]]:
    """(разрешённый уровень, причины). Уровень только понижается; отказ — NO_ACTION с причиной."""
    action = candidate.action_type
    if action in _FREE_ACTIONS:
        return level, ()
    key = _REQUIRED_CAPABILITY.get(action)
    if key is None:
        return ActionLevel.NO_ACTION, (f"capability_not_defined:{action.value}",)
    cap = capabilities.get(key, CapabilityResult(S.UNKNOWN, ("capability_missing",)))
    if not usable_in_recommendation(cap.status):
        return ActionLevel.NO_ACTION, tuple(f"{key}:{cap.status.value}:{r}" for r in cap.reasons) or (
            f"{key}:{cap.status.value}",)
    cap_level = lowered(cap.max_level, ActionLevel.REVIEW) if cap.status is S.PARTIAL else cap.max_level
    allowed = lowered(level, cap_level)
    return allowed, (() if allowed is level else (f"{key}:{cap.status.value}:level_capped",))
