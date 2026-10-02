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
    return value_of(Value.model_validate(raw))


def value_of(v: Value) -> dict:
    """Value бэкенда → контракт API: без snapshot_id, period вместо period_from / period_to."""
    amount = None if v.amount is None else format(Decimal(v.amount), "f")
    return {"amount": amount, "unit": v.unit, "calculation_type": v.calculation_type, "source": v.source,
            "period": {"from": v.period_from.isoformat(), "to": v.period_to.isoformat()},
            "data_status": v.data_status, "data_sufficiency": v.data_sufficiency,
            "formula": v.formula, "rule_version": v.rule_version}


def recommendation_item(rec: int, finding: int, account_id: int, login: str | None, object_type: str, object_id: int,
                        action_level: str, lost: dict, recoverable: dict, created_at: datetime,
                        updated_at: datetime) -> dict:
    """RecommendationListItem (API_CONTRACT.md §5) — только поля, которые уже есть в схеме."""
    return {"id": ext("rec", rec), "version_id": ext("rv", finding),
            "ad_account": {"id": ext("acc", account_id), "login": login},
            "object": {"type": object_type, "id": str(object_id)},
            "action_level": action_level, "exposure": value(lost), "can_save": value(recoverable),
            "data_status": lost["data_status"],
            "period": {"from": lost["period_from"], "to": lost["period_to"]},
            "created_at": moment(created_at), "updated_at": moment(updated_at)}
