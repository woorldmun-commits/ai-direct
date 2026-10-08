"""Достаточность данных (§19) и уровень действия (§20 ТЗ). Уровень можно только понижать.

Словарь БД (findings.action_level: inspect_only/review/change, data_quality: high/medium/low,
Value.data_sufficiency: sufficient/insufficient) переводится явными функциями; неизвестное значение — ValueError."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.intelligence.contracts._validate import check_text


class DataSufficiency(str, Enum):
    INSUFFICIENT = "insufficient"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionLevel(str, Enum):
    NO_ACTION = "no_action"
    INSPECT_ONLY = "inspect_only"
    REVIEW = "review"
    CHANGE_CANDIDATE = "change_candidate"

    @property
    def rank(self) -> int:
        return _ORDER.index(self)


_ORDER = (ActionLevel.NO_ACTION, ActionLevel.INSPECT_ONLY, ActionLevel.REVIEW, ActionLevel.CHANGE_CANDIDATE)
_LEVEL_FOR = dict(zip(DataSufficiency, _ORDER))  # порядок членов Enum совпадает с §20


def level_for(sufficiency: DataSufficiency) -> ActionLevel:
    return _LEVEL_FOR[sufficiency]


def lowered(a: ActionLevel, b: ActionLevel) -> ActionLevel:
    """Меньший из двух уровней: результат никогда не выше ни одного из аргументов."""
    return a if a.rank <= b.rank else b


def _count(name: str, value: int | None) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise ValueError(f"{name}: ожидается целое >= 0")


@dataclass(frozen=True)
class SufficiencyAssessment:
    """Оценка достаточности с обязательной причиной и фактами, на которых она стоит."""
    level: DataSufficiency
    reason: str
    days: int | None = None
    clicks: int | None = None
    conversions: Decimal | None = None

    def __post_init__(self):
        if not isinstance(self.level, DataSufficiency):
            raise ValueError("level: ожидается DataSufficiency")
        check_text("reason", self.reason)
        _count("days", self.days)
        _count("clicks", self.clicks)
        if self.conversions is not None and (not isinstance(self.conversions, Decimal)
                                             or not self.conversions.is_finite() or self.conversions < 0):
            raise ValueError("conversions: ожидается конечный Decimal >= 0")

    @property
    def action_level(self) -> ActionLevel:
        return level_for(self.level)


def _pair(table: dict, key, what: str):
    try:
        return table[key]
    except (KeyError, TypeError):
        raise ValueError(f"{what}: неизвестное значение {key!r}") from None


_LEGACY_ACTION = {"inspect_only": ActionLevel.INSPECT_ONLY, "review": ActionLevel.REVIEW,
                  "change": ActionLevel.CHANGE_CANDIDATE}
_LEGACY_QUALITY = {"low": DataSufficiency.LOW, "medium": DataSufficiency.MEDIUM, "high": DataSufficiency.HIGH}


def from_legacy_action_level(value: str) -> ActionLevel:
    return _pair(_LEGACY_ACTION, value, "action_level")


def _to_legacy(table: dict, key, cls: type, what: str):
    """str-Enum равен своей строке, поэтому тип проверяется отдельно: «review» вместо ActionLevel — ошибка."""
    if not isinstance(key, cls):
        raise ValueError(f"{what}: ожидается {cls.__name__}, получено {key!r}")
    return _pair(table, key, what)


def to_legacy_action_level(level: ActionLevel) -> str:
    return _to_legacy({v: k for k, v in _LEGACY_ACTION.items()}, level, ActionLevel,
                      "action_level (в БД нет такого уровня)")


def from_legacy_data_quality(value: str) -> DataSufficiency:
    return _pair(_LEGACY_QUALITY, value, "data_quality")


def to_legacy_data_quality(level: DataSufficiency) -> str:
    return _to_legacy({v: k for k, v in _LEGACY_QUALITY.items()}, level, DataSufficiency,
                      "data_quality (в БД нет такого уровня)")


def to_legacy_data_sufficiency(level: DataSufficiency) -> str:
    table = {DataSufficiency.INSUFFICIENT: "insufficient", DataSufficiency.LOW: "sufficient",
             DataSufficiency.MEDIUM: "sufficient", DataSufficiency.HIGH: "sufficient"}
    return _to_legacy(table, level, DataSufficiency, "data_sufficiency")


def from_legacy_data_sufficiency(sufficiency: str, data_quality: str | None) -> DataSufficiency:
    """«sufficient» не говорит об уровне: он берётся из data_quality, угадывать нельзя."""
    if sufficiency == "insufficient":
        return DataSufficiency.INSUFFICIENT
    if sufficiency == "sufficient":
        return from_legacy_data_quality(data_quality)
    raise ValueError(f"data_sufficiency: неизвестное значение {sufficiency!r}")
