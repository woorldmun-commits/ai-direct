"""Metric Registry v2 (docs/INTELLIGENCE_V2_CONTRACTS.md §2): аддитивные поля и can_compute."""

from decimal import Decimal

import pytest

from app.contract import UNAVAILABLE_REASONS
from app.intelligence.metrics.definitions import DEFINITIONS, MinimumData, can_compute

ALL = ("cost", "clicks", "impressions", "conversions", "cpa", "cr")


def test_every_metric_has_v2_fields():
    for metric, d in DEFINITIONS.items():
        assert d.owner and d.required_fields and d.channel_scope in ("search", "network", "all")
        assert d.value_type in ("actual", "calculated", "estimated")
        assert d.metric_version == f"{metric}@1"
        assert isinstance(d.minimum_data, MinimumData)
        assert d.unavailable_reasons and set(d.unavailable_reasons) <= set(UNAVAILABLE_REASONS)
        assert len(set(d.unavailable_reasons)) == len(d.unavailable_reasons)


def test_value_types():
    assert {m: DEFINITIONS[m].value_type for m in ALL} == {
        "cost": "actual", "clicks": "actual", "impressions": "actual", "conversions": "actual",
        "cpa": "calculated", "cr": "calculated"}


def test_pr1_semantics_kept_retrieval_vs_measurement():
    for m in ("conversions", "cpa", "cr"):
        assert (DEFINITIONS[m].source_of_truth, DEFINITIONS[m].measurement_source) == ("yandex_direct",
                                                                                         "yandex_metrika")
    assert DEFINITIONS["cost"].measurement_source == "yandex_direct"


def test_minimum_data_means_minimum_to_compute():
    assert DEFINITIONS["cpa"].minimum_data.min_conversions == 1
    assert DEFINITIONS["cost"].minimum_data.min_conversions is None


def test_required_fields_are_known_metrics():
    for d in DEFINITIONS.values():
        assert set(d.required_fields) <= set(ALL)


def test_cpa_needs_cost_and_conversions_fields():
    assert can_compute("cpa", {"cost", "conversions"}, Decimal("3")) == (True, None)
    ok, reason = can_compute("cpa", {"cost"}, None)
    assert (ok, reason) == (False, "source_missing")


def test_cpa_with_zero_conversions_is_unavailable_never_zero():
    assert can_compute("cpa", {"cost", "conversions"}, Decimal("0")) == (False, "no_conversions")


def test_conversions_none_is_missing_not_zero():
    assert can_compute("cpa", {"cost", "conversions"}, None) == (False, "source_missing")


def test_metric_without_minimum_ignores_conversions():
    assert can_compute("cost", {"cost"}, None) == (True, None)
    assert can_compute("cr", {"conversions", "clicks"}, Decimal("0")) == (True, None)  # 0 конверсий — валидный CR


def test_reasons_returned_are_declared_by_the_metric():
    for metric in ALL:
        ok, reason = can_compute(metric, set(), Decimal("0"))
        assert not ok and reason in DEFINITIONS[metric].unavailable_reasons


def test_unknown_metric_raises():
    with pytest.raises(KeyError):
        can_compute("roas", {"cost"}, None)
