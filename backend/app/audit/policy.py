"""Политика безопасных рекомендаций (ARCHITECTURE.md §4.1): rule engine → safety policy → рекомендация → одобрение
человека → изменение. Чистая функция, как правила; версия хранится в каждом finding рядом с rule_version.

Правило отвечает «что показывают данные и какое действие из этого следует» (кандидат). Политика — «вправе ли мы
сейчас его предлагать». Она может только понизить уровень действия, никогда не повысить (это проверяет и БД):

  inspect_only — показать проблему и факты, предложить что проверить; никаких изменений настроек;
  review       — предложить изменение для проверки человеком;
  change       — предложить изменение; и оно выполняется только после явного подтверждения человека.

safety_policy@1:
- достаточность данных текущего периода: low (1–2 конверсии) → inspect_only, medium → review, high → change;
- стратегия кампании пока неизвестна (данных Campaigns.get в снимке нет) → не выше review: ручная ставка может
  быть недоступна на автостратегии. Проверка совместимости стратегии — safety_policy@2;
- неизвестный тип действия → inspect_only: новое правило не может обойти политику.

safety_policy@2 — всё из @1 и дополнительно (только понижает):
- конверсии вывода за дни досчёта (evidence_meta.level_reason = conversions_partial) → не выше review;
- источник данных упал (DataHealth.source_failed) или данные устарели (DataHealth.stale) → inspect_only.
DataHealth пока не поставляет ни один воркер (в SnapshotView нет ни source_failures, ни свежести): по умолчанию оба поля
None = «неизвестно» и не понижают уровень — неизвестное не выдаётся ни за хорошее, ни за плохое. Подключение — отдельным шагом."""

from dataclasses import dataclass

from app.flags import flag
from app.rules.domain import Finding

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


def decide_v2(f: Finding, health: DataHealth = DataHealth()) -> Decision:
    caps = [(MAX_BY_DATA[f.current_data_quality], f"data_sufficiency_{f.current_data_quality}")]
    if f.evidence_meta.get("level_reason") == "conversions_partial":
        caps.append((MAX_PARTIAL, "conversions_partial"))
    caps.append((MAX_WITHOUT_STRATEGY, "strategy_unknown"))
    if health.source_failed:
        caps.append((MAX_UNHEALTHY, "source_failed"))
    if health.stale:
        caps.append((MAX_UNHEALTHY, "source_stale"))
    return _lowered(f, tuple(caps), VERSION_V2)


def decide_active(f: Finding, health: DataHealth = DataHealth()) -> Decision:
    """Политика, которой аудит решает сейчас: по флагу safety_engine_v2 (app/flags.py)."""
    return decide_v2(f, health) if flag("safety_engine_v2") else decide(f)
