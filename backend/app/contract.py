"""Контракт Value (docs/ARCHITECTURE.md §3, DATA_MODEL.md §5). Любое число в системе проходит через эту модель.
Те же инварианты продублированы в SQL: value_is_valid() в db/schema.sql. Согласованность держит tests/test_value_contract.py."""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

SOURCES = ("yandex_direct", "yandex_metrika", "user_input")
# Почему числа нет (calculation_type = unavailable) — закрытый список; тот же, что rules.domain.UnavailableReason.
UnavailableReason = Literal["source_missing", "no_conversions", "history_insufficient", "volume_insufficient",
                            "no_forecast", "no_data"]
UNAVAILABLE_REASONS: tuple[str, ...] = get_args(UnavailableReason)
# Value, записанные до 0004 (без unavailable_reason), читаются с этой причиной: другой в записи нет.
LEGACY_UNAVAILABLE_REASON = "no_data"
# Везде fullmatch и [0-9], как в SQL: «$» в Python совпадает перед завершающим переводом строки,
# а «\d» — с цифрами любого письма.
_SOURCE_RE = re.compile(rf"({'|'.join(SOURCES)})(\+({'|'.join(SOURCES)}))*")
_RULE_VERSION_RE = re.compile(r"[a-z0-9_]+@[0-9]+")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_NUMBER_RE = re.compile(r"-?[0-9]+(\.[0-9]+)?")


class Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: Decimal | None
    unit: Literal["rub", "count", "pct"]
    source: str
    period_from: date
    period_to: date
    calculation_type: Literal["actual", "estimated", "unavailable"]
    data_status: Literal["complete", "partial"]
    data_sufficiency: Literal["sufficient", "insufficient"]
    snapshot_id: Annotated[StrictInt, Field(strict=True, ge=0)]
    rule_version: str | None = None
    formula: str | None = None
    unavailable_reason: UnavailableReason | None = None

    @classmethod
    def from_stored(cls, raw) -> "Value":
        """Value из jsonb. До миграции 0004 причины unavailable не писали, а строки неизменяемы (append-only): такое
        значение читается с LEGACY_UNAVAILABLE_REASON. Новая запись без причины не пройдёт модель; SQL (value_is_valid)
        причину не требует только ради старых строк, но проверяет её значение и что она есть лишь у unavailable."""
        if (isinstance(raw, dict) and raw.get("calculation_type") == "unavailable"
                and raw.get("unavailable_reason") is None):
            raw = {**raw, "unavailable_reason": LEGACY_UNAVAILABLE_REASON}
        return cls.model_validate(raw)

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, x):
        if x is None:
            return x
        if isinstance(x, bool) or not isinstance(x, (int, str, Decimal)):
            raise ValueError("amount: ожидается Decimal, строка или целое (float теряет точность денег)")
        # Decimal — в позиционной записи: иначе Decimal("1E+2") ушёл бы в jsonb строкой «1E+2», которую SQL отвергнет
        s = format(x, "f") if isinstance(x, Decimal) and x.is_finite() else str(x)
        if not _NUMBER_RE.fullmatch(s):
            raise ValueError("amount: не десятичное число")
        return Decimal(s)

    @field_validator("period_from", "period_to", mode="before")
    @classmethod
    def _iso_date(cls, x):
        if isinstance(x, date):
            return x
        if not isinstance(x, str) or not _DATE_RE.fullmatch(x):
            raise ValueError("дата: ожидается строка YYYY-MM-DD")
        return x

    @field_validator("source")
    @classmethod
    def _source(cls, x):
        if not _SOURCE_RE.fullmatch(x):
            raise ValueError(f"source: допустимы {SOURCES}, объединённые через '+'")
        return x

    @field_validator("rule_version")
    @classmethod
    def _rule_version(cls, x):
        if x is not None and not _RULE_VERSION_RE.fullmatch(x):
            raise ValueError("rule_version: ожидается имя@номер")
        return x

    @model_validator(mode="after")
    def _invariants(self):
        unavailable = self.calculation_type == "unavailable"
        # insufficient ⇔ unavailable ⇔ amount is None
        if not (unavailable == (self.data_sufficiency == "insufficient") == (self.amount is None)):
            raise ValueError("insufficient ⇔ unavailable ⇔ amount is None")
        if unavailable == (self.unavailable_reason is None):
            raise ValueError("unavailable ⇔ unavailable_reason задан")
        if self.calculation_type == "estimated" and not self.formula:
            raise ValueError("estimated ⇒ formula обязательна")
        if self.period_from > self.period_to:
            raise ValueError("period_from > period_to")
        return self
