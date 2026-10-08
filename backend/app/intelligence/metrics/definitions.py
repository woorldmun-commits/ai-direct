"""Реестр метрик в коде (metric_definitions@1): откуда берётся число, на каком уровне и по какому определению.

Правило не решает, какой источник у метрики, — оно берёт метку отсюда. Конверсии и CPA по кампаниям, фразам и
площадкам считает Директ (Reports API): цели и модель атрибуции задаются в запросе и замораживаются в снимке
(snapshots.conversion_definition), поэтому источник — yandex_direct, а не Метрика, хотя цели — цели Метрики.
Чистый модуль: ни БД, ни окружения, ни сети. Любое изменение определения — новая версия реестра."""

from dataclasses import dataclass

VERSION = "metric_definitions@1"
# Конверсии по целям складываются: визит с двумя целями даёт две конверсии (sync/parse.py).
_GOALS = "snapshot.conversion_definition.goal_ids"
_ATTRIBUTION = "snapshot.conversion_definition.attribution"
_LEVELS = ("campaign", "placement", "query")


@dataclass(frozen=True)
class MetricDefinition:
    metric: str
    provider: str                    # откуда запрашиваем
    object_level: tuple[str, ...]    # на каких уровнях отчёта определение действует
    source_of_truth: str             # метка источника у Value / Fact (contract.SOURCES)
    attribution_model: str | None    # None: метрика не зависит от атрибуции
    goal_definition: str | None      # None: метрика не зависит от целей
    formula: str
    empty_cell_semantics: str | None = None  # что значит пустая ячейка отчёта провайдера (решение владельца)
    version: str = VERSION


# Решение владельца: «--» в столбце Conversions_* Директа — 0 конверсий за день по цели (sync/parse.py), не «нет данных».
_DASH_IS_ZERO = "'--' в столбце конверсий Директа = 0 конверсий"


def _direct(metric: str, formula: str, *, conversion: bool = False) -> MetricDefinition:
    return MetricDefinition(metric, "yandex_direct", _LEVELS, "yandex_direct", _ATTRIBUTION if conversion else None,
                            _GOALS if conversion else None, formula, _DASH_IS_ZERO if metric == "conversions" else None)


DEFINITIONS: dict[str, MetricDefinition] = {d.metric: d for d in (
    _direct("cost", "sum(Cost) за период"),
    _direct("clicks", "sum(Clicks) за период"),
    _direct("impressions", "sum(Impressions) за период"),
    _direct("conversions", "sum(Conversions_<goal>_<attribution>) по goal_ids снимка", conversion=True),
    _direct("cpa", "cost / conversions", conversion=True),
    _direct("cr", "conversions / clicks * 100", conversion=True),
)}


def source_of_truth(metric: str) -> str:
    """Метка источника метрики. Неизвестная метрика — KeyError, а не молчаливое умолчание."""
    return DEFINITIONS[metric].source_of_truth
