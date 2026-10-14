"""Причины изменения CPA: вклад CPC и CR (LMDI) + проверка, что изменение CR не шум. Причинность — не выше «связано»."""

from decimal import Decimal as D

from app.intelligence.metrics.contribution import Period
from app.intelligence.root_cause import METHOD, Status, explain

BEFORE = Period(cost=D(500000), clicks=D(20000), conversions=D(400))   # CPC 25, CR 2%, CPA 1250


def test_cr_drop_on_large_sample_is_the_associated_driver():
    after = Period(cost=D(520000), clicks=D(20000), conversions=D(260))  # CPC 26, CR 1,3%, CPA 2000
    cause = explain(BEFORE, after)
    assert cause.status is Status.ASSOCIATED and cause.driver == "cr" and cause.cr_change_significant is True
    assert cause.contribution.cpc + cause.contribution.cr == cause.contribution.cpa_after - cause.contribution.cpa_before
    assert "conversion_goals" in cause.next_checks and "mix_shift_not_checked" in cause.limitations
    assert cause.method == METHOD


def test_cpc_growth_driver():
    after = Period(cost=D(700000), clicks=D(20000), conversions=D(400))  # CPC 35, CR тот же
    cause = explain(BEFORE, after)
    assert (cause.status, cause.driver) == (Status.ASSOCIATED, "cpc") and "strategy" in cause.next_checks


def test_cr_change_within_noise_is_not_established():
    small_before = Period(cost=D(10000), clicks=D(200), conversions=D(4))
    small_after = Period(cost=D(10000), clicks=D(200), conversions=D(2))  # «CR упал вдвое» по 2 конверсиям
    cause = explain(small_before, small_after)
    assert cause.status is Status.NOT_ESTABLISHED and cause.cr_change_significant is False
    assert cause.next_checks == ("more_data",)


def test_mixed_when_no_factor_dominates():
    after = Period(cost=D(600000), clicks=D(20000), conversions=D(330))  # CPC +20%, CR −17%
    assert explain(BEFORE, after).driver == "mixed"


def test_no_change_and_missing_data():
    assert explain(BEFORE, BEFORE).status is Status.NO_MATERIAL_CHANGE
    assert explain(BEFORE, Period(cost=D(100), clicks=D(10), conversions=None)).status is Status.INSUFFICIENT_DATA
