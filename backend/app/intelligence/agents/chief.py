"""Chief Analyst (§59 ТЗ): детерминированный план над находками + связный текст через LLM-шлюз → Judge → или шаблон.

План решает код: Capability Resolver — что допустимо, приоритет — по ₽ exposure, два действия на один объект — оба
не выше inspect_only (conflict), недостаточно данных — отказ «Недостаточно данных» с тем, что подключить. LLM только
пересказывает план; шлюз приходит инъекцией (модуль не импортирует сеть). Каждый запуск даёт AgentRunRecord;
запись в БД делает вызывающий."""

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from app.flags import flag
from app.intelligence.actions.capabilities import CapabilityResult, CapabilityStatus, resolve_action
from app.intelligence.agents.registry import get_agent
from app.intelligence.agents.run_record import AgentRunRecord
from app.intelligence.agents.specialists import SpecialistReport, route
from app.intelligence.contracts.action_types import ActionCandidate, ActionType
from app.intelligence.contracts.claims import CausalStatus, Claim, ClaimType
from app.intelligence.contracts.evidence import EvidenceBundle, canonical_json
from app.intelligence.contracts.sufficiency import ActionLevel, DataSufficiency, level_for, lowered
from app.intelligence.judge import judge
from app.intelligence.privacy import OBJECT_REF, PrivacyError, build_packet

INSUFFICIENT_TEXT = "Недостаточно данных"
_CONNECT = {
    "source_missing": "Подключите Яндекс Директ",
    "metrika_missing": "Подключите Яндекс Метрику",
    "conversion_definition_missing": "Выберите цели конверсий в Яндекс Метрике",
    "revenue_missing": "Передайте доход в Яндекс Метрику (электронная коммерция)",
    "search_query_stats_missing": "Дождитесь накопления статистики поисковых запросов",
    "placement_stats_missing": "Дождитесь накопления статистики площадок РСЯ",
    "experiment_control_missing": "Нужна контрольная группа для эксперимента",
}
_FALLBACK_CONNECT = "Подключите недостающие источники и дождитесь накопления статистики"


@dataclass(frozen=True)
class RunContext:
    run_id: str
    workspace_id: int
    rule_version: str
    source_snapshot_ids: tuple[int, ...]
    metric_versions: tuple[str, ...]
    data_status: str


@dataclass(frozen=True)
class PlanItem:
    finding_id: str
    object: Any
    action_type: ActionType
    level: ActionLevel
    exposure: Decimal | None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Explanation:
    summary: str
    claims: tuple[Claim, ...]
    source: str  # "llm" | "template"


@dataclass(frozen=True)
class ChiefResult:
    plan: tuple[PlanItem, ...]
    explanation: Explanation
    refusal: str | None
    missing_data: tuple[str, ...]
    run: AgentRunRecord
    specialists: tuple[SpecialistReport, ...] = ()


@dataclass
class _LLMTrace:
    fields: dict = field(default_factory=dict)
    tools: tuple[str, ...] = ()


# --- План ---------------------------------------------------------------------------------------------------------

def capabilities_of(bundle: EvidenceBundle) -> dict[str, CapabilityResult]:
    """В пакете возможность — строка статуса или {status, max_level, reasons}."""
    out = {}
    for key, value in bundle.capabilities.items():
        raw = value if isinstance(value, Mapping) else {"status": value}
        level = raw.get("max_level")
        out[key] = CapabilityResult(CapabilityStatus(raw["status"]), tuple(raw.get("reasons", ())),
                                    ActionLevel(level) if level else None)
    return out


def _sufficiency(value: Any) -> DataSufficiency:
    # нет оценки — считаем недостаточной: угадывать уровень нельзя
    return DataSufficiency(value) if value else DataSufficiency.INSUFFICIENT


def _item(finding: Mapping, caps: Mapping[str, CapabilityResult]) -> PlanItem:
    action = ActionType(finding["action_type"])
    sufficiency = _sufficiency(finding.get("data_sufficiency"))
    level = lowered(level_for(sufficiency), ActionLevel(finding.get("action_level", "change_candidate")))
    exposure = finding.get("exposure")
    if sufficiency is DataSufficiency.INSUFFICIENT:
        return PlanItem(finding["id"], finding["object"], action, ActionLevel.NO_ACTION, exposure,
                        ("insufficient_data",))
    candidate = ActionCandidate(action, str(finding["object"]), None, None, (), str(finding.get("rule", "rule")),
                                (finding["id"],), "high", "partially_reversible", "recommend_only",
                                "Сравнить показатели объекта до и после изменения")
    level, reasons = resolve_action(candidate, caps, level)
    return PlanItem(finding["id"], finding["object"], action, level, exposure, reasons)


def build_plan(bundle: EvidenceBundle) -> tuple[PlanItem, ...]:
    caps = capabilities_of(bundle)
    items = [_item(f, caps) for f in bundle.findings]
    per_object: dict[str, int] = {}
    for it in items:
        per_object[str(it.object)] = per_object.get(str(it.object), 0) + 1
    items = [PlanItem(it.finding_id, it.object, it.action_type, lowered(it.level, ActionLevel.INSPECT_ONLY),
                      it.exposure, it.reasons + ("conflict",)) if per_object[str(it.object)] > 1 else it
             for it in items]
    return tuple(sorted(items, key=lambda it: (it.exposure is None, -(it.exposure or 0), it.finding_id)))


def missing_data(bundle: EvidenceBundle) -> tuple[str, ...]:
    reasons = list(bundle.data_health.get("missing", ()))
    for cap in capabilities_of(bundle).values():
        if cap.status is not CapabilityStatus.SUPPORTED:
            reasons += cap.reasons
    texts = tuple(dict.fromkeys(_CONNECT[r] for r in reasons if r in _CONNECT))
    return texts or (_FALLBACK_CONNECT,)


