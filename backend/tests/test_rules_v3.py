"""Правила @3 и anomaly@2 — исправления аналитической корректности (аудит модели): статистический порог high_cpa,
НДС в target_cpa, точный lost, CPA сетей для площадок, абсолютный режим zero_conv_campaign, база anomaly по активным
дням. Старые версии (@1, @2) не меняются — их проверяют прежние тесты."""

import random
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app.audit.policy import decide_v2
from app.rules import FLAGGED, RULES_V3, active_rules
from app.rules.anomaly import ANOMALY, ANOMALY_V2
from app.rules.domain import (DIRECT_CONVERSIONS, DIRECT_PLACEMENTS, AuditSettings, CampaignDay, Finding, NotEnoughData,
                              PlacementDay, Reason, SnapshotView, run)
from app.rules.high_cpa import HIGH_CPA_BASELINE_V3, HIGH_CPA_TARGET_V2, HIGH_CPA_TARGET_V3
from app.rules.zero_conv_campaign import ZERO_CONV_CAMPAIGN_V2, ZERO_CONV_CAMPAIGN_V3
from app.rules.zero_conv_placements import ZERO_CONV_PLACEMENTS_V2, ZERO_CONV_PLACEMENTS_V3
from app.sources.conversion import ConversionDefinition

END = date(2026, 9, 30)
CID = 101
SOURCES = frozenset({"yandex_direct", DIRECT_CONVERSIONS, DIRECT_PLACEMENTS})


def view(days, placements=(), history=37, partial_from=END + timedelta(1)) -> SnapshotView:
    """days: {дата: (расход, клики, конверсии)} кампании CID; остальные дни окна истории — нули."""
    full = {END - timedelta(i): (D(0), 0, D(0)) for i in range(history)}
    full.update({d: (D(c), k, None if v is None else D(v)) for d, (c, k, v) in days.items()})
    return SnapshotView(1, 1, 1, END - timedelta(history - 1), END, SOURCES,
                        tuple(CampaignDay(CID, d, *x) for d, x in sorted(full.items())),
                        tuple(placements), partial_from, ConversionDefinition(1, (111,), "last"))


def eval_day(cost, conv, clicks=1000):
    return {END - timedelta(3): (cost, clicks, conv)}


def findings(rule, v, settings):
    return [o for o in run(rule, v, settings) if isinstance(o, Finding)]


