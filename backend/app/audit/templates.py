"""Шаблонное объяснение вывода — работает без LLM (ARCHITECTURE.md §6). Все числа — из Finding, ничего не добавляется.
Решение принимают правило (кандидат) и политика безопасности (уровень); здесь только текст. Изменение настроек
предлагается, только если политика его разрешила."""

from decimal import Decimal

from app.audit.policy import Decision
from app.rules.domain import Finding


def _rub(x: Decimal) -> str:
    return f"{x:,.0f}".replace(",", " ")


def _bid_advice(f: Finding, d: Decision) -> str:
    change = abs(f.action["change_pct"])
    if d.level == "inspect_only":
        conv = f.evidence["conversions"].amount
        return (f"Конверсий за период пока мало ({conv:,.0f}) для безопасного изменения ставки — продолжаем "
                "наблюдать. Проверьте, какие запросы и площадки дают расход без заявок.").replace(",", " ")
    if d.level == "review":
        return (f"Можно снизить ставку на {change}% — проверьте перед изменением, доступна ли ручная ставка "
                "в стратегии кампании.")
    return f"Рекомендуется снизить ставку на {change}%."


def explain(f: Finding, d: Decision) -> str:
    head = f"CPA кампании {f.object_id} — {_rub(f.actual)} ₽"
    if f.reason_code == "cpa_above_target":
        return f"{head}, это на {f.delta_pct}% выше целевого CPA {_rub(f.reference)} ₽. {_bid_advice(f, d)}"
    if f.reason_code == "cpa_above_baseline":
        return (f"{head}, это на {f.delta_pct}% выше исторического базового уровня {_rub(f.reference)} ₽. "
                "Проверьте причину роста и укажите целевой CPA — оценка станет точнее.")
    return f"{f.metric} = {f.actual}, ориентир {f.reference} ({f.reference_type}), отклонение {f.delta_pct}%."
