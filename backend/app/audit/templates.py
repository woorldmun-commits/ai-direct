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


_ZERO_CONV_REFERENCE = {
    "target_cpa": ("target_cpa", "целевого CPA"),
    "campaign_baseline": ("baseline_cpa", "CPA кампании за прошлые 30 дней"),
    "account_baseline": ("account_baseline_cpa", "CPA аккаунта за прошлые 30 дней"),
}


def _zero_conv(f: Finding) -> str:
    """Числа — только из Finding: расход, клики, порог и CPA-ориентир из доказательств."""
    ev = f.evidence
    text = (f"Кампания {f.object_id} потратила {_rub(f.actual)} ₽ ({_rub(ev['clicks'].amount)} кликов) за период "
            f"и не получила ни одной конверсии. Порог достаточного объёма — {_rub(f.reference)} ₽")
    if (ref := _ZERO_CONV_REFERENCE.get(f.evidence_meta.get("reference_source"))) and ref[0] in ev:
        text += f", рассчитан от {ref[1]} {_rub(ev[ref[0]].amount)} ₽"
    text += (". Проверьте: учитываются ли цели и конверсии Метрики в кампании, стратегию и её цель, поисковые "
             "запросы и минус-фразы.")
    if f.action.get("suggest") == "set_target_cpa":
        text += " Укажите целевой CPA — порог станет точнее."
    return text


def explain(f: Finding, d: Decision) -> str:
    if f.reason_code == "zero_conversions":
        return _zero_conv(f)
    head = f"CPA кампании {f.object_id} — {_rub(f.actual)} ₽"
    if f.reason_code == "cpa_above_target":
        return f"{head}, это на {f.delta_pct}% выше целевого CPA {_rub(f.reference)} ₽. {_bid_advice(f, d)}"
    if f.reason_code == "cpa_above_baseline":
        return (f"{head}, это на {f.delta_pct}% выше исторического базового уровня {_rub(f.reference)} ₽. "
                "Проверьте причину роста и укажите целевой CPA — оценка станет точнее.")
    return f"{f.metric} = {f.actual}, ориентир {f.reference} ({f.reference_type}), отклонение {f.delta_pct}%."
