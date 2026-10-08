"""Agent Registry в коде (§59, §116 ТЗ). Сейчас только две заглушки, выключенные флагом chief_analyst.

Специалистов (§59) здесь нет намеренно: каждый добавляется вместе со своей реализацией (YAGNI).
Права: ни один агент не пишет (write_scope пуст) и не утверждает FACT / DERIVED_FACT — это проверяет конструктор."""

from dataclasses import dataclass
from types import MappingProxyType

from app.flags import flag
from app.intelligence.contracts.action_types import STATE_CHANGING, ActionType
from app.intelligence.contracts.claims import AUTHORITATIVE_CLAIM_TYPES, ClaimType
from app.intelligence.contracts.finding import AgentFinding


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    name: str
    domain: str
    provider_scope: tuple[str, ...]
    required_data: tuple[str, ...]
    optional_data: tuple[str, ...]
    allowed_claim_types: frozenset[ClaimType]
    allowed_actions: frozenset[ActionType]
    forbidden_claims: tuple[str, ...]
    version: str
    knowledge_pack_version: str | None
    model_policy: str
    max_runtime_s: int
    max_tool_calls: int
    workspace_scope: str                 # §116: чужие workspace агент не видит
    object_scope: tuple[str, ...]
    data_scope: tuple[str, ...]
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...]         # всегда пусто
    flag_name: str

    def __post_init__(self):
        if self.allowed_claim_types & AUTHORITATIVE_CLAIM_TYPES:
            raise ValueError(f"{self.agent_id}: агент не может утверждать FACT / DERIVED_FACT")
        if self.allowed_actions & STATE_CHANGING:
            raise ValueError(f"{self.agent_id}: allowed_actions не может менять кабинет (действия применяет не агент)")
        if self.write_scope:
            raise ValueError(f"{self.agent_id}: write_scope должен быть пуст")

    @property
    def enabled(self) -> bool:
        """Флаг читается при каждом обращении, не при импорте."""
        return flag(self.flag_name)


_NO_WRITE = dict(workspace_scope="current_workspace", write_scope=(), version="0", knowledge_pack_version=None,
                 model_policy="llm_gateway_only", max_runtime_s=60, max_tool_calls=0, flag_name="chief_analyst",
                 provider_scope=("yandex_direct", "yandex_metrika"), forbidden_claims=("FACT", "DERIVED_FACT"),
                 optional_data=(), object_scope=("campaign",), data_scope=("aggregates",),
                 read_scope=("evidence_bundle",))

AGENTS = MappingProxyType({a.agent_id: a for a in (
    AgentSpec(agent_id="evidence_judge", name="Evidence Judge", domain="evidence",
              required_data=("evidence_bundle", "agent_findings"), allowed_claim_types=frozenset(),
              allowed_actions=frozenset(), **_NO_WRITE),
    AgentSpec(agent_id="chief_analyst", name="Chief Analyst", domain="orchestration",
              required_data=("evidence_bundle",),
              allowed_claim_types=frozenset({ClaimType.OBSERVATION, ClaimType.ASSOCIATION, ClaimType.HYPOTHESIS,
                                             ClaimType.RECOMMENDATION_CANDIDATE}),
              allowed_actions=frozenset({ActionType.INSPECT, ActionType.MONITOR, ActionType.INVESTIGATE,
                                         ActionType.DO_NOTHING}), **_NO_WRITE),
)})


def get_agent(agent_id: str) -> AgentSpec:
    return AGENTS[agent_id]


def validate_finding(spec: AgentSpec, finding: AgentFinding) -> None:
    """Находка укладывается в права агента: известный agent_id, разрешённые типы утверждений и действий."""
    if finding.agent_id not in AGENTS or finding.agent_id != spec.agent_id:
        raise ValueError(f"agent_id {finding.agent_id!r}: нет в реестре или не совпадает с {spec.agent_id!r}")
    for claim in finding.observations + finding.hypotheses:
        if claim.type not in spec.allowed_claim_types:
            raise ValueError(f"claim {claim.type.value}: агент {spec.agent_id} такие утверждения не делает")
    for candidate in finding.candidate_actions:
        if candidate.action_type not in spec.allowed_actions:
            raise ValueError(f"action {candidate.action_type.value}: агенту {spec.agent_id} не разрешено")
