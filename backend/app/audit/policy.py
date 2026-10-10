"""Политика безопасных рекомендаций (ARCHITECTURE.md §4.1): rule engine → safety policy → рекомендация → одобрение
человека → изменение. Чистая функция, как правила; версия хранится в каждом finding рядом с rule_version.

Правило отвечает «что показывают данные и какое действие из этого следует» (кандидат). Политика — «вправе ли мы
сейчас его предлагать». Она может только понизить уровень действия, никогда не повысить (это проверяет и БД):

  inspect_only — показать проблему и факты, предложить что проверить; никаких изменений настроек;
  review       — предложить изменение для проверки человеком;
  change       — предложить изменение; и оно выполняется только после явного подтверждения человека.

safety_policy@1:
- достаточность данных текущего периода: low (1–2 конверсии) → inspect_only, medium → review, high → change;
- стратегия кампании неизвестна → не выше review: ручная ставка может быть недоступна на автостратегии;
- неизвестный тип действия → inspect_only: новое правило не может обойти политику.

safety_policy@2 — всё из @1 и дополнительно (только понижает):
- конверсии вывода за дни досчёта (evidence_meta.level_reason = conversions_partial) → не выше review;
- источник данных упал (DataHealth.source_failed) или данные устарели (DataHealth.stale) → inspect_only;
- стратегия кампании из снимка (snapshots.campaign_strategies): у снижения ставки потолок — по матрице
  STRATEGY_ACTIONS (sources/strategy.py), причина strategy_<стратегия>; нет её в снимке — как в @1, strategy_unknown.
  Действия, не зависящие от стратегии (исключение площадок, «проверить»), по известной стратегии не режутся.
DataHealth снимка считает воркер аудита (audit/data_health.py snapshot_health). Поле None = «неизвестно» и не понижает
уровень — неизвестное не выдаётся ни за хорошее, ни за плохое."""

from dataclasses import dataclass

from app.flags import flag
from app.rules.domain import Finding
from app.rules.evidence import PARTIAL_REASON
from app.sources.strategy import STRATEGY_ACTIONS, Strategy

VERSION = "safety_policy@1"
VERSION_V2 = "safety_policy@2"
LEVELS = ("inspect_only", "review", "change")  # по возрастанию воздействия на кабинет

# Уровень, который действие правила требует само по себе.
CANDIDATE_LEVEL = {
    "decrease_bid": "change",
    "investigate_cpa_growth": "inspect_only",
    "investigate_zero_conversions": "inspect_only",  # zero_conv_campaign: только «проверить», настройки не меняются
    # zero_conv_placements: исключение площадок меняет охват кампании — только на проверку человеком, change не бывает
    "exclude_placements": "review",
}
MAX_BY_DATA = {"low": "inspect_only", "medium": "review", "high": "change"}
MAX_WITHOUT_STRATEGY = "review"
MAX_PARTIAL = "review"       # @2: конверсии последних дней ещё досчитываются
MAX_UNHEALTHY = "inspect_only"  # @2: источник упал или данные устарели


@dataclass(frozen=True)
class Decision:
    candidate_level: str
    level: str
    reasons: tuple[str, ...]  # почему понижено; пусто ⇔ level == candidate_level
    version: str = VERSION


def _rank(level: str) -> int:
    return LEVELS.index(level)


def _lowered(f: Finding, caps: tuple[tuple[str, str], ...], version: str) -> Decision:
    candidate = CANDIDATE_LEVEL.get(f.action["type"])
    if candidate is None:
        return Decision("inspect_only", "inspect_only", (), version)  # неизвестное действие изменений не предлагает
    level, reasons = candidate, []
    for cap, reason in caps:
        if _rank(cap) < _rank(candidate):
            reasons.append(reason)
            level = min(level, cap, key=_rank)
    return Decision(candidate, level, tuple(reasons), version)


def decide(f: Finding) -> Decision:
    caps = ((MAX_BY_DATA[f.current_data_quality], f"data_sufficiency_{f.current_data_quality}"),
            (MAX_WITHOUT_STRATEGY, "strategy_unknown"))
    return _lowered(f, caps, VERSION)


@dataclass(frozen=True)
class DataHealth:
    """Состояние источника данных. None — неизвестно: не понижает (см. docstring модуля)."""
    source_failed: bool | None = None
    stale: bool | None = None


def _strategy_cap(f: Finding, strategy: Strategy | None) -> tuple[str, str] | None:
    if strategy is None:
        return MAX_WITHOUT_STRATEGY, "strategy_unknown"
    if f.action.get("type") != "decrease_bid":
        return None  # рычаг против CPA есть только у снижения ставки; остальные действия от стратегии не зависят
    return STRATEGY_ACTIONS[strategy][1], f"strategy_{strategy.value}"


def decide_v2(f: Finding, health: DataHealth = DataHealth(), strategy: Strategy | None = None) -> Decision:
    caps = [(MAX_BY_DATA[f.current_data_quality], f"data_sufficiency_{f.current_data_quality}")]
    if f.evidence_meta.get("level_reason") == PARTIAL_REASON:
        caps.append((MAX_PARTIAL, PARTIAL_REASON))
    if cap := _strategy_cap(f, strategy):
        caps.append(cap)
    if health.source_failed:
        caps.append((MAX_UNHEALTHY, "source_failed"))
    if health.stale:
        caps.append((MAX_UNHEALTHY, "source_stale"))
    return _lowered(f, tuple(caps), VERSION_V2)


def decide_active(f: Finding, health: DataHealth = DataHealth(), env=None,
                  strategy: Strategy | None = None) -> Decision:
    """Политика, которой аудит решает сейчас: по флагу safety_engine_v2 (app/flags.py), читается при каждом вызове.
    Версии правил (RULES, флаг source_of_truth_v2) выбираются при старте процесса из того же окружения: флаги
    независимы, допустима смесь правила @1 + политика @2 (политика только понижает уровень, метки @1 не меняются)."""
    return decide_v2(f, health, strategy) if flag("safety_engine_v2", env) else decide(f)
