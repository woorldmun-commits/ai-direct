"""Методики замера zero_conv_campaign / zero_conv_placements на обычных данных, без БД: «Сэкономлено» — только когда
эффект доказан всеми критериями; каждая ветка без saved — со своей причиной. Числа — golden-кейсы (считаются руками)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.audit.measurement import (DESIGN, METHODS, MeasureInput, counts_in_saved_total, family, measure,
                                   measure_zero_conv_campaign, measure_zero_conv_placements)
from app.rules import RULES
from app.rules.domain import CampaignDay, PlacementDay, Window

DONE = date(2026, 9, 30)
BEFORE = Window(DONE - timedelta(7), DONE - timedelta(1))
AFTER = Window(DONE + timedelta(1), DONE + timedelta(7))
REF = Decimal("3000")


def days(before_cost, before_conv, after_cost, after_conv):
    """Итоги окон — одной строкой в последний день окна; день выполнения — шум, который не должен учитываться."""
    return [CampaignDay(1, BEFORE.date_to, Decimal(before_cost), 10, None if before_conv is None else Decimal(before_conv)),
            CampaignDay(1, DONE, Decimal(99999), 10, Decimal(50)),
            CampaignDay(1, AFTER.date_to, Decimal(after_cost), 10, None if after_conv is None else Decimal(after_conv))]


def test_every_family_the_trigger_names_has_a_method():
    """Триггер на 'done' ставит '<issue_type>_measure@2' — для каждого семейства правил v1.0 методика есть."""
    for rule in RULES:
        assert f"{rule.family}_measure@2" in METHODS
    assert family("zero_conv_placements_measure@2") == "zero_conv_placements"
    assert DESIGN == "uncontrolled_before_after"
    assert all(p["final_data_wait_days"] == 14 for p in METHODS.values())  # ожидание данных — как у high_cpa
    with pytest.raises(KeyError):
        measure("zero_conv_queries_measure@2", MeasureInput(()), BEFORE, AFTER)


# --- zero_conv_campaign_measure@2 -----------------------------------------------------------------

def zc(before_cost, before_conv, after_cost, after_conv, ref=REF):
    return measure_zero_conv_campaign(days(before_cost, before_conv, after_cost, after_conv), BEFORE, AFTER, ref)


def test_zero_conv_campaign_effect_golden():
    """До: 21 000 ₽, 0 конверсий. После: 6 000 ₽, 3 конверсии → CPA 2 000 ≤ ориентира 3 000.
    Сэкономлено = 21 000 − 6 000 = 15 000 ₽ (эффективный расход «после» не вычитается)."""
    m = zc(21000, 0, 6000, 3)
    assert m.verdict == "effect"
    assert m.saved.amount == Decimal("15000.00") and isinstance(m.saved.amount, Decimal)
    assert (m.saved.calculation_type, m.saved.period, m.saved.formula) == \
        ("estimated", AFTER, "campaign_cost_before - campaign_cost_after")
    assert dict(m.effect) == {"reason": "spend_lower_conversions_at_reference_cpa", "cost_change_pct": "-71.4",
                              "conversions_after": "3", "reference_cpa": "3000.00", "cpa_after_vs_reference_pct": "-33.3"}
    assert m.before["cost"].amount == 21000 and m.after["cpa"].amount == Decimal("2000.00")  # день выполнения — вне


def test_zero_conv_campaign_kopecks_stay_decimal():
    m = measure_zero_conv_campaign([CampaignDay(1, BEFORE.date_from, Decimal("21000.50"), 5, Decimal(0)),
                                    CampaignDay(1, AFTER.date_from, Decimal("6000.25"), 5, Decimal(3))],
                                   BEFORE, AFTER, Decimal("2500.10"))
    assert m.saved.amount == Decimal("15000.25")


@pytest.mark.parametrize("args, ref, verdict, reason", [
    ((21000, 0, 9000, 3), REF, "effect", "spend_lower_conversions_at_reference_cpa"),          # CPA = ориентиру
    ((21000, 0, 12000, 2), REF, "not_confirmed", "cpa_after_above_reference"),                 # 6 000 > 3 000
    ((21000, 0, 6000, 3), None, "not_confirmed", "no_reference_cpa"),                          # порог был абсолютным
    ((21000, 0, 5000, 0), REF, "not_confirmed", "spend_lower_still_no_conversions"),           # бюджет урезан
    ((21000, 0, 25000, 10), REF, "not_confirmed", "conversions_appeared_spend_not_lower"),
    ((21000, 0, 21000, 0), REF, "no_effect", "no_conversions_after"),
    ((21000, 0, 30000, 0), REF, "no_effect", "no_conversions_after"),
    ((21000, 2, 6000, 3), REF, "insufficient", "conversions_before"),                          # проблемы «до» нет
    ((0, 0, 6000, 3), REF, "insufficient", "no_spend_before"),
    ((21000, 0, 0, 0), REF, "insufficient", "no_activity_after"),                              # кампанию остановили
    ((21000, None, 6000, 3), REF, "insufficient", "conversions_unknown"),
    ((21000, 0, 6000, None), REF, "insufficient", "conversions_unknown"),
])
def test_zero_conv_campaign_branches(args, ref, verdict, reason):
    m = zc(*args, ref=ref)
    assert (m.verdict, m.effect["reason"]) == (verdict, reason)
    assert (m.saved is not None) == (verdict == "effect")


# --- zero_conv_placements_measure@2 ---------------------------------------------------------------

EXCLUDED = frozenset({101, 102})


def placements(p101=(5000, 0), p102=(3000, 0), other=(2000, 2000)):
    """(до, после) по площадкам; 103 — не исключалась, её расход в замер не идёт; день выполнения — шум."""
    rows = []
    for pid, (b, a) in ((101, p101), (102, p102), (103, other)):
        rows += [PlacementDay(1, pid, BEFORE.date_from, Decimal(b), 30, Decimal(0)),
                 PlacementDay(1, pid, DONE, Decimal(777), 30, Decimal(0)),
                 PlacementDay(1, pid, AFTER.date_from, Decimal(a), 30, Decimal(0))]
    return rows


def zp(campaign=(50000, 10, 42000, 10), reported=True, ids=EXCLUDED, **kw):
    return measure_zero_conv_placements(days(*campaign), placements(**kw), ids, BEFORE, AFTER,
                                        placements_reported=reported)


def test_zero_conv_placements_effect_golden():
    """Площадки 101 и 102 тратили 5 000 + 3 000 = 8 000 ₽, после исключения — 0. Кампания 50 000 → 42 000 ₽
    (≤ 50 000 − 8 000: деньги ушли из кампании, а не на другие площадки), конверсии 10 → 10.
    Сэкономлено = 8 000 ₽."""
    m = zp()
    assert m.verdict == "effect" and m.saved.amount == Decimal("8000.00")
    assert m.saved.formula == "excluded_placements_cost_before - excluded_placements_cost_after"
    assert (m.before["placements_cost"].amount, m.after["placements_cost"].amount) == (8000, 0)
    assert dict(m.effect) == {"reason": "placements_spend_left_campaign", "placements_cost_change_pct": "-100.0",
                              "campaign_cost_change_pct": "-16.0", "conversions_change_pct": "0.0"}


def test_zero_conv_placements_partial_reduction():
    """101 продолжила тратить 1 000 ₽ (исключили не всё) → сэкономлено только 8 000 − 1 000 = 7 000 ₽."""
    m = zp(campaign=(50000, 10, 43000, 11), p101=(5000, 1000))
    assert (m.verdict, m.saved.amount) == ("effect", Decimal("7000.00"))


def test_budget_flowing_to_other_placements_is_not_saved():
    """Площадки перестали тратить 8 000 ₽, но расход кампании 50 000 → 45 000: 3 000 ₽ Директ перераспределил —
    экономия не подтверждена, saved = NULL, перетёкшая сумма видна в effect."""
    m = zp(campaign=(50000, 10, 45000, 12))
    assert (m.verdict, m.saved, m.effect["reason"], m.effect["reallocated"]) == \
        ("not_confirmed", None, "budget_reallocated", "3000.00")
    full = zp(campaign=(50000, 10, 50000, 12))                              # весь бюджет перетёк
    assert (full.verdict, full.effect["reallocated"]) == ("not_confirmed", "8000.00")


@pytest.mark.parametrize("kw, verdict, reason", [
    ({"campaign": (50000, 10, 42000, 9)}, "not_confirmed", "conversions_dropped"),
    ({"p101": (5000, 5000), "p102": (3000, 3000)}, "no_effect", "placements_spend_not_lower"),
    ({"p101": (5000, 6000), "p102": (3000, 3000)}, "no_effect", "placements_spend_not_lower"),
    ({"reported": False}, "insufficient", "placements_not_in_snapshot"),
    ({"ids": frozenset()}, "insufficient", "no_placements_in_action"),
    ({"campaign": (50000, None, 42000, 10)}, "insufficient", "conversions_unknown"),
    ({"campaign": (50000, 2, 42000, 5)}, "insufficient", "before_conversions_below_minimum"),
    ({"p101": (0, 0), "p102": (0, 0)}, "insufficient", "no_placement_spend_before"),
    ({"campaign": (50000, 10, 0, 0)}, "insufficient", "no_activity_after"),
])
def test_zero_conv_placements_branches(kw, verdict, reason):
    m = zp(**kw)
    assert (m.verdict, m.effect["reason"]) == (verdict, reason)
    assert (m.saved is not None) == (verdict == "effect")


def test_measure_dispatches_by_policy_name():
    data = MeasureInput(tuple(days(50000, 10, 42000, 10)), tuple(placements()), True, EXCLUDED)
    assert measure("zero_conv_placements_measure@2", data, BEFORE, AFTER) == zp()
    data = MeasureInput(tuple(days(21000, 0, 6000, 3)), reference_cpa=REF)
    assert measure("zero_conv_campaign_measure@2", data, BEFORE, AFTER) == zc(21000, 0, 6000, 3)


# --- «Сэкономлено ≈»: только подтверждённое сверкой ручное выполнение -------------------------------

@pytest.mark.parametrize("saved, mode, status, counts", [
    ({"amount": "1"}, "manual", "confirmed", True),
    ({"amount": "1"}, "manual", "pending", False),
    ({"amount": "1"}, "manual", "not_confirmed", False),
    ({"amount": "1"}, "manual", None, False),
    ({"amount": "1"}, "none", "not_required", False),
    (None, "manual", "confirmed", False),
])
def test_counts_in_saved_total_only_when_confirmed(saved, mode, status, counts):
    assert counts_in_saved_total(saved, mode, status) is counts
