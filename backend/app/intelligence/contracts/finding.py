"""AgentFinding (§60 ТЗ): структурированный результат агента. Поля-эссе нет; вывод агента — не доказательство."""

from dataclasses import dataclass

from app.intelligence.contracts.action_types import ActionCandidate, RejectedAction
from app.intelligence.contracts._validate import check_ident, check_ident_tuple, check_text_tuple
from app.intelligence.contracts.claims import AUTHORITATIVE_CLAIM_TYPES, CausalStatus, Claim, ClaimType
from app.intelligence.contracts.sufficiency import SufficiencyAssessment

_OBSERVATION_TYPES = frozenset({ClaimType.OBSERVATION, ClaimType.ASSOCIATION})
_TEXT_TUPLES = ("affected_objects", "missing_data", "next_checks")
_ITEM_TYPES = {"observations": Claim, "hypotheses": Claim, "candidate_actions": ActionCandidate,
               "rejected_actions": RejectedAction}
# Находка агента (ИИ) не бывает «подтверждена экспериментом» или «верифицирована»: это решает код, не агент.
_AI_CAUSAL = frozenset({CausalStatus.DESCRIPTIVE, CausalStatus.ASSOCIATED, CausalStatus.PLAUSIBLE_HYPOTHESIS,
                        CausalStatus.NOT_ESTABLISHED})


@dataclass(frozen=True)
class AgentFinding:
    agent_id: str
    agent_version: str
    knowledge_version: str
    scope: str
    evidence_ids: tuple[str, ...]
    observations: tuple[Claim, ...]
    hypotheses: tuple[Claim, ...]
    causal_status: CausalStatus
    data_sufficiency: SufficiencyAssessment
    affected_objects: tuple[str, ...]
    candidate_actions: tuple[ActionCandidate, ...]
    rejected_actions: tuple[RejectedAction, ...]
    missing_data: tuple[str, ...]
    next_checks: tuple[str, ...]

    def __post_init__(self):
        for name in ("agent_id", "agent_version", "knowledge_version", "scope"):
            check_ident(name, getattr(self, name))
        check_ident_tuple("evidence_ids", self.evidence_ids)
        for name in _TEXT_TUPLES:
            check_text_tuple(name, getattr(self, name))
        for name, kind in _ITEM_TYPES.items():
            items = getattr(self, name)
            if not isinstance(items, tuple) or not all(isinstance(i, kind) for i in items):
                raise ValueError(f"{name}: ожидается tuple из {kind.__name__}")
        if not isinstance(self.data_sufficiency, SufficiencyAssessment):
            raise ValueError("data_sufficiency: ожидается SufficiencyAssessment")
        if not isinstance(self.causal_status, CausalStatus) or self.causal_status not in _AI_CAUSAL:
            raise ValueError(f"causal_status {self.causal_status!r} недопустим для находки агента")
        if any(not set(a.evidence_ids) <= set(self.evidence_ids) for a in self.candidate_actions):
            raise ValueError("candidate_actions: действие ссылается на evidence вне evidence_ids находки")
        self._check_claims("observations", _OBSERVATION_TYPES)
        self._check_claims("hypotheses", frozenset({ClaimType.HYPOTHESIS}))

    def _check_claims(self, slot: str, allowed: frozenset) -> None:
        for claim in getattr(self, slot):
            if claim.type in AUTHORITATIVE_CLAIM_TYPES or claim.origin != "ai":
                raise ValueError(f"{slot}: агент не создаёт {claim.type.value}")
            if claim.type not in allowed:
                raise ValueError(f"{slot}: тип {claim.type.value} не подходит")
            if not claim.evidence_ids or not set(claim.evidence_ids) <= set(self.evidence_ids):
                raise ValueError(f"{slot}: утверждение ссылается на evidence вне evidence_ids находки")
