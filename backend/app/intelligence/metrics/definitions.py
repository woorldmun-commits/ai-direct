"""Реестр метрик в коде (metric_definitions@1): откуда берётся число, на каком уровне и по какому определению.

Правило не решает, какой источник у метрики, — оно берёт метку отсюда. Два разных понятия:
- source_of_truth (источник получения) — откуда AdPilot берёт каноническое число для расчётов. Для всех метрик это
  отчёт Директа (Reports API); эта метка стоит в Fact.source / Value.source;
- measurement_source (источник измерения) — кто измерил величину. Расход, клики, показы измеряет сам Директ, а
  конверсии в отчёте Директа (Conversions_<цель>_<модель>) — данные Метрики, доставленные через Директ; CPA и CR
  наследуют это от конверсий.
Цели и модель атрибуции задаются в запросе и замораживаются в снимке (snapshots.conversion_definition).
Metric Registry v2 добавляет к определению (аддитивно, VERSION реестра прежний): owner, required_fields,
minimum_data (минимум, чтобы число ВООБЩЕ считалось, а не достаточность для действия — её решает Safety),
channel_scope, value_type, unavailable_reasons и версию метрики (metric_version, например cpa@1).
Чистый модуль: ни БД, ни окружения, ни сети. Любое изменение определения — новая версия реестра."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Collection

VERSION = "metric_definitions@1"
# Конверсии по целям складываются: визит с двумя целями даёт две конверсии (sync/parse.py).
_GOALS = "snapshot.conversion_definition.goal_ids"
_ATTRIBUTION = "snapshot.conversion_definition.attribution"
_LEVELS = ("campaign", "placement", "query")


@dataclass(frozen=True)
class MinimumData:
    """Минимум для расчёта числа. None — ограничения нет."""
    min_conversions: int | None = None


@dataclass(frozen=True)
class MetricDefinition:
    metric: str
    provider: str                    # откуда запрашиваем
    object_level: tuple[str, ...]    # на каких уровнях отчёта определение действует
    source_of_truth: str             # источник получения: откуда берём число для расчётов (метка Value / Fact)
    measurement_source: str          # источник измерения: кто измерил величину (у конверсий — Метрика)
    attribution_model: str | None    # None: метрика не зависит от атрибуции
    goal_definition: str | None      # None: метрика не зависит от целей
    formula: str
    empty_cell_semantics: str | None = None  # что значит пустая ячейка отчёта провайдера (решение владельца)
    version: str = VERSION
    metric_version: str = ""         # версия самой метрики (cpa@1); версии набора пишутся в analysis_run
    owner: str = "metrics"
    required_fields: tuple[str, ...] = ()
    minimum_data: MinimumData = MinimumData()
    channel_scope: str = "all"       # search | network | all; поиск и сеть в один KPI не смешиваются
    value_type: str = "actual"       # actual | calculated | estimated
    unavailable_reasons: tuple[str, ...] = ()  # подмножество contract.UNAVAILABLE_REASONS


# «--» в столбце Conversions_* = 0 конверсий — принятое решение парсера AdPilot (зафиксировано тестом), не гарантия
# API Яндекса (sync/parse.py). Для Impressions / Clicks / Cost «--» — ошибка формата.
_DASH_IS_ZERO = ("'--' в столбце конверсий = 0 конверсий: принятое решение парсера AdPilot (зафиксировано тестом), "
                 "не гарантия API Яндекса")


def _direct(metric: str, formula: str, fields: tuple[str, ...], reasons: tuple[str, ...], *,
            conversion: bool = False, calculated: bool = False, min_conversions: int | None = None) -> MetricDefinition:
    return MetricDefinition(metric, "yandex_direct", _LEVELS, "yandex_direct",
                            "yandex_metrika" if conversion else "yandex_direct",
                            _ATTRIBUTION if conversion else None, _GOALS if conversion else None, formula,
                            _DASH_IS_ZERO if metric == "conversions" else None,
                            metric_version=f"{metric}@1", required_fields=fields,
                            minimum_data=MinimumData(min_conversions),
                            value_type="calculated" if calculated else "actual", unavailable_reasons=reasons)


_MISSING = ("source_missing", "no_data")
DEFINITIONS: dict[str, MetricDefinition] = {d.metric: d for d in (
    _direct("cost", "sum(Cost) за период", ("cost",), _MISSING),
    _direct("clicks", "sum(Clicks) за период", ("clicks",), _MISSING),
    _direct("impressions", "sum(Impressions) за период", ("impressions",), _MISSING),
    _direct("conversions", "sum(Conversions_<goal>_<attribution>) по goal_ids снимка", ("conversions",), _MISSING,
            conversion=True),
    _direct("cpa", "cost / conversions", ("cost", "conversions"), ("source_missing", "no_conversions", "no_data"),
            conversion=True, calculated=True, min_conversions=1),
    _direct("cr", "conversions / clicks * 100", ("conversions", "clicks"), _MISSING, conversion=True,
            calculated=True),
)}


def source_of_truth(metric: str) -> str:
    """Метка источника метрики. Неизвестная метрика — KeyError, а не молчаливое умолчание."""
    return DEFINITIONS[metric].source_of_truth


def can_compute(metric: str, available_fields: Collection[str], conversions: Decimal | None) -> tuple[bool, str | None]:
    """(можно ли посчитать, причина «нет данных»). Не считает число: None — не 0, причина — из закрытого списка метрики.
    Неизвестная метрика — KeyError."""
    d = DEFINITIONS[metric]
    if not set(d.required_fields) <= set(available_fields):
        return False, "source_missing"
    need = d.minimum_data.min_conversions
    if need is not None:
        if conversions is None:
            return False, "source_missing"
        if not conversions.is_finite() or conversions < 0:
            return False, "source_missing"
        if conversions < need:
            return False, "no_conversions"
    return True, None
