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


def test_definition_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFINITIONS["cpa"].source_of_truth = "yandex_metrika"


def test_unknown_metric_is_an_error_not_a_default():
    with pytest.raises(KeyError):
        source_of_truth("roas")
