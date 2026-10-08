"""zero_conv_campaign@1 на обычных fixtures, без БД: пороги «достаточного объёма», выбор CPA-ориентира, действия
без ставки и бюджета, «недостаточно данных». Проверяется точная семантика результата."""

import dataclasses
import hashlib
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.audit.policy import decide
from app.audit.templates import explain
from app.audit.values import to_value
from app.rules import ALL_RULES, RULES
from app.rules.domain import (BID_OR_BUDGET_ACTIONS, SPEND_CAMPAIGN, AuditSettings, CampaignDay, Finding, NotEnoughData,
                              Reason, SnapshotView, run, windows)
from app.rules.zero_conv_campaign import ZERO_CONV_CAMPAIGN

D = date(2026, 9, 30)
BOTH = frozenset({"yandex_direct", "direct_conversions"})
CID, OTHER = 12345, 777
TARGET = AuditSettings(target_cpa=Decimal("3000"))
NO_TARGET = AuditSettings()
RULE = "zero_conv_campaign@1"


PARTIAL = D - timedelta(2)   # последние 3 дня досчитываются
SOLID_DAY = D - timedelta(3)  # завершённый день внутри окна оценки


def rows(cid, *, eval_cost=0, eval_clicks=0, eval_conv=0, base_cost=0, base_conv=0, history_days=37, eval_day=SOLID_DAY):
    """Итоги периода — в eval_day (по умолчанию завершённый день окна), baseline — в его последний день, остальные дни
    нулевые (глубина истории)."""
    first = D - timedelta(history_days - 1)
    days = {first + timedelta(i): (Decimal(0), 0, Decimal(0)) for i in range(history_days)}
    days[eval_day] = (Decimal(eval_cost), eval_clicks, None if eval_conv is None else Decimal(eval_conv))
    if D - timedelta(7) in days:
        days[D - timedelta(7)] = (Decimal(base_cost), 0, Decimal(base_conv))
    return tuple(CampaignDay(cid, d, cost, clicks, conv) for d, (cost, clicks, conv) in sorted(days.items()))


def snap(*campaign_rows, sources=BOTH, eval_cost=42000, eval_clicks=70, eval_conv=0, partial_from=PARTIAL, **kw):
    days = sum(campaign_rows, ()) or rows(CID, eval_cost=eval_cost, eval_clicks=eval_clicks, eval_conv=eval_conv, **kw)
    return SnapshotView(snapshot_id=84721, workspace_id=7, direct_account_id=3, period_from=D - timedelta(36),
                        period_to=D, sources=sources, campaign_days=days, partial_from=partial_from)


def audit(s, settings):
    return tuple(out for out in run(ZERO_CONV_CAMPAIGN, s, settings))


def only(result):
    assert len(result) == 1, result
    return result[0]


def test_registered_once():
    assert [r.rule_version for r in RULES if r.family == "zero_conv_campaign"] == ["zero_conv_campaign@2"]
    assert [r.rule_version for r in ALL_RULES if r.family == "zero_conv_campaign"] == [RULE, "zero_conv_campaign@2"]


def test_v1_params_are_fixed():
    """Изменение любого порога — новая версия правила (@2). Значения утверждает владелец продукта."""
    assert dict(ZERO_CONV_CAMPAIGN.params) == {
        "cpa_multiple": 3, "high_cpa_multiple": 5, "min_clicks": 50, "high_clicks": 100,
        "min_cost_rub": 1000, "absolute_min_cost_rub": 5000, "baseline_min_conversions": 10,
    }


# --- Target ---------------------------------------------------------------------------------------

def test_target_exact_contract():
    f = only(audit(snap(), TARGET))
    assert isinstance(f, Finding)
    assert (f.rule_version, f.issue_type, f.object_type, f.object_id) == (RULE, "zero_conv_campaign", "campaign", CID)
    assert f.issue_key == hashlib.sha256(f"7|3|zero_conv_campaign|campaign|{CID}|".encode()).digest()
    assert (f.reason_code, f.metric, f.reference_type) == ("zero_conversions", "cost", "target")
    assert (f.actual, f.reference, f.delta_pct) == (Decimal(42000), Decimal("9000.00"), Decimal("366.7"))
    assert dict(f.action) == {"type": "investigate_zero_conversions",
                              "check": ("conversion_goals", "strategy", "search_queries_negative_keywords")}
    assert (f.lost.amount, f.lost.calculation_type, f.lost.source) == (Decimal(42000), "estimated",
                                                                       "yandex_direct+yandex_metrika")
    assert f.lost.formula and f.lost.period == windows(D)[0]
    assert set(f.evidence) == {"cost", "clicks", "conversions", "target_cpa", "spend_threshold"}
    assert f.evidence["conversions"].amount == 0 and f.evidence["clicks"].amount == 70
    assert f.evidence["spend_threshold"].source == "user_input" and f.evidence["spend_threshold"].formula
    assert dict(f.evidence_meta) == {"reference_source": "target_cpa"}
    assert f.current_data_quality == "medium"  # 42 000 ≥ 5 × 3 000, но кликов 70 < 100


