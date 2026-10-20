"""Типы утверждений (§17) и статус причинности (§18 ТЗ). Вывод агента — не доказательство."""

from dataclasses import dataclass
from enum import Enum

from app.intelligence.contracts._validate import check_ident_tuple, check_text


class ClaimType(str, Enum):
    FACT = "FACT"
    DERIVED_FACT = "DERIVED_FACT"
    OBSERVATION = "OBSERVATION"
    ASSOCIATION = "ASSOCIATION"
    HYPOTHESIS = "HYPOTHESIS"
    EXPERIMENT_RESULT = "EXPERIMENT_RESULT"
    VERIFIED_OUTCOME = "VERIFIED_OUTCOME"
    RECOMMENDATION_CANDIDATE = "RECOMMENDATION_CANDIDATE"  # не доказательство
    ANALYST_OPINION = "ANALYST_OPINION"                    # не доказательство


class CausalStatus(str, Enum):
    DESCRIPTIVE = "descriptive"
    ASSOCIATED = "associated"
    PLAUSIBLE_HYPOTHESIS = "plausible_hypothesis"
    EXPERIMENTALLY_SUPPORTED = "experimentally_supported"
    VERIFIED = "verified"
    NOT_ESTABLISHED = "not_established"


C, K = ClaimType, CausalStatus
AUTHORITATIVE_CLAIM_TYPES = frozenset({C.FACT, C.DERIVED_FACT})  # только детерминированный код
AI_ALLOWED_CLAIM_TYPES = frozenset({C.OBSERVATION, C.ASSOCIATION, C.HYPOTHESIS})
NON_EVIDENCE_KINDS = frozenset({C.RECOMMENDATION_CANDIDATE, C.ANALYST_OPINION})
_AI_TYPES = AI_ALLOWED_CLAIM_TYPES | NON_EVIDENCE_KINDS

# Какие статусы причинности допустимы для типа; NOT_ESTABLISHED допустим всегда.
_DESCRIPTIVE = frozenset({K.DESCRIPTIVE, K.NOT_ESTABLISHED})
_CAUSAL_ALLOWED = {
    C.FACT: _DESCRIPTIVE, C.DERIVED_FACT: _DESCRIPTIVE, C.OBSERVATION: _DESCRIPTIVE,
    C.RECOMMENDATION_CANDIDATE: _DESCRIPTIVE, C.ANALYST_OPINION: _DESCRIPTIVE,
    C.ASSOCIATION: _DESCRIPTIVE | {K.ASSOCIATED},
    C.HYPOTHESIS: _DESCRIPTIVE | {K.ASSOCIATED, K.PLAUSIBLE_HYPOTHESIS},
    C.EXPERIMENT_RESULT: _DESCRIPTIVE | {K.ASSOCIATED, K.EXPERIMENTALLY_SUPPORTED},
    C.VERIFIED_OUTCOME: _DESCRIPTIVE | {K.ASSOCIATED, K.VERIFIED},
}


@dataclass(frozen=True)
class Claim:
    """Утверждение. origin="ai" по умолчанию: AI не может выдать себя за источник факта.
    origin="deterministic" Claim не проверяет — его выставляет вызывающий код. Парсер ответов LLM (позже) обязан
    жёстко ставить origin="ai"; AgentFinding отвергает любое утверждение с другим origin."""
    type: ClaimType
    text: str
    evidence_ids: tuple[str, ...]
    causal_status: CausalStatus
    origin: str = "ai"

    def __post_init__(self):
        if self.origin not in ("ai", "deterministic"):
            raise ValueError(f"origin: {self.origin!r}")
        if not isinstance(self.type, ClaimType) or not isinstance(self.causal_status, CausalStatus):
            raise ValueError("type / causal_status: ожидаются ClaimType / CausalStatus")
        check_text("text", self.text)
        check_ident_tuple("evidence_ids", self.evidence_ids)
        if self.origin == "ai" and self.type not in _AI_TYPES:
            raise ValueError(f"AI-утверждение не может быть {self.type.value}")
        if self.type in AUTHORITATIVE_CLAIM_TYPES and not self.evidence_ids:
            raise ValueError(f"{self.type.value} требует evidence_ids")
        if self.causal_status not in _CAUSAL_ALLOWED[self.type]:
            raise ValueError(f"causal_status {self.causal_status.value} недопустим для {self.type.value}")
