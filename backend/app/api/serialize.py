"""Представление для клиента (API_CONTRACT.md §1–2, §5): идентификаторы — строки с префиксом, деньги — строки-числа,
Value — без snapshot_id и с period вместо period_from/period_to. Числа не пересчитываются: как сохранил аудит."""

from datetime import datetime
from decimal import Decimal

from app.contract import Value
from app.rules.zero_conv_campaign import CHECKS

CENT = Decimal("0.01")
# Действия трёх правил v1.0 (API_CONTRACT.md §5). Что человек делает в кабинете сам: execution всегда manual.
SUGGESTIONS = ("set_target_cpa",)


def ext(prefix: str, value: int) -> str:
    return f"{prefix}_{value}"


def moment(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def value(raw: dict) -> dict:
    """Value из jsonb → контракт API. Проверка — той же моделью, что и при записи (app/contract.py); записи до
    миграции 0004 без причины unavailable читаются через Value.from_stored."""
    return value_of(Value.from_stored(raw))


def value_of(v: Value) -> dict:
    """Value бэкенда → контракт API: без snapshot_id, period вместо period_from / period_to."""
    amount = None if v.amount is None else format(Decimal(v.amount), "f")
    return {"amount": amount, "unit": v.unit, "calculation_type": v.calculation_type, "source": v.source,
            "period": {"from": v.period_from.isoformat(), "to": v.period_to.isoformat()},
            "data_status": v.data_status, "data_sufficiency": v.data_sufficiency,
            "formula": v.formula, "rule_version": v.rule_version, "unavailable_reason": v.unavailable_reason}


def _suggest(raw: dict) -> str | None:
    s = raw.get("suggest")
    if s is not None and s not in SUGGESTIONS:
        raise ValueError(f"action.suggest: {s!r} вне контракта")
    return s


def action(raw: dict, meta: dict) -> dict:
    """findings.action (+ evidence_meta для имён площадок) → ровно одна из четырёх форм §5. Тип или параметры вне
    контракта — ошибка сервера, а не молча отданная клиенту незнакомая форма."""
    kind = raw.get("type")
    if kind == "decrease_bid":
        pct = Decimal(str(raw["change_pct"]))
        if not pct < 0:
            raise ValueError("decrease_bid: change_pct < 0")
        return {"type": kind, "execution": "manual", "change_pct": format(pct.quantize(CENT), "f")}
    if kind == "investigate_zero_conversions":
        checks = list(raw["check"])
        if not checks or any(c not in CHECKS for c in checks):
            raise ValueError(f"investigate_zero_conversions: checks вне контракта: {checks!r}")
        return {"type": kind, "execution": "manual", "checks": checks, "suggest": _suggest(raw)}
    if kind == "investigate_cpa_growth":
        return {"type": kind, "execution": "manual", "suggest": _suggest(raw)}
    if kind == "exclude_placements":
        ids = [int(pid) for pid in raw["placement_ids"]]
        if not ids or raw.get("execution", "manual") != "manual":
            raise ValueError("exclude_placements: нужны площадки, исполнение только ручное")
        # Имя — нормализованный домен или id приложения (sync/sanitize.py), не ПД: человек исключает площадку по
        # нему в Директе. Нет имени (маска «***», нет справочника) — null, UI пишет «имя недоступно».
        return {"type": kind, "execution": "manual", "placements_count": len(ids),
                "placements": [{"id": str(pid), "name": meta.get(f"placement_{pid}_name")} for pid in ids]}
    raise ValueError(f"action.type {kind!r} вне контракта v1.0")


def recommendation_item(rec: int, finding: int, account_id: int, login: str | None, object_type: str, object_id: int,
                        action_level: str, lost: dict, recoverable: dict, created_at: datetime,
                        updated_at: datetime, *, computed_at: datetime, action_raw: dict, meta: dict) -> dict:
    """RecommendationListItem (API_CONTRACT.md §5) — только поля, которые уже есть в схеме. computed_at — когда
    посчитана текущая версия (findings.created_at)."""
    return {"id": ext("rec", rec), "version_id": ext("rv", finding),
            "ad_account": {"id": ext("acc", account_id), "login": login},
            "object": {"type": object_type, "id": str(object_id)},
            "action_level": action_level, "action": action(action_raw, meta),
            "exposure": value(lost), "can_save": value(recoverable),
            "data_status": lost["data_status"],
            "period": {"from": lost["period_from"], "to": lost["period_to"]},
            "computed_at": moment(computed_at), "created_at": moment(created_at), "updated_at": moment(updated_at)}