def poisson(rng: random.Random, lam: float) -> int:
    """Алгоритм Кнута — для λ ≤ 30 достаточно точен и не тянет numpy."""
    limit, k, p = pow(2.718281828459045, -lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


# --- high_cpa@3: статистический порог ----------------------------------------------------------------------

@pytest.mark.parametrize("lam", [10, 20, 30])
def test_on_target_campaign_rarely_gets_a_level_change(lam):
    """Кампания ровно на цели (истинный CPA = target): конверсии недели ~ Пуассон(λ), расход = λ × target. Доля
    ложных выводов (любой уровень) и ложных «change» — не больше 5%. @2 (порог +10%) давал «снизить ставку» в десятки
    процентов недель — то, что исправляет @3."""
    rng, target, trials = random.Random(20261014), D(3000), 2000
    settings = AuditSettings(target_cpa=target)
    fired = changes = fired_v2 = 0
    for _ in range(trials):
        v = view(eval_day(target * lam, poisson(rng, lam)))
        out = findings(HIGH_CPA_TARGET_V3, v, settings)
        fired += bool(out)
        changes += any(decide_v2(f).level == "change" for f in out)
        fired_v2 += bool(findings(HIGH_CPA_TARGET_V2, v, settings))
    assert fired / trials <= 0.05 and changes / trials <= 0.05
    assert fired_v2 / trials > 0.25  # регрессионный якорь: у @2 проблема была


def test_clear_excess_still_fires_with_exact_lost():
    """CPA 4 500 ₽ при цели 3 000 ₽ и 40 конверсиях: превышение надёжно → вывод; lost = cost − target × conv точно."""
    settings = AuditSettings(target_cpa=D(3000))
    (f,) = findings(HIGH_CPA_TARGET_V3, view(eval_day(D("180000.01"), 40)), settings)
    assert f.lost.amount == D("60000.01") and f.lost.formula == "cost - target_cpa * conversions"
    assert f.current_data_quality == "high" and f.evidence_meta["vat_basis"] == "target_includes_vat"


@pytest.mark.parametrize("conv, quality", [(9, "low"), (10, "medium"), (29, "medium"), (30, "high")])
def test_data_sufficiency_high_only_from_30_conversions(conv, quality):
    (f,) = findings(HIGH_CPA_TARGET_V3, view(eval_day(D(9000) * conv, conv)), AuditSettings(target_cpa=D(3000)))
    assert f.current_data_quality == quality


def test_baseline_mode_uses_the_same_statistical_trigger():
    """Пример PRD §4.1 (8 конверсий, +37% к baseline) — шум; при 24 конверсиях с CPA 7 000 ₽ — вывод."""
    base = {END - timedelta(20): (115200, 300, 30)}
    noisy = view({**base, **eval_day(42000, 8)})
    assert findings(HIGH_CPA_BASELINE_V3, noisy, AuditSettings()) == []
    (f,) = findings(HIGH_CPA_BASELINE_V3, view({**base, **eval_day(168000, 24)}), AuditSettings())
    assert f.lost.amount == D("75840.00")


# --- НДС ---------------------------------------------------------------------------------------------------

def test_net_target_is_compared_with_vat_inclusive_cost():
    """target 1 000 ₽ без НДС, CPA с НДС 1 220 ₽ — ровно на цели: вывода нет. Тот же target «с НДС» — вывод."""
    v = view(eval_day(488000, 400))
    net = AuditSettings(target_cpa=D(1000), target_cpa_includes_vat=False)
    assert findings(HIGH_CPA_TARGET_V3, v, net) == []
    (f,) = findings(HIGH_CPA_TARGET_V3, v, AuditSettings(target_cpa=D(1000)))
    assert f.reference == D(1000)


def test_net_target_evidence_shows_both_numbers_and_basis():
    net = AuditSettings(target_cpa=D(1000), target_cpa_includes_vat=False)
    (f,) = findings(HIGH_CPA_TARGET_V3, view(eval_day(800000, 400)), net)
    assert f.reference == D("1220.00")
    assert f.evidence["target_cpa"].amount == D(1000) and f.evidence["target_cpa_with_vat"].amount == D("1220.00")
    assert f.evidence_meta["vat_basis"] == "target_net_converted" and f.evidence_meta["vat_rate"] == "0.22"


# --- zero_conv_placements@3: CPA сетей, а не смешанный --------------------------------------------------------

def placement(pid, day, cost, clicks, conv):
    return PlacementDay(CID, pid, day, D(cost), clicks, None if conv is None else D(conv), f"site{pid}.ru")


def test_placements_reference_is_network_cpa_not_mixed():
    """Поиск: 10 000 ₽ / 10 конв. (CPA 1 000), сети: 30 000 ₽ / 10 конв. (CPA 3 000); смешанный CPA = 2 000 ₽.
    Площадка 2 500 ₽ без конверсий — ниже CPA сетей: @3 вывода не даёт (@2 по смешанному CPA давал)."""
    early = END - timedelta(20)
    v = view({early: (37500, 2000, 20), END - timedelta(3): (2500, 40, 0)},
             [placement(1, early, 27500, 900, 10), placement(2, END - timedelta(3), 2500, 40, 0)])
    assert findings(ZERO_CONV_PLACEMENTS_V2, v, AuditSettings())  # смешанный CPA 2 000 ₽ — ложный вывод
    out = run(ZERO_CONV_PLACEMENTS_V3, v, AuditSettings())
    assert out == (NotEnoughData("zero_conv_placements@3", Reason.VOLUME_INSUFFICIENT, "campaign", CID),)


def test_placements_flag_above_network_cpa_with_network_evidence():
    early = END - timedelta(20)
    v = view({early: (40000, 2000, 20), END - timedelta(3): (3500, 40, 0)},
             [placement(1, early, 26500, 900, 10), placement(2, END - timedelta(3), 3500, 40, 0)])
    (f,) = findings(ZERO_CONV_PLACEMENTS_V3, v, AuditSettings())
    assert f.reference == D("3000.00") and f.evidence_meta["reference_mode"] == "network"
    assert f.evidence["network_conversions"].amount == D(10)


@pytest.mark.parametrize("conv, reason", [(0, Reason.BASELINE_DATA_INSUFFICIENT), (4, Reason.BASELINE_DATA_INSUFFICIENT),
                                          (None, Reason.SOURCE_MISSING)])
def test_placements_without_network_cpa_do_not_fall_back_to_mixed(conv, reason):
    early = END - timedelta(20)
    v = view({early: (40000, 2000, 20)}, [placement(1, early, 20000, 900, conv),
                                          placement(2, END - timedelta(3), 9000, 400, 0)])
    assert run(ZERO_CONV_PLACEMENTS_V3, v, AuditSettings()) == (
        NotEnoughData("zero_conv_placements@3", reason, "campaign", CID),)


# --- zero_conv_campaign@3: абсолютный режим ---------------------------------------------------------------

def test_absolute_mode_is_low_and_out_of_exposure():
    """Ориентира CPA нет (история 10 дней): 6 000 ₽ без конверсий — только «проверить», low, суммы нет."""
    v = view({END - timedelta(3): (6000, 80, 0)}, history=10)
    (old,) = findings(ZERO_CONV_CAMPAIGN_V2, v, AuditSettings())
    (f,) = findings(ZERO_CONV_CAMPAIGN_V3, v, AuditSettings())
    assert old.current_data_quality == "medium" and old.lost.amount == D("6000.00")
    assert f.reference_type == "absolute" and f.current_data_quality == "low"
    assert f.lost.amount is None and f.lost.reason == "volume_insufficient"
    assert f.evidence["cost"].amount == D(6000) and decide_v2(f).level == "inspect_only"


def test_target_mode_keeps_exposure_and_vat_basis():
    v = view({END - timedelta(3): (15000, 120, 0)})
    (f,) = findings(ZERO_CONV_CAMPAIGN_V3, v, AuditSettings(target_cpa=D(4000), target_cpa_includes_vat=False))
    assert f.reference == D("14640.00")  # 3 × 4 880 ₽ (4 000 ₽ + НДС 22%)
    assert f.lost.amount == D("15000.00") and f.evidence_meta["vat_basis"] == "target_net_converted"


# --- anomaly@2: база по активным дням -----------------------------------------------------------------------

def test_spike_baseline_uses_active_days():
    """База — 15 дней по 10 000 ₽ (кампания запущена посреди базы), неделя 70 000 ₽ — норма: @2 вывода не даёт;
    @1 делил базу на 30 дней («ожидал» 35 000 ₽) и видел рост в 2 раза. Конверсий в базе меньше 10 — поправки на
    конверсии нет, сравнивается только расход."""
    days = {END - timedelta(7 + i): (10000, 100, 1 if i < 5 else 0) for i in range(15)}
    days |= {END - timedelta(i): (10000, 100, 1 if i < 2 else 0) for i in range(7)}
    v = view(days, partial_from=END - timedelta(2))
    assert [f.reason_code for f in findings(ANOMALY, v, AuditSettings())] == ["spend_spike"]
    assert findings(ANOMALY_V2, v, AuditSettings()) == []


def test_registry_v3_is_behind_its_flag():
    assert active_rules({"AUDIT_RULES_V3": "1"})[:4] == RULES_V3
    assert not {r.rule_version for r in RULES_V3} & {r.rule_version for r in active_rules({})}
    assert ANOMALY_V2 in FLAGGED["audit_rules_candidates"]
