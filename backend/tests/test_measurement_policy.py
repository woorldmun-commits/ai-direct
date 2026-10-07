"""Методика замера high_cpa на обычных данных, без БД: «Сэкономлено» — только когда эффект доказан.
Первая часть — high_cpa_measure@2 (замеры, созданные до @3, пересчитываются ею), @1 — историческая;
вторая — текущая high_cpa_measure@3."""

from datetime import date, timedelta
from decimal import Decimal
from functools import partial

import pytest

from app.audit.measurement import METHODS, POLICY, binomial_upper_tail, measure_cpa as _measure_cpa
from app.rules.domain import CampaignDay, Window

measure_cpa = partial(_measure_cpa, params=METHODS["high_cpa_measure@2"])
V3 = METHODS["high_cpa_measure@3"]

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
    m = measure_cpa(days(50000, 10, 3000 * after_conv, after_conv), BEFORE, AFTER, params=METHODS["high_cpa_measure@1"])
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


# --- high_cpa_measure@3: «до» — базовый период вывода, эффект — статистически значимый ----------------

BASELINE = Window(DONE - timedelta(37), DONE - timedelta(8))  # 30 дней перед неделей срабатывания правила


def days3(base_cost, base_conv, after_cost, after_conv):
    """База — одной строкой в последний её день; неделя срабатывания (плохая, по ней правило сработало) и день
    выполнения — шум, который в @3 не должен учитываться: иначе регрессия к среднему выглядит как экономия."""
    return [CampaignDay(1, BASELINE.date_to, Decimal(base_cost), 10, Decimal(base_conv)),
            CampaignDay(1, DONE - timedelta(3), Decimal(60000), 10, Decimal(10)),  # неделя срабатывания: CPA 6 000
            CampaignDay(1, DONE, Decimal(99999), 10, Decimal(1)),
            CampaignDay(1, AFTER.date_to, Decimal(after_cost), 10, Decimal(after_conv))]


def test_current_policy_is_v3():
    assert POLICY == "high_cpa_measure@3"


def test_v3_regression_to_mean_is_not_savings():
    """Кампания работает как обычно (CPA 3 000 и в базе, и после): плохая неделя срабатывания — случайность.
    @2 сравнила бы с ней (6 000 → 3 000) и «нашла» экономию; @3 сравнивает с базой — экономии нет."""
    m = _measure_cpa(days3(90000, 30, 21000, 7), BASELINE, AFTER, V3)
    assert (m.verdict, m.saved, m.effect["reason"]) == ("no_effect", None, "cpa_not_lower")
    assert m.before["cpa"].amount == Decimal("3000.00") and m.before["cost"].period == BASELINE


def test_v3_lower_cpa_within_noise_is_not_confirmed():
    """3 000 → 2 000 ₽ при 7 конверсиях после: p ≈ 0,27 — такое бывает случайно; экономию не показываем."""
    m = _measure_cpa(days3(90000, 30, 14000, 7), BASELINE, AFTER, V3)
    assert (m.verdict, m.saved, m.effect["reason"]) == ("not_confirmed", None, "not_significant")
    assert Decimal("0.10") <= Decimal(m.effect["p_value"]) < Decimal("0.5")


def test_v3_significant_effect_is_saved():
    """3 000 → 1 500 ₽, 14 конверсий за 7 дней (2 в день против 1 в базе): p < 0,10. Сэкономлено 14 × 1 500."""
    m = _measure_cpa(days3(90000, 30, 21000, 14), BASELINE, AFTER, V3)
    assert m.verdict == "effect" and m.saved.amount == Decimal("21000.00") and m.saved.period == AFTER
    assert Decimal(m.effect["p_value"]) < Decimal("0.10")
    assert m.effect["conversions_change_pct"] == "100.0"  # в день: 1 → 2


def test_v3_compares_volume_per_day():
    """База 30 дней, «после» 7: 6 конверсий за неделю — меньше, чем 1 в день, хотя CPA ниже."""
    m = _measure_cpa(days3(90000, 30, 6000, 6), BASELINE, AFTER, V3)
    assert (m.verdict, m.saved, m.effect["reason"]) == ("not_confirmed", None, "conversions_dropped")


def test_v3_needs_baseline_volume():
    m = _measure_cpa(days3(27000, 9, 21000, 14), BASELINE, AFTER, V3)
    assert (m.verdict, m.effect["reason"]) == ("insufficient", "before_conversions_below_minimum")


@pytest.mark.parametrize("k, n, q, p", [(0, 5, 0.3, 1.0), (3, 3, 0.5, 0.125), (2, 2, 0.5, 0.25),
                                        (6, 5, 0.5, 0.0), (1, 4, 0.5, 0.9375)])
def test_binomial_upper_tail(k, n, q, p):
    assert binomial_upper_tail(k, n, q) == pytest.approx(p)


def test_binomial_upper_tail_does_not_overflow_on_large_volumes():
    assert binomial_upper_tail(600, 2000, 0.25) < 1e-6 and binomial_upper_tail(400, 2000, 0.25) > 0.99