@pytest.mark.parametrize("cost, clicks, expected", [
    ("9000", 50, "finding"),                  # ровно на обоих порогах — срабатывает
    ("8999.99", 50, "volume"), ("9000", 49, "volume"),
    ("15000", 100, "high"), ("14999.99", 100, "medium"), ("15000", 99, "medium"),
])
def test_target_thresholds_are_inclusive(cost, clicks, expected):
    out = only(audit(snap(eval_cost=cost, eval_clicks=clicks), TARGET))
    if expected == "volume":
        assert out == NotEnoughData(RULE, Reason.VOLUME_INSUFFICIENT, "campaign", CID)
    else:
        assert isinstance(out, Finding)
        assert out.current_data_quality == ("high" if expected == "high" else "medium")


def test_cheap_target_uses_cost_floor():
    """target 100 ₽ → 3 × 100 = 300 ₽, но порог не ниже min_cost_rub = 1 000 ₽."""
    assert only(audit(snap(eval_cost=999, eval_clicks=60), AuditSettings(target_cpa=Decimal(100)))).reason \
        is Reason.VOLUME_INSUFFICIENT
    assert only(audit(snap(eval_cost=1000, eval_clicks=60), AuditSettings(target_cpa=Decimal(100)))).reference \
        == Decimal(1000)


# --- Досчёт конверсий (partial) -----------------------------------------------------------------

@pytest.mark.parametrize("eval_day, partial_from", [(D, PARTIAL), (SOLID_DAY, None)])
def test_threshold_reached_only_with_partial_days_is_marked(eval_day, partial_from):
    """Расход за дни досчёта — не настоящий ноль конверсий: вывод остаётся, но не выше medium и с level_reason.
    partial_from неизвестен — всё partial."""
    f = only(audit(snap(eval_cost=15000, eval_clicks=100, eval_day=eval_day, partial_from=partial_from), TARGET))
    assert f.current_data_quality == "medium" and f.evidence_meta["level_reason"] == "conversions_partial"
    assert to_value(f.lost, 1, partial_from).data_status == "partial"


def test_threshold_reached_on_complete_days_is_not_marked():
    f = only(audit(snap(eval_cost=15000, eval_clicks=100), TARGET))  # весь расход — в завершённый день окна
    assert f.current_data_quality == "high" and "level_reason" not in f.evidence_meta


# --- Baseline и абсолютный минимум --------------------------------------------------------------

def test_campaign_baseline_reference():
    """Кампания конвертила раньше (CPA 2 000 ₽), а за неделю — ноль: порог 6 000 ₽."""
    f = only(audit(snap(eval_cost=12000, eval_clicks=120, base_cost=40000, base_conv=20), NO_TARGET))
    assert (f.reference_type, f.reference, f.evidence_meta["reference_source"]) == \
        ("baseline", Decimal("6000.00"), "campaign_baseline")
    assert {"baseline_cost", "baseline_conversions", "baseline_cpa", "spend_threshold"} <= set(f.evidence)
    assert f.evidence["baseline_cpa"].period == windows(D)[1]
    assert f.current_data_quality == "high"  # 12 000 ≥ 5 × 2 000 и 120 кликов
    assert f.action["suggest"] == "set_target_cpa"


def test_account_baseline_when_campaign_never_converted():
    s = snap(rows(CID, eval_cost=9000, eval_clicks=60),
             rows(OTHER, eval_cost=5000, eval_clicks=40, eval_conv=2, base_cost=30000, base_conv=10))
    f = only(audit(s, NO_TARGET))  # OTHER с конверсиями — не эта проблема
    assert (f.object_id, f.reference, f.evidence_meta["reference_source"]) == (CID, Decimal("9000.00"),
                                                                               "account_baseline")
    assert f.evidence["account_baseline_cpa"].amount == Decimal("3000.00")


