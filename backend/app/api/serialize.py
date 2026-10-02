"""Представление для клиента (API_CONTRACT.md §1–2): идентификаторы — строки с префиксом, деньги — строки-числа,
Value — без snapshot_id и с period вместо period_from/period_to. Числа не пересчитываются: как сохранил аудит."""

from datetime import datetime
from decimal import Decimal

from app.contract import Value


def ext(prefix: str, value: int) -> str:
    return f"{prefix}_{value}"


def moment(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def value(raw: dict) -> dict:
    """Value из jsonb → контракт API. Проверка — той же моделью, что и при записи (app/contract.py)."""
    v = Value.model_validate(raw)
    amount = None if v.amount is None else format(Decimal(v.amount), "f")
    return {"amount": amount, "unit": v.unit, "calculation_type": v.calculation_type, "source": v.source,
            "period": {"from": v.period_from.isoformat(), "to": v.period_to.isoformat()},
            "data_status": v.data_status, "data_sufficiency": v.data_sufficiency,
            "formula": v.formula, "rule_version": v.rule_version}
