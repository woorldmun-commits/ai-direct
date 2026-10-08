"""Методика замера high_cpa на обычных данных, без БД: «Сэкономлено» — только когда эффект доказан.
По умолчанию — текущая high_cpa_measure@2; @1 — историческая, проверяется отдельно."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.audit.measurement import METHODS, measure_cpa
from app.rules.domain import CampaignDay, Window

DONE = date(2026, 9, 30)
BEFORE = Window(DONE - timedelta(7), DONE - timedelta(1))
AFTER = Window(DONE + timedelta(1), DONE + timedelta(7))


def days(before_cost, before_conv, after_cost, after_conv):
    """Итоги окон — одной строкой в последний день окна; день выполнения — шум, который не должен учитываться."""
    return [CampaignDay(1, BEFORE.date_to, Decimal(before_cost), 10, Decimal(before_conv)),
            CampaignDay(1, DONE, Decimal(99999), 10, Decimal(1)),
            CampaignDay(1, AFTER.date_to, Decimal(after_cost), 10, Decimal(after_conv))]


def test_effect_saved_is_computed_from_volume_actually_achieved():
    """До: 50 000 / 10 = 5 000 ₽. После: 35 000 / 10 = 3 500 ₽. Сэкономлено 10 × 1 500 = 15 000 ₽."""
    m = measure_cpa(days(50000, 10, 35000, 10), BEFORE, AFTER)
    assert m.verdict == "effect"
    assert m.saved.amount == Decimal("15000.00") and m.saved.calculation_type == "estimated" and m.saved.formula
    assert m.saved.period == AFTER
    assert dict(m.effect) == {"reason": "cpa_lower_at_same_volume", "cpa_change_pct": "-30.0",
                              "conversions_change_pct": "0.0"}
    assert (m.before["cpa"].amount, m.after["cpa"].amount) == (Decimal("5000.00"), Decimal("3500.00"))
    assert m.before["cost"].amount == 50000                                # день выполнения не вошёл в окна


def test_cheaper_cpa_with_fewer_conversions_is_not_confirmed_savings():
    """CPA 5 000 → 3 500, но конверсий 10 → 4: стоимость заявки снизилась, но экономия не подтверждена —
    заявок стало меньше. Не «без эффекта»: изменение CPA сохраняется и показывается."""
    m = measure_cpa(days(50000, 10, 14000, 4), BEFORE, AFTER)
    assert (m.verdict, m.saved, m.effect["reason"]) == ("not_confirmed", None, "conversions_dropped")
    assert (m.effect["cpa_change_pct"], m.effect["conversions_change_pct"]) == ("-30.0", "-60.0")


@pytest.mark.parametrize("before_conv, after_conv, verdict", [
    (10, 10, "effect"), (10, 9, "not_confirmed"), (10, 8, "not_confirmed"),  # @2: conv_after ≥ conv_before
    (100, 90, "not_confirmed"), (100, 101, "effect"),
])
def test_conversions_must_not_drop(before_conv, after_conv, verdict):
    m = measure_cpa(days(5000 * before_conv, before_conv, 3000 * after_conv, after_conv), BEFORE, AFTER)
    assert m.verdict == verdict


@pytest.mark.parametrize("after_conv, verdict", [(8, "effect"), (7, "no_effect")])  # @1: допуск падения 20%
def test_legacy_v1_keeps_its_own_rule(after_conv, verdict):
    """Замеры, созданные по @1, пересчитываются только своей методикой — результат не меняется задним числом."""
    m = measure_cpa(days(50000, 10, 3000 * after_conv, after_conv), BEFORE, AFTER, METHODS["high_cpa_measure@1"])
    assert m.verdict == verdict


@pytest.mark.parametrize("args, verdict, reason", [
    ((50000, 10, 60000, 10), "no_effect", "cpa_not_lower"),
    ((50000, 10, 50000, 10), "no_effect", "cpa_not_lower"),
    ((50000, 10, 30000, 0), "no_effect", "no_conversions_after"),
    ((50000, 2, 30000, 10), "insufficient", "before_conversions_below_minimum"),
    ((50000, 10, 0, 0), "insufficient", "no_activity_after"),
])
def test_no_saved_without_proof(args, verdict, reason):
    m = measure_cpa(days(*args), BEFORE, AFTER)
    assert (m.verdict, m.saved, m.effect["reason"]) == (verdict, None, reason)


def test_saved_only_with_effect_everywhere():
    for bc, bv, ac, av in [(50000, 10, 35000, 10), (50000, 10, 60000, 10), (50000, 2, 1, 1), (1, 10, 1, 10)]:
        m = measure_cpa(days(bc, bv, ac, av), BEFORE, AFTER)
        assert (m.saved is not None) == (m.verdict == "effect")


def test_measure_cpa_unknown_conversions_are_insufficient_not_zero():
    """Нет данных о конверсиях за день окна — это не «0 конверсий» и не вывод «эффекта нет»."""
    rows = days(50000, 10, 35000, 10)
    rows[0] = CampaignDay(1, BEFORE.date_to, Decimal(50000), 10, None)
    m = measure_cpa(rows, BEFORE, AFTER)
    assert (m.verdict, m.effect["reason"], m.saved) == ("insufficient", "conversions_unknown", None)


def test_measurement_labels_conversions_and_cpa_as_yandex_direct():
    m = measure_cpa(days(50000, 10, 35000, 10), BEFORE, AFTER)
    assert m.saved is not None and m.saved.source == "yandex_direct"
    for facts in (m.before, m.after):
        assert {f.source for f in facts.values()} == {"yandex_direct"}
