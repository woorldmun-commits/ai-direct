"""Разложение изменения CPA на вклад CPC и CR (LMDI): точное (вклады в сумме = ΔCPA) и не зависит от порядка."""

from decimal import Decimal as D

import pytest

from app.intelligence.metrics.contribution import METHOD, Period, cpa_contribution

BEFORE = Period(cost=D(100000), clicks=D(2000), conversions=D(40))   # CPC 50, CR 2%, CPA 2500
AFTER = Period(cost=D(132000), clicks=D(2400), conversions=D(40))    # CPC 55, CR 1,667%, CPA 3300


def test_contributions_sum_to_the_cpa_change():
    c = cpa_contribution(BEFORE, AFTER)
    assert c.method == METHOD
    assert c.cpa_before == D("2500.00") and c.cpa_after == D("3300.00")
    assert c.cpc + c.cr == c.cpa_after - c.cpa_before


def test_cr_drop_is_the_larger_part_here():
    c = cpa_contribution(BEFORE, AFTER)  # CPC +10%, CR −16,7%: CR даёт больше
    assert c.cr > c.cpc > 0


def test_only_cpc_changed_gives_all_to_cpc():
    c = cpa_contribution(BEFORE, Period(cost=D(110000), clicks=D(2000), conversions=D(40)))
    assert c.cr == 0 and c.cpc == D("250.00")


@pytest.mark.parametrize("after", [Period(D(100), D(10), D(0)), Period(D(100), D(0), D(0)),
                                   Period(D(100), D(10), None)])
def test_no_conversions_or_clicks_gives_none_not_zero(after):
    assert cpa_contribution(BEFORE, after) is None
