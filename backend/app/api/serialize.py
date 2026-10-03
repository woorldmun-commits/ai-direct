"""Представление для клиента (API_CONTRACT.md §1–2, §5): идентификаторы — строки с префиксом, деньги — строки-числа,
Value — без snapshot_id и с period вместо period_from/period_to. Числа не пересчитываются: как сохранил аудит."""

import logging
from datetime import datetime
from decimal import Decimal

from app.api.active import Card
from app.audit.present import present_action, title
from app.contract import Value

log = logging.getLogger("app.api")


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


def action(raw: dict, meta: dict, level: str, topic: str) -> dict | None:
    """Действие для человека, согласованное с уровнем политики (app/audit/present.py, API_CONTRACT §5). Сохранённая
    форма, которую код больше не понимает (старая версия правила, повреждённая запись), не роняет весь список:
    у карточки action = null, в лог — предупреждение с id вывода вызывающего."""
    try:
        return present_action(raw, level, topic, meta)
    except (ValueError, KeyError, TypeError, ArithmeticError) as e:
        log.warning("action outside contract: %s (%s)", type(e).__name__, e)
        return None


def recommendation_item(card: Card, overlap: Value) -> dict:
    """RecommendationListItem (API_CONTRACT.md §5). computed_at — когда посчитана текущая версия (findings.created_at);
    exposure_overlap — часть exposure, уже учтённая другой карточкой (exposure_total@1, разложение по карточкам)."""
    act = action(card.action_raw, card.meta, card.action_level, card.issue_type)
    if act is None:
        log.warning("recommendation %s, finding %s: action = null", card.rec_id, card.finding_id)
    return {"id": ext("rec", card.rec_id), "version_id": ext("rv", card.finding_id),
            "title": title(card.issue_type, card.object_type, card.object_id, card.meta,
                           insufficient=card.insufficient),
            "ad_account": {"id": ext("acc", card.account_id), "login": card.login},
            "object": {"type": card.object_type, "id": str(card.object_id), "name": None},
            "status": card.status, "execution_mode": None, "verification_status": None,
            "action_level": card.action_level, "action": act,
            "exposure": value_of(card.lost), "exposure_overlap": value_of(overlap),
            "can_save": value_of(card.recoverable),
            "data_status": card.lost.data_status, "data_sufficiency": card.lost.data_sufficiency,
            "period": {"from": card.lost.period_from.isoformat(), "to": card.lost.period_to.isoformat()},
            "computed_at": moment(card.computed_at), "created_at": moment(card.created_at),
            "updated_at": moment(card.updated_at)}
