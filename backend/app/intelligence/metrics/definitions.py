"""Реестр метрик в коде (metric_definitions@1): откуда берётся число, на каком уровне и по какому определению.

Правило не решает, какой источник у метрики, — оно берёт метку отсюда. Два разных понятия:
- source_of_truth (источник получения) — откуда AdPilot берёт каноническое число для расчётов. Для всех метрик это
  отчёт Директа (Reports API); эта метка стоит в Fact.source / Value.source;
- measurement_source (источник измерения) — кто измерил величину. Расход, клики, показы измеряет сам Директ, а
  конверсии в отчёте Директа (Conversions_<цель>_<модель>) — данные Метрики, доставленные через Директ; CPA и CR
  наследуют это от конверсий.
Цели и модель атрибуции задаются в запросе и замораживаются в снимке (snapshots.conversion_definition).
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
    source_of_truth: str             # источник получения: откуда берём число для расчётов (метка Value / Fact)
    measurement_source: str          # источник измерения: кто измерил величину (у конверсий — Метрика)
    attribution_model: str | None    # None: метрика не зависит от атрибуции
    goal_definition: str | None      # None: метрика не зависит от целей
    formula: str
    empty_cell_semantics: str | None = None  # что значит пустая ячейка отчёта провайдера (решение владельца)
    version: str = VERSION


# «--» в столбце Conversions_* = 0 конверсий — принятое решение парсера AdPilot (зафиксировано тестом), не гарантия
# API Яндекса (sync/parse.py). Для Impressions / Clicks / Cost «--» — ошибка формата.
_DASH_IS_ZERO = ("'--' в столбце конверсий = 0 конверсий: принятое решение парсера AdPilot (зафиксировано тестом), "
                 "не гарантия API Яндекса")


def _direct(metric: str, formula: str, *, conversion: bool = False) -> MetricDefinition:
    return MetricDefinition(metric, "yandex_direct", _LEVELS, "yandex_direct",
                            "yandex_metrika" if conversion else "yandex_direct",
                            _ATTRIBUTION if conversion else None, _GOALS if conversion else None, formula,
                            _DASH_IS_ZERO if metric == "conversions" else None)


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
