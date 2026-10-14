"""Agent Registry в коде (§59, §116 ТЗ): Chief Analyst, Evidence Judge и детерминированные специалисты; всё выключено
флагом chief_analyst.

Специалист = область анализа поверх семейств правил (rule_families), которые уже реализованы в rules/: он не считает
и не утверждает новых чисел, а собирает находки своей области и честно говорит, проверялась ли она
(agents/specialists.py). Новый специалист добавляется вместе со своими правилами, не раньше (YAGNI).
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
    rule_families: tuple[str, ...] = ()  # семейства правил rules/, чьи находки принадлежат этой области

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


_NO_WRITE = dict(workspace_scope="current_workspace", write_scope=(), version="1", knowledge_pack_version=None,
                 model_policy="llm_gateway_only", max_runtime_s=60, max_tool_calls=0, flag_name="chief_analyst",
                 provider_scope=("yandex_direct", "yandex_metrika"), forbidden_claims=("FACT", "DERIVED_FACT"),
                 optional_data=(), object_scope=("campaign",), data_scope=("aggregates",),
                 read_scope=("evidence_bundle",))

# Специалисты работают только внутри Chief Analyst: своего флага у них нет, включаются вместе с ним.
_SPECIALIST = dict(_NO_WRITE, flag_name="chief_analyst", model_policy="deterministic", allowed_claim_types=frozenset(),
                   allowed_actions=frozenset({ActionType.INSPECT, ActionType.MONITOR, ActionType.INVESTIGATE,
                                              ActionType.DO_NOTHING}))


def _specialist(agent_id: str, name: str, domain: str, families: tuple[str, ...], required: tuple[str, ...],
                objects: tuple[str, ...]) -> AgentSpec:
    return AgentSpec(agent_id=agent_id, name=name, domain=domain, rule_families=families, required_data=required,
                     **{**_SPECIALIST, "object_scope": objects})


SPECIALISTS = (
    _specialist("data_quality", "Качество данных", "data_health", (), ("data_health",), ("account",)),
    _specialist("campaign_performance", "Эффективность кампаний", "performance",
                ("high_cpa", "zero_conv_campaign"), ("direct_cost", "direct_conversions"), ("campaign",)),
    _specialist("search_queries", "Поисковые запросы", "search", ("zero_conv_queries",),
                ("direct_cost", "direct_conversions", "search_query_stats"), ("search_query",)),
    _specialist("rsya_placements", "РСЯ и площадки", "network", ("zero_conv_placements",),
                ("direct_cost", "direct_conversions", "placement_stats"), ("placement",)),
    _specialist("anomaly", "Аномалии", "anomaly", ("anomaly",), ("direct_cost", "direct_conversions"),
                ("campaign",)),
    _specialist("budget", "Бюджет", "budget", ("budget_underuse",), ("direct_cost", "campaign_budget"),
                ("campaign",)),
    # без своих правил: область — исправность целей Метрики (data_health.goals)
    _specialist("goals_attribution", "Цели и атрибуция", "measurement", (), ("metrika_goals",), ("account",)),
    # без своих правил: вклад CPC и CR в изменение CPA по фактам campaign_periods (intelligence/root_cause.py)
    _specialist("root_cause", "Причины изменения CPA", "root_cause", (),
                ("direct_cost", "direct_clicks", "direct_conversions"), ("campaign",)),
)

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
    *SPECIALISTS,
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
