"""Fact правила → Value контракта. Здесь добавляется то, чего правило знать не должно: snapshot_id и data_status."""

from datetime import date

from app.contract import Value
from app.rules.domain import Fact


def to_value(fact: Fact, snapshot_id: int, partial_from: date, rule_version: str | None = None) -> Value:
    return Value(
        amount=fact.amount, unit=fact.unit, source=fact.source,
        period_from=fact.period.date_from, period_to=fact.period.date_to,
        calculation_type=fact.calculation_type,
        data_status="partial" if fact.period.date_to >= partial_from else "complete",
        data_sufficiency="insufficient" if fact.calculation_type == "unavailable" else "sufficient",
        snapshot_id=snapshot_id, rule_version=rule_version, formula=fact.formula, unavailable_reason=fact.reason,
    )
