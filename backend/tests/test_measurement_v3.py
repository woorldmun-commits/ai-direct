"""high_cpa_measure@3: «до» вне окна срабатывания правила (регрессия к среднему), экономия — только значимая,
отрицательный наблюдаемый эффект не теряется. Пример PRD §2 («История одной рекомендации») — по @2."""

import random
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app.audit.measurement import (METHODS, POLICY, MeasureInput, measure, measure_cpa,
                                   measure_cpa_outside_trigger)
from app.rules.domain import AuditSettings, CampaignDay, Finding, SnapshotView, Window, run
from app.rules.high_cpa import HIGH_CPA_TARGET_V2
from app.sources.conversion import ConversionDefinition

CID = 101
EXEC = date(2026, 9, 20)
BEFORE = Window(EXEC - timedelta(7), EXEC - timedelta(1))
AFTER = Window(EXEC + timedelta(1), EXEC + timedelta(7))


def spread(window: Window, cost, conv) -> list[CampaignDay]:
    """Расход и конверсии окна — в его первый день, остальные дни — нули (сумма по окну та же)."""
    first = [CampaignDay(CID, window.date_from, D(cost), 100, D(conv))]
    return first + [CampaignDay(CID, window.date_from + timedelta(i), D(0), 0, D(0)) for i in range(1, 7)]


def test_prd_example():
    """PRD: CPA 1 840 → 1 420 ₽, конверсии 19 → 21: сэкономлено 21 × (1 840 − 1 420) = 8 820 ₽ (а не ≈ 3 000 ₽)."""
    m = measure_cpa(spread(BEFORE, 19 * 1840, 19) + spread(AFTER, 21 * 1420, 21), BEFORE, AFTER)
    assert (m.verdict, m.saved.amount) == ("effect", D("8820.00"))


def test_prd_example_under_v3_is_within_noise():
    """Та же неделя после, «до» — 28 дней перед окном срабатывания с тем же CPA 1 840 ₽: снижение на 23% при 21
    конверсии статистически не подтверждается — not_confirmed, наблюдаемый эффект виден."""
    base = Window(BEFORE.date_from - timedelta(28), BEFORE.date_from - timedelta(1))
    days = [CampaignDay(CID, base.date_from, D(76 * 1840), 300, D(76))] + spread(BEFORE, 19 * 1840, 19)
    m = measure_cpa_outside_trigger(days + spread(AFTER, 21 * 1420, 21), BEFORE, AFTER, BEFORE)
    assert (m.verdict, m.effect["reason"], m.saved) == ("not_confirmed", "cpa_change_within_noise", None)
    assert m.effect["observed_saved"] == "8820.00" and m.effect["before_window"] == f"{base.date_from}..{base.date_to}"


def test_unknown_trigger_window_is_insufficient():
    m = measure("high_cpa_measure@3", MeasureInput(tuple(spread(BEFORE, 1000, 10))), BEFORE, AFTER)
    assert (m.verdict, m.effect["reason"]) == ("insufficient", "trigger_window_unknown")
    assert POLICY == "high_cpa_measure@3" and "high_cpa_measure@2" in METHODS  # старые замеры читаются по своей


def test_non_overlapping_before_window_is_used_as_is_and_negative_effect_is_kept():
    trigger = Window(BEFORE.date_from - timedelta(20), BEFORE.date_from - timedelta(14))
    days = spread(BEFORE, 20 * 1000, 20) + spread(AFTER, 22 * 1300, 22)
    m = measure("high_cpa_measure@3", MeasureInput(tuple(days), trigger_window=trigger), BEFORE, AFTER)
    assert (m.verdict, m.effect["reason"], m.saved) == ("no_effect", "cpa_not_lower", None)
    assert m.effect["observed_saved"] == "-6600.00"  # 22 × (1 000 − 1 300): ухудшение не обнуляется
    assert m.before["cost"].period == BEFORE


def test_significant_drop_at_same_volume_is_effect():
    base = Window(BEFORE.date_from - timedelta(28), BEFORE.date_from - timedelta(1))
    days = [CampaignDay(CID, base.date_from, D(160 * 2000), 900, D(160))] + spread(BEFORE, 40 * 2000, 40)
    m = measure_cpa_outside_trigger(days + spread(AFTER, 60 * 1000, 60), BEFORE, AFTER, BEFORE)
    assert (m.verdict, m.saved.amount) == ("effect", D("44768.09"))  # 60 × (2 000 − 60 000 / 47,86): нижняя граница
    assert m.effect["observed_saved"] == "60000.00"


# --- Регрессия к среднему: симуляция без истинного эффекта --------------------------------------------------

def poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = pow(2.718281828459045, -lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _campaign(rng, start: date, n_days: int, cpa: D, weekly: float) -> list[CampaignDay]:
    cost = (cpa * D(weekly) / 7).quantize(D("0.01"))
    return [CampaignDay(CID, start + timedelta(i), cost, 50, D(poisson(rng, weekly / 7))) for i in range(n_days)]


def _flagged(days, trigger: Window, target: D) -> bool:
    """Сработало ли правило high_cpa_target@2 на окне trigger (снимок — 37 дней по его конец)."""
    view = SnapshotView(1, 1, 1, trigger.date_to - timedelta(36), trigger.date_to,
                        frozenset({"yandex_direct", "direct_conversions"}),
                        tuple(d for d in days if d.date <= trigger.date_to), (), trigger.date_to + timedelta(1),
                        ConversionDefinition(1, (111,), "last"))
    return any(isinstance(o, Finding) for o in run(HIGH_CPA_TARGET_V2, view, AuditSettings(target_cpa=target)))


@pytest.mark.parametrize("lam", [15])
def test_regression_to_the_mean_does_not_create_savings(lam):
    """Истинного эффекта нет (CPA постоянен), λ = 15 конверсий в неделю. Берутся только недели, на которых правило
    сработало (CPA случайно высокий), выполнение — сразу после окна срабатывания: «до» @2 = окно срабатывания.
    @3: доля verdict = effect ≤ 10%, средний saved ≈ 0 и средний наблюдаемый эффект ≈ 0. @2 — якорь проблемы."""
    rng, cpa, weekly_cost = random.Random(20261014), D(2000), D(2000 * lam)
    v2_effects = v3_effects = n = 0
    saved_v3, observed = D(0), D(0)
    for _ in range(1500):
        days = _campaign(rng, BEFORE.date_from - timedelta(30), 45, cpa, lam)
        if not _flagged(days, BEFORE, cpa):
            continue
        n += 1
        v2_effects += measure_cpa(days, BEFORE, AFTER).verdict == "effect"
        m = measure_cpa_outside_trigger(days, BEFORE, AFTER, BEFORE)
        v3_effects += m.verdict == "effect"
        saved_v3 += m.saved.amount if m.saved else 0
        observed += D(m.effect.get("observed_saved", "0"))
    assert n >= 300
    assert v3_effects / n <= 0.10
    assert saved_v3 / n <= weekly_cost * D("0.02")    # ≈ 0: < 2% недельного расхода
    assert abs(observed / n) <= weekly_cost * D("0.05")
    assert v2_effects / n > 0.3                         # у @2 регрессия к среднему давала «экономию»
