"""Доменный слой rule engine: неизменяемые входы и выходы правил (docs/ARCHITECTURE.md §4).

Правило = чистая функция (SnapshotView, AuditSettings, params) -> tuple[Output, ...].
Здесь нет БД, Pydantic, сети, текущего времени и глобального состояния — один вход всегда даёт один выход.
Перевод в Value / строки БД / текст объяснения — следующие слои (audit/, ai/), не правила."""

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Callable, Literal, Mapping

Source = Literal["yandex_direct", "yandex_metrika", "user_input"]
DataQuality = Literal["high", "medium", "low"]

EVALUATION_DAYS = 7
BASELINE_DAYS = 30
HISTORY_DAYS = EVALUATION_DAYS + BASELINE_DAYS  # 37: столько грузит каждая синхронизация

# Действия, меняющие ставку или бюджет. Baseline-режим и «недостаточно данных» не выдают их никогда.
# Не API-источник, а возможность: в отчёте Директа есть конверсии Метрики по кампаниям. Её требуют CPA-правила —
# отказ отдельного API Метрики не выключает CPA, если Директ конверсии отдал.
DIRECT_CONVERSIONS = "direct_conversions"

BID_OR_BUDGET_ACTIONS = frozenset({"decrease_bid", "increase_bid", "change_budget", "pause"})


def frozen(d: Mapping) -> Mapping:
    return MappingProxyType(dict(d))


# --- Вход -----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class CampaignDay:
    campaign_id: int
    date: date
    cost: Decimal
    clicks: int
    conversions: Decimal | None  # None: Метрика не подключена


@dataclass(frozen=True)
class SnapshotView:
    snapshot_id: int
    workspace_id: int
    direct_account_id: int
    period_from: date
    period_to: date
    sources: frozenset[str]  # API-источники и возможности (DIRECT_CONVERSIONS)
    campaign_days: tuple[CampaignDay, ...]


@dataclass(frozen=True)
class AuditSettings:
    """Замороженная копия настроек workspace на момент аудита (audit_runs.settings)."""
    target_cpa: Decimal | None = None

    def __post_init__(self):
        if self.target_cpa is not None and self.target_cpa <= 0:  # то же, что CHECK в workspace_settings
            raise ValueError("target_cpa > 0")


@dataclass(frozen=True)
class Window:
    date_from: date
    date_to: date

    def __contains__(self, d: date) -> bool:
        return self.date_from <= d <= self.date_to


def windows(period_to: date) -> tuple[Window, Window]:
    """(оцениваемый период, baseline). Последние 7 дней и 30 дней перед ними — без пересечения."""
    evaluation = Window(period_to - timedelta(EVALUATION_DAYS - 1), period_to)
    baseline = Window(evaluation.date_from - timedelta(BASELINE_DAYS), evaluation.date_from - timedelta(1))
    return evaluation, baseline


# --- Выход ----------------------------------------------------------------------------------------

class Reason(str, Enum):
    """Структурированная причина «недостаточно данных» — не текст объяснения."""
    SOURCE_MISSING = "source_missing"
    NO_CONVERSIONS = "no_conversions"
    BASELINE_HISTORY_INSUFFICIENT = "baseline_history_insufficient"
    BASELINE_DATA_INSUFFICIENT = "baseline_data_insufficient"
    VOLUME_INSUFFICIENT = "volume_insufficient"  # расход/клики ниже порога «достаточного объёма» правила


@dataclass(frozen=True)
class Fact:
    """Одно число доказательства. Слой audit/ превращает его в Value (добавляя snapshot_id, data_status)."""
    amount: Decimal
    unit: Literal["rub", "count", "pct"]
    source: str
    period: Window
    calculation_type: Literal["actual", "estimated"] = "actual"
    formula: str | None = None


def issue_key(workspace_id: int, direct_account_id: int, issue_type: str,
              object_type: str, object_id: int, dimension: str = "") -> bytes:
    """Стабильный ключ проблемы — только из нормализованных ID (DATA_MODEL.md §4), никогда из текста."""
    parts = (workspace_id, direct_account_id, issue_type, object_type, object_id, dimension)
    return hashlib.sha256("|".join(map(str, parts)).encode()).digest()


@dataclass(frozen=True)
class Finding:
    rule_version: str
    issue_type: str
    object_type: str
    object_id: int
    issue_key: bytes
    reason_code: str
    metric: str
    actual: Decimal
    reference: Decimal
    reference_type: Literal["target", "baseline", "absolute"]  # absolute: порог-параметр версии, без CPA
    delta_pct: Decimal
    lost: Fact
    recoverable: Fact
    current_data_quality: DataQuality  # достаточность данных текущего периода — не статистическая уверенность
    evidence: Mapping[str, Fact]
    evidence_meta: Mapping[str, str]
    action: Mapping[str, object]


@dataclass(frozen=True)
class NotEnoughData:
    rule_version: str
    reason: Reason
    object_type: str | None = None  # None: правило не вычислялось для всего аккаунта
    object_id: int | None = None


Output = Finding | NotEnoughData


# --- Правило --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    id: str
    version: int
    family: str  # семейство проблемы = issue_type; issue_key не зависит ни от id, ни от версии правила
    required_sources: frozenset[str]
    params: Mapping[str, object]
    evaluate: Callable[["Rule", SnapshotView, AuditSettings], tuple[Output, ...]] = field(repr=False)
    # Применима ли версия при этих настройках (например, target- или baseline-режим). Неприменимая молчит.
    applies: Callable[[AuditSettings], bool] = field(default=lambda settings: True, repr=False)

    @property
    def rule_version(self) -> str:
        return f"{self.id}@{self.version}"


def run(rule: Rule, snapshot: SnapshotView, settings: AuditSettings) -> tuple[Output, ...]:
    """Единственный вход в правило: нет нужного источника → правило не вычисляется вовсе."""
    if not rule.applies(settings):
        return ()
    if not rule.required_sources <= snapshot.sources:
        return (NotEnoughData(rule.rule_version, Reason.SOURCE_MISSING),)
    return rule.evaluate(rule, snapshot, settings)