# --- Текст --------------------------------------------------------------------------------------------------------

def _rub(value: Decimal | None) -> str:
    return "нет оценки" if value is None else f"{format(value, 'f')} ₽"


def template_explanation(plan: tuple[PlanItem, ...]) -> Explanation:
    if not plan:
        return Explanation("Признаков неэффективности не найдено", (), "template")
    claims = tuple(Claim(ClaimType.OBSERVATION, f"Находка {it.finding_id}: действие {it.action_type.value}, "
                         f"уровень {it.level.value}, расход с признаками неэффективности {_rub(it.exposure)}",
                         (it.finding_id,), CausalStatus.DESCRIPTIVE, origin="deterministic") for it in plan)
    return Explanation(f"Находок: {len(plan)}. Порядок — по расходу с признаками неэффективности", claims,
                       "template")


def _plan_rows(plan: tuple[PlanItem, ...]) -> tuple[dict, ...]:
    return tuple({"finding": it.finding_id, "object": it.object, "action_type": it.action_type.value,
                  "level": it.level.value, "reasons": it.reasons} for it in plan)


def _display(text: str, refs: Mapping) -> str:
    """Обратная подстановка obj_N → объект — только после Judge."""
    return OBJECT_REF.sub(lambda m: str(refs[m.group(0)]), text)


def llm_explanation(bundle: EvidenceBundle, plan: tuple[PlanItem, ...], gateway, trace: _LLMTrace):
    try:
        packet = build_packet(bundle, _plan_rows(plan))
    except PrivacyError:
        trace.tools = ("privacy_guard",)
        return None
    result = gateway.generate(packet.payload)
    trace.tools = ("privacy_guard", "llm_gateway", "evidence_judge")
    if result.attempts:  # вызов был: LLM применялся, даже если ответ ушёл на шаблон
        trace.fields = dict(provider=result.provider, model=result.model, model_version=result.model_version,
                            prompt_version=result.prompt_version, prompt_hash=result.prompt_hash)
    if result.answer is None:
        return None
    verdict = judge(result.answer.model_dump(), packet, get_agent("chief_analyst").allowed_claim_types)
    if not verdict.accepted:
        return None
    claims = tuple(Claim(c.type, _display(c.text, packet.refs), c.evidence_ids, c.causal_status) for c in
                   verdict.claims)
    return Explanation(_display(verdict.summary, packet.refs), claims, "llm")


# --- Запуск -------------------------------------------------------------------------------------------------------

def _record(ctx: RunContext, bundle: EvidenceBundle, plan, explanation: Explanation, refusal: str | None,
            trace: _LLMTrace, started: datetime, t0: float, specialists=()) -> AgentRunRecord:
    output = {"plan": [{**row, "exposure": it.exposure} for row, it in zip(_plan_rows(plan), plan)],
              "summary": explanation.summary, "claims": [c.text for c in explanation.claims], "refusal": refusal,
              "specialists": [[r.agent_id, r.status.value, list(r.finding_ids)] for r in specialists]}
    return AgentRunRecord(
        run_id=ctx.run_id, workspace_id=ctx.workspace_id, started_at=started,
        completed_at=datetime.now(timezone.utc), status="refused" if refusal else "completed",
        agent_version=get_agent("chief_analyst").version, rule_version=ctx.rule_version,
        input_bundle_hash=bundle.bundle_hash, source_snapshot_ids=ctx.source_snapshot_ids,
        metric_versions=ctx.metric_versions, data_status=ctx.data_status,
        data_sufficiency=_sufficiency(bundle.data_health.get("data_sufficiency")),
        capabilities_used=tuple(sorted(bundle.capabilities)), tools_used=trace.tools,
        latency_ms=int((time.monotonic() - t0) * 1000),
        output_hash=hashlib.sha256(canonical_json(output).encode("utf-8")).hexdigest(),
        decision_count=len(plan), recommendation_count=sum(it.level.rank >= ActionLevel.REVIEW.rank for it in plan),
        explanation_count=1, refusal_reason="insufficient_data" if refusal else None, **trace.fields)


def _insufficient(bundle: EvidenceBundle, plan: tuple[PlanItem, ...]) -> bool:
    if _sufficiency(bundle.data_health.get("data_sufficiency")) is DataSufficiency.INSUFFICIENT:
        return True
    return bool(plan) and all("insufficient_data" in it.reasons for it in plan)


def run(bundle: EvidenceBundle, ctx: RunContext, gateway=None, env: Mapping[str, str] | None = None
        ) -> ChiefResult | None:
    """None — агент выключен флагом chief_analyst. gateway — LLMGateway или None (только шаблон)."""
    if not flag("chief_analyst", env):
        return None
    started, t0, trace = datetime.now(timezone.utc), time.monotonic(), _LLMTrace()
    specialists = route(bundle)
    plan = build_plan(bundle)
    if _insufficient(bundle, plan):
        missing = missing_data(bundle)
        explanation = Explanation(INSUFFICIENT_TEXT, (), "template")
        return ChiefResult((), explanation, INSUFFICIENT_TEXT, missing,
                           _record(ctx, bundle, (), explanation, INSUFFICIENT_TEXT, trace, started, t0, specialists),
                           specialists)
    explanation = None
    if plan and gateway is not None and flag("llm_enabled", env):
        explanation = llm_explanation(bundle, plan, gateway, trace)
    explanation = explanation or template_explanation(plan)
    return ChiefResult(plan, explanation, None, (),
                       _record(ctx, bundle, plan, explanation, None, trace, started, t0, specialists), specialists)
