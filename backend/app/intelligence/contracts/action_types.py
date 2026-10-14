"""Типы действий (§54 ТЗ) и кандидат действия. Кандидат — предложение, а не доказательство и не команда."""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from app.intelligence.contracts._validate import check_ident_tuple, check_text, check_text_tuple, freeze


class ActionType(str, Enum):
    INSPECT = "inspect"
    MONITOR = "monitor"
    FIX_TRACKING = "fix_tracking"
    FIX_GOAL = "fix_goal"
    INVESTIGATE = "investigate"
    CHANGE_TARGET_CPA = "change_target_cpa"
    CHANGE_BID = "change_bid"
    EXCLUDE_PLACEMENT = "exclude_placement"
    ADD_NEGATIVE_KEYWORD = "add_negative_keyword"
    ADJUST_GEO = "adjust_geo"
    ADJUST_DEVICE = "adjust_device"
    ADJUST_SCHEDULE = "adjust_schedule"
    REDISTRIBUTE_BUDGET = "redistribute_budget"
    CHANGE_CREATIVE = "change_creative"
    RUN_EXPERIMENT = "run_experiment"
    DO_NOTHING = "do_nothing"


NO_EVIDENCE_NEEDED = frozenset({ActionType.INSPECT, ActionType.MONITOR, ActionType.DO_NOTHING})
RISKS = ("low", "medium", "high")
REVERSIBILITY = ("reversible", "partially_reversible", "irreversible")
EXECUTION_MODES = ("recommend_only",)  # v1.0 только рекомендует; режим применения появится вместе с Apply (v1.1)
STATE_CHANGING = frozenset({
    ActionType.CHANGE_TARGET_CPA, ActionType.CHANGE_BID, ActionType.EXCLUDE_PLACEMENT, ActionType.ADD_NEGATIVE_KEYWORD,
    ActionType.ADJUST_GEO, ActionType.ADJUST_DEVICE, ActionType.ADJUST_SCHEDULE, ActionType.REDISTRIBUTE_BUDGET,
    ActionType.CHANGE_CREATIVE})


@dataclass(frozen=True)
class ActionCandidate:
    action_type: ActionType
    object: str
    current_state: Mapping | None
    target_state: Mapping | None
    preconditions: tuple[str, ...]
    reason: str
    evidence_ids: tuple[str, ...]
    risk: str
    reversibility: str
    execution_mode: str
    verification_plan: str | None

    def __post_init__(self):
        if not isinstance(self.action_type, ActionType):
            raise ValueError("action_type: ожидается ActionType")
        check_text("object", self.object)
        check_text("reason", self.reason)
        check_text_tuple("preconditions", self.preconditions)
        check_ident_tuple("evidence_ids", self.evidence_ids)
        for name, allowed in (("risk", RISKS), ("reversibility", REVERSIBILITY), ("execution_mode", EXECUTION_MODES)):
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name}: {getattr(self, name)!r} не из {allowed}")
        if self.action_type not in NO_EVIDENCE_NEEDED:
            if not self.evidence_ids:
                raise ValueError(f"{self.action_type.value}: нужны evidence_ids")
        if self.verification_plan is not None or self.action_type not in NO_EVIDENCE_NEEDED:
            check_text("verification_plan", self.verification_plan)
        object.__setattr__(self, "current_state", freeze(self.current_state))
        object.__setattr__(self, "target_state", freeze(self.target_state))


@dataclass(frozen=True)
class RejectedAction:
    action_type: ActionType
    reason: str

    def __post_init__(self):
        check_text("reason", self.reason)
