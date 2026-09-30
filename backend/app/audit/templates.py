"""Шаблонное объяснение вывода — работает без LLM (ARCHITECTURE.md §6). Все числа — из Finding, ничего не добавляется.
Решение принимает правило; здесь только текст."""

from decimal import Decimal

from app.rules.domain import Finding


def _rub(x: Decimal) -> str:
    return f"{x:,.0f}".replace(",", " ")


def explain(f: Finding) -> str:
    head = f"CPA кампании {f.object_id} — {_rub(f.actual)} ₽"
    if f.reason_code == "cpa_above_target":
        return (f"{head}, это на {f.delta_pct}% выше целевого CPA {_rub(f.reference)} ₽. "
                f"Рекомендуется снизить ставку на {abs(f.action['change_pct'])}%.")
    if f.reason_code == "cpa_above_baseline":
        return (f"{head}, это на {f.delta_pct}% выше исторического базового уровня {_rub(f.reference)} ₽. "
                "Проверьте причину роста и укажите целевой CPA — оценка станет точнее.")
    return f"{f.metric} = {f.actual}, ориентир {f.reference} ({f.reference_type}), отклонение {f.delta_pct}%."
