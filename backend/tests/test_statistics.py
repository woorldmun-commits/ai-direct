"""Статистическая проверка доли (CR): интервал Уилсона и «изменение достоверно» — без выводов по 1–2 конверсиям."""

from decimal import Decimal as D

import pytest

from app.intelligence.metrics.statistics import METHOD, rate_changed, wilson


def test_wilson_known_value():
    low, high = wilson(D(20), D(1000))  # 2%: интервал Уилсона 95% ≈ 1,30%…3,07%
    assert D("0.0129") < low < D("0.0131") and D("0.0306") < high < D("0.0308")


def test_wilson_bounds_and_zero_successes():
    low, high = wilson(D(0), D(50))
    assert low == 0 and D(0) < high < D("0.08")
    assert wilson(D(50), D(50))[1] == 1


@pytest.mark.parametrize("successes, trials", [(D(1), D(0)), (D(-1), D(10)), (D(11), D(10)), (None, D(10))])
def test_wilson_undefined_is_none_not_zero(successes, trials):
    assert wilson(successes, trials) is None


def test_small_sample_change_is_not_significant():
    # CR 2/100 → 1/100: «упал вдвое», но по одной-двум конверсиям вывода нет
    assert rate_changed(D(2), D(100), D(1), D(100)) is False


def test_large_sample_change_is_significant():
    assert rate_changed(D(200), D(10000), D(100), D(10000)) is True
    assert METHOD == "wilson_95@1"


def test_unknown_data_is_none():
    assert rate_changed(None, D(100), D(1), D(100)) is None