@pytest.mark.parametrize("kw", [dict(history_days=20), dict(base_cost=27000, base_conv=9), dict(base_conv=10)])
def test_absolute_minimum_without_any_cpa(kw):
    """Нет target, истории < 37 дней, < 10 конверсий в baseline или CPA 0 ₽ → абсолютный порог 5 000 ₽."""
    f = only(audit(snap(eval_cost=5000, eval_clicks=500, **kw), NO_TARGET))
    assert (f.reference_type, f.reference, f.evidence_meta["reference_source"]) == \
        ("absolute", Decimal(5000), "absolute_minimum")
    assert "spend_threshold" not in f.evidence
    assert f.current_data_quality == "medium"  # ожидаемое число конверсий неизвестно — не выше medium
    assert only(audit(snap(eval_cost="4999.99", eval_clicks=500, **kw), NO_TARGET)).reason \
        is Reason.VOLUME_INSUFFICIENT


# --- Когда правило молчит или «недостаточно данных» -------------------------------------------

@pytest.mark.parametrize("kw", [dict(eval_cost=0, eval_clicks=0), dict(eval_conv=1), dict(eval_conv="0.5")])
def test_no_spend_or_any_conversion_gives_nothing(kw):
    assert audit(snap(**kw), TARGET) == ()


def test_unknown_conversions_are_not_zero():
    assert only(audit(snap(eval_conv=None), TARGET)) == NotEnoughData(RULE, Reason.SOURCE_MISSING, "campaign", CID)


@pytest.mark.parametrize("sources", [frozenset({"yandex_direct"}), frozenset({"direct_conversions"}), frozenset()])
def test_missing_source_means_rule_is_not_computed(sources):
    assert audit(snap(sources=sources), TARGET) == (NotEnoughData(RULE, Reason.SOURCE_MISSING),)


def test_empty_snapshot():
    assert audit(dataclasses.replace(snap(), campaign_days=()), TARGET) == ()


# --- Действие, политика, объяснение ---------------------------------------------------------------

FIXTURES = [(snap(), TARGET), (snap(), NO_TARGET), (snap(eval_cost=12000, eval_clicks=120, base_cost=40000,
                                                         base_conv=20), NO_TARGET),
            (snap(eval_cost=90000, eval_clicks=900), TARGET)]


@pytest.mark.parametrize("s, settings", FIXTURES)
def test_never_bid_or_budget_and_policy_keeps_inspect_only(s, settings):
    """Стратегия кампании неизвестна (автостратегии): только «проверить», уровень inspect_only без понижений."""
    f = only(audit(s, settings))
    assert f.action["type"] not in BID_OR_BUDGET_ACTIONS
    d = decide(f)
    assert (d.candidate_level, d.level, d.reasons) == ("inspect_only", "inspect_only", ())


@pytest.mark.parametrize("s, settings", FIXTURES)
def test_deterministic_and_immutable(s, settings):
    first = audit(s, settings)
    assert first == audit(s, settings)
    with pytest.raises(TypeError):
        first[0].action["type"] = "pause"
    with pytest.raises(dataclasses.FrozenInstanceError):
        first[0].lost = None


def test_template_uses_only_finding_numbers():
    text = explain(f := only(audit(snap(), TARGET)), decide(f))
    assert "42 000 ₽" in text and "70 кликов" in text and "9 000 ₽" in text and "3 000 ₽" in text
    assert "ставк" not in text  # рычаг — не ставка
    baseline = only(audit(snap(), NO_TARGET))
    assert "Укажите целевой CPA" in explain(baseline, decide(baseline))


@pytest.mark.parametrize("s, settings", FIXTURES)
def test_recoverable_is_unavailable_not_a_copy_of_lost(s, settings):
    """ARCHITECTURE §4: у «проверить» нет обоснованной формулы прогноза — «Можно сэкономить» не завышается копией
    exposure, а честно unavailable. Основа exposure — весь расход кампании за окно."""
    f = only(audit(s, settings))
    assert f.lost.amount > 0 and f.lost.calculation_type == "estimated"
    assert (f.recoverable.amount, f.recoverable.calculation_type) == (None, "unavailable")
    assert f.recoverable.unit == "rub" and f.recoverable.period == f.lost.period
    assert f.exposure_basis == SPEND_CAMPAIGN
