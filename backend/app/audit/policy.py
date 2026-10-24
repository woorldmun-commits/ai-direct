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
- неизвестный тип действия → inspect_only: новое правило не может обойти политику."""

from dataclasses import dataclass

from app.rules.domain import Finding

VERSION = "safety_policy@1"
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


@dataclass(frozen=True)
class Decision:
    candidate_level: str
    level: str
    reasons: tuple[str, ...]  # почему понижено; пусто ⇔ level == candidate_level
    version: str = VERSION


def _rank(level: str) -> int:
    return LEVELS.index(level)


def decide(f: Finding) -> Decision:
    candidate = CANDIDATE_LEVEL.get(f.action["type"])
    if candidate is None:
        return Decision("inspect_only", "inspect_only", ())  # неизвестное действие изменений не предлагает
    caps = ((MAX_BY_DATA[f.current_data_quality], f"data_sufficiency_{f.current_data_quality}"),
            (MAX_WITHOUT_STRATEGY, "strategy_unknown"))
    level, reasons = candidate, []
    for cap, reason in caps:
        if _rank(cap) < _rank(candidate):
            reasons.append(reason)
            level = min(level, cap, key=_rank)
    return Decision(candidate, level, tuple(reasons))


def decide_with_strategy(f: Finding, strategy: str) -> Decision:
    """v2: only a known compatible strategy can permit a manual setting change."""
    from app.sources.campaigns import STRATEGY_ACTIONS, Strategy
    candidate = CANDIDATE_LEVEL.get(f.action['type'], 'inspect_only')
    try:
        known = Strategy(strategy)
    except ValueError:
        known = Strategy.UNKNOWN
    caps = [(MAX_BY_DATA[f.current_data_quality], f'data_sufficiency_{f.current_data_quality}')]
    if f.action['type'] == 'decrease_bid':
        lever, cap = STRATEGY_ACTIONS[known]
        caps.append((cap if lever == 'change_bid' else 'inspect_only',
                     'strategy_unknown' if known is Strategy.UNKNOWN else 'strategy_action_incompatible'))
    elif f.action['type'] == 'exclude_placements' and known in (Strategy.UNKNOWN, Strategy.UNSUPPORTED, Strategy.SERVING_OFF):
        caps.append(('inspect_only', 'strategy_unknown' if known is Strategy.UNKNOWN else 'strategy_action_incompatible'))
    level = min([candidate, *(cap for cap, _ in caps)], key=_rank)
    return Decision(candidate, level, tuple(reason for cap, reason in caps if _rank(cap) < _rank(candidate)),
                    version='safety_policy@2')
