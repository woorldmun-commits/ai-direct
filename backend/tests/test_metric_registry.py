"""Реестр метрик в коде (metric_definitions@1): источник истины задаёт реестр, а не правило."""

import dataclasses

import pytest

from app.intelligence.metrics.definitions import DEFINITIONS, VERSION, MetricDefinition, source_of_truth

METRICS = ("cost", "clicks", "impressions", "conversions", "cpa", "cr")


def test_registry_has_all_metrics_and_version():
    assert VERSION == "metric_definitions@1"
    assert set(DEFINITIONS) == set(METRICS)
    assert all(isinstance(d, MetricDefinition) and d.metric == k and d.version == VERSION
               for k, d in DEFINITIONS.items())


@pytest.mark.parametrize("metric", ["conversions", "cpa"])
def test_conversions_and_cpa_come_from_direct_reports_with_fixed_goals(metric):
    d = DEFINITIONS[metric]
    assert (d.provider, d.source_of_truth) == ("yandex_direct", "yandex_direct")
    assert d.goal_definition and d.attribution_model  # цели и атрибуция фиксируются снимком
    assert source_of_truth(metric) == "yandex_direct"


def test_volume_metrics_have_no_goal_or_attribution():
    for metric in ("cost", "clicks", "impressions"):
        d = DEFINITIONS[metric]
        assert d.source_of_truth == "yandex_direct" and d.goal_definition is None and d.attribution_model is None


def test_every_metric_has_formula_and_known_source():
    for d in DEFINITIONS.values():
        assert d.formula and d.object_level
        assert d.source_of_truth in ("yandex_direct", "yandex_metrika", "user_input")


def test_direct_dash_means_zero_conversions_is_pinned():
    """«--» в столбце конверсий = 0 конверсий — принятое решение парсера AdPilot (sync/parse.py), не «нет данных»."""
    note = DEFINITIONS["conversions"].empty_cell_semantics
    assert "--" in note and "0 конверсий" in note
    assert DEFINITIONS["cost"].empty_cell_semantics is None


def test_definition_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFINITIONS["cpa"].source_of_truth = "yandex_metrika"


def test_unknown_metric_is_an_error_not_a_default():
    with pytest.raises(KeyError):
        source_of_truth("roas")


def test_every_definition_has_retrieval_and_measurement_source():
    for d in DEFINITIONS.values():
        assert d.source_of_truth and d.measurement_source, d.metric


@pytest.mark.parametrize("metric", ["conversions", "cpa", "cr"])
def test_conversion_based_metrics_are_retrieved_from_direct_but_measured_by_metrika(metric):
    """Число берём из отчёта Директа, но конверсии — данные Метрики, доставленные через Директ."""
    d = DEFINITIONS[metric]
    assert (d.source_of_truth, d.measurement_source) == ("yandex_direct", "yandex_metrika")
    assert d.measurement_source != d.source_of_truth


@pytest.mark.parametrize("metric", ["cost", "clicks", "impressions"])
def test_volume_metrics_are_measured_by_direct_itself(metric):
    assert DEFINITIONS[metric].measurement_source == DEFINITIONS[metric].source_of_truth == "yandex_direct"


def test_dash_note_says_parser_decision_not_api_guarantee():
    note = DEFINITIONS["conversions"].empty_cell_semantics
    assert "решение парсера AdPilot" in note and "не гарантия API Яндекса" in note
