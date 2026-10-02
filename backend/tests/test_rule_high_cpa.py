"""high_cpa_target@1 и high_cpa_baseline@1 на обычных fixtures, без БД (PRD §4.1). Проверяется точная семантика результата, а не «что-то вернулось»."""

import ast
import dataclasses
import hashlib
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.rules.domain import (BID_OR_BUDGET_ACTIONS, AuditSettings, CampaignDay, Finding, NotEnoughData, Reason,
                              SnapshotView, run, windows)
from app.rules import RULES
from app.rules.high_cpa import HIGH_CPA_BASELINE, HIGH_CPA_TARGET, bid_change

D = date(2026, 9, 30)  # последний день снимка
BOTH = frozenset({"yandex_direct", "direct_conversions"})
CID = 12345
TARGET = AuditSettings(target_cpa=Decimal("3000"))
NO_TARGET = AuditSettings()


def snap(eval_cost=42000, eval_conv=8, base_cost=115200, base_conv=30, history_days=37, sources=BOTH, extra=()):
    """37-дневный снимок одной кампании: итоги периода — в последний день, итоги baseline — в последний день baseline,
    остальные дни нулевые (они задают глубину истории)."""
    first = D - timedelta(history_days - 1)
    rows = {first + timedelta(i): [Decimal(0), Decimal(0)] for i in range(history_days)}
    rows[D] = [Decimal(eval_cost), Decimal(eval_conv)]
    if D - timedelta(7) in rows:
        rows[D - timedelta(7)] = [Decimal(base_cost), Decimal(base_conv)]
    days = tuple(CampaignDay(CID, d, cost, 10, conv) for d, (cost, conv) in sorted(rows.items())) + tuple(extra)
    return SnapshotView(snapshot_id=84721, workspace_id=7, direct_account_id=3,
                        period_from=D - timedelta(36), period_to=D, sources=sources, campaign_days=days)


HIGH_CPA_RULES = tuple(r for r in RULES if r.family == "high_cpa")  # другие семейства — свои тесты


def audit(s, settings):
    """Как аудит: все зарегистрированные версии семейства high_cpa; неприменимая версия молчит."""
    return tuple(out for rule in HIGH_CPA_RULES for out in run(rule, s, settings))


def only(result):
    assert len(result) == 1, result
    return result[0]


# --- Режим target --------------------------------------------------------------------------------

def test_target_high_cpa_exact_contract():
    f = only(audit(snap(), TARGET))
    assert isinstance(f, Finding)
    assert (f.rule_version, f.issue_type, f.object_type, f.object_id) == ("high_cpa_target@1", "high_cpa", "campaign", CID)
    assert f.issue_key == hashlib.sha256(f"7|3|high_cpa|campaign|{CID}|".encode()).digest()
    assert (f.reason_code, f.metric, f.reference_type) == ("cpa_above_target", "cpa", "target")
    assert (f.actual, f.reference, f.delta_pct) == (Decimal("5250.00"), Decimal("3000"), Decimal("75.0"))
    assert dict(f.action) == {"type": "decrease_bid", "change_pct": -15}
    assert f.lost.amount == Decimal("18000.00") and f.lost.calculation_type == "estimated" and f.lost.formula
    assert f.lost.source == "yandex_direct+yandex_metrika+user_input"
    assert f.recoverable == f.lost  # target-режим: действие с шагом ставки, прогноз = lost
    assert f.current_data_quality == "medium"  # 8 конверсий в периоде
    assert set(f.evidence) == {"cost", "conversions", "cpa", "target_cpa"}
    assert f.evidence["target_cpa"].source == "user_input"
    assert (f.evidence["cost"].amount, f.evidence["conversions"].amount) == (Decimal(42000), Decimal(8))
    assert f.evidence["cost"].period == windows(D)[0]


def test_target_normal_cpa_gives_nothing():
    assert audit(snap(eval_cost=31000, eval_conv=10), TARGET) == ()  # 3 100 ₽: +3,3% — ниже порога


def test_target_zero_conversions_is_not_enough_data():
    assert only(audit(snap(eval_conv=0), TARGET)) == \
        NotEnoughData("high_cpa_target@1", Reason.NO_CONVERSIONS, "campaign", CID)


@pytest.mark.parametrize("eval_cost, step", [(40000, -15), (56000, -25), (3500 * 8, -5)])
def test_target_bid_step_grows_with_excess_and_is_capped(eval_cost, step):
    """5 000 ₽ → −15%, 7 000 ₽ → −25% (сценарий пересчёта из DATA_MODEL.md), небольшое превышение → минимальный шаг."""
    assert only(audit(snap(eval_cost=eval_cost), TARGET)).action["change_pct"] == step


@pytest.mark.parametrize("delta, change", [
    ("10", -5), ("19.99", -5), ("20", -5), ("36.7", -5), ("39.99", -5), ("40", -10), ("59.99", -10),
    ("60", -15), ("66.7", -15), ("80", -20), ("100", -25), ("133.3", -25), ("500", -25),
])
def test_bid_change_floor_boundaries(delta, change):
    """high_cpa_target@1: floor(delta / 20) шагов по 5%, от 5% до 25%. Границы — в Decimal, без float."""
    assert bid_change(Decimal(delta), HIGH_CPA_TARGET.params) == change


def test_target_v1_params_are_fixed():
    assert dict(HIGH_CPA_TARGET.params) == {
        "mode": "target", "trigger_delta_pct": 10, "step_excess_pct": 20, "bid_change_step_pct": 5,
        "rounding": "floor", "min_bid_change_pct": 5, "max_bid_change_pct": 25,
        "current_high_conversions": 10, "current_medium_conversions": 3,
    }


@pytest.mark.parametrize("eval_cost, expected", [
    (32997, None),   # CPA 3 299,70 ₽ → +9,99%: не срабатывает
    (33000, -5),     # CPA 3 300 ₽ → ровно +10%
    (35997, -5),     # +19,99%
    (41997, -5),     # +39,99% — не превращается в 40,0% и лишний шаг
    (42000, -10),    # ровно +40%
])
def test_target_trigger_and_step_boundaries_end_to_end(eval_cost, expected):
    out = audit(snap(eval_cost=eval_cost, eval_conv=10), TARGET)
    assert (out[0].action["change_pct"] if out else None) == expected


def test_target_mode_does_not_need_history():
    assert isinstance(only(audit(snap(history_days=10), TARGET)), Finding)


# --- Режим baseline ------------------------------------------------------------------------------

def test_baseline_high_cpa_exact_contract():
    """Пример из PRD §4.1: 42 000 / 8 = 5 250 ₽ против 115 200 / 30 = 3 840 ₽ → +36,7%."""
    f = only(audit(snap(), NO_TARGET))
    assert (f.rule_version, f.issue_type) == ("high_cpa_baseline@1", "high_cpa")
    assert (f.reason_code, f.reference_type) == ("cpa_above_baseline", "baseline")
    assert (f.actual, f.reference, f.delta_pct) == (Decimal("5250.00"), Decimal("3840.00"), Decimal("36.7"))
    assert dict(f.action) == {"type": "investigate_cpa_growth", "suggest": "set_target_cpa"}
    assert f.lost.amount == Decimal("11280.00") and f.lost.source == "yandex_direct+yandex_metrika"
    # «Проверить»: прогноза эффекта нет — «Можно сэкономить» недоступно, а не копия lost (ARCHITECTURE §4)
    assert (f.recoverable.amount, f.recoverable.calculation_type) == (None, "unavailable")
    assert dict(f.evidence_meta) == {"baseline_data_quality": "high"}
    assert set(f.evidence) == {"cost", "conversions", "cpa", "baseline_cost", "baseline_conversions", "baseline_cpa"}
    b = f.evidence["baseline_cpa"]
    assert (b.calculation_type, b.formula, b.period) == ("estimated", "period_total_spend / period_total_conversions",
                                                         windows(D)[1])


def test_baseline_normal_cpa_gives_nothing():
    assert audit(snap(eval_cost=38400, eval_conv=10), NO_TARGET) == ()


@pytest.mark.parametrize("base_conv, expected", [
    (0, None), (9, None),            # < 10 → baseline не считается, а не 0 и не бесконечность
    (10, "medium"), (19, "medium"),
    (20, "high"), (30, "high"),
])
def test_baseline_data_quality_thresholds(base_conv, expected):
    out = only(audit(snap(base_cost=3000 * base_conv, base_conv=base_conv), NO_TARGET))
    if expected is None:
        assert out == NotEnoughData("high_cpa_baseline@1", Reason.BASELINE_DATA_INSUFFICIENT, "campaign", CID)
    else:
        assert out.evidence_meta["baseline_data_quality"] == expected


def test_less_than_37_days_history_is_not_enough_data():
    assert only(audit(snap(history_days=36), NO_TARGET)) == \
        NotEnoughData("high_cpa_baseline@1", Reason.BASELINE_HISTORY_INSUFFICIENT, "campaign", CID)


def test_snapshot_shorter_than_37_days_is_not_enough_data():
    s = dataclasses.replace(snap(), period_from=D - timedelta(20))
    assert only(audit(s, NO_TARGET)).reason is Reason.BASELINE_HISTORY_INSUFFICIENT


def test_evaluation_period_does_not_leak_into_baseline():
    """Окна не пересекаются: расход последних 7 дней не попадает в baseline, иначе рост CPA «съедается»."""
    evaluation, baseline = windows(D)
    assert baseline.date_to < evaluation.date_from
    assert (evaluation.date_to - evaluation.date_from).days + 1 == 7
    assert (baseline.date_to - baseline.date_from).days + 1 == 30
    boundary = CampaignDay(CID, evaluation.date_from, Decimal(8000), 10, Decimal(0))  # первый день периода
    f = only(audit(snap(extra=(boundary,)), NO_TARGET))
    assert f.evidence["baseline_cost"].amount == Decimal(115200)
    assert f.evidence["cost"].amount == Decimal(50000)


# --- Источники -----------------------------------------------------------------------------------

@pytest.mark.parametrize("sources", [frozenset({"yandex_direct"}), frozenset({"direct_conversions"}),
                                     frozenset({"yandex_direct", "yandex_metrika"}), frozenset()])
@pytest.mark.parametrize("settings", [TARGET, NO_TARGET])
def test_missing_source_means_rule_is_not_computed(sources, settings):
    """Источника нет → правило не вычисляется вовсе; это не то же самое, что «данных мало»."""
    version = "high_cpa_target@1" if settings.target_cpa else "high_cpa_baseline@1"
    assert audit(snap(sources=sources), settings) == (NotEnoughData(version, Reason.SOURCE_MISSING),)


# --- Инварианты на всех fixtures -----------------------------------------------------------------

FIXTURES = [
    (snap(), TARGET), (snap(), NO_TARGET),
    (snap(eval_cost=31000, eval_conv=10), TARGET), (snap(eval_conv=0), TARGET), (snap(eval_conv=0), NO_TARGET),
    (snap(eval_cost=56000), TARGET), (snap(eval_cost=90000), NO_TARGET),
    (snap(base_conv=9, base_cost=27000), NO_TARGET), (snap(base_conv=15, base_cost=45000), NO_TARGET),
    (snap(history_days=36), NO_TARGET), (snap(history_days=10), TARGET),
    (snap(sources=frozenset({"yandex_direct"})), TARGET),
]


@pytest.mark.parametrize("s, settings", FIXTURES)
def test_invariants(s, settings):
    for out in audit(s, settings):
        if isinstance(out, NotEnoughData):
            assert not hasattr(out, "action")  # недостаточно данных → никакого действия
            continue
        if out.reference_type == "baseline":  # baseline → никогда не ставка и не бюджет
            assert out.action["type"] not in BID_OR_BUDGET_ACTIONS
        assert out.evidence["conversions"].amount > 0  # ноль конверсий → никогда не CPA-рекомендация
        assert out.lost.amount > 0 and out.delta_pct >= HIGH_CPA_TARGET.params["trigger_delta_pct"]


@pytest.mark.parametrize("s, settings", FIXTURES)
def test_deterministic_and_immutable(s, settings):
    first, second = audit(s, settings), audit(s, settings)
    assert first == second
    for out in first:
        with pytest.raises(dataclasses.FrozenInstanceError):
            out.rule_version = "x@1"
        if isinstance(out, Finding):
            with pytest.raises(TypeError):
                out.action["change_pct"] = -50
            with pytest.raises(TypeError):
                out.evidence["cpa"] = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.period_to = D


def test_current_data_quality_does_not_block_action():
    """1 конверсия при заданном target: правило всё равно предлагает кандидата — понижает его политика
    безопасности (tests/test_safety_policy.py), а не правило."""
    f = only(audit(snap(eval_cost=5000, eval_conv=1), TARGET))
    assert f.current_data_quality == "low" and f.action["type"] == "decrease_bid"


@pytest.mark.parametrize("settings", [TARGET, NO_TARGET])
def test_exactly_one_version_of_family_applies(settings):
    applied = [r.rule_version for r in HIGH_CPA_RULES if run(r, snap(), settings)]
    assert applied == (["high_cpa_target@1"] if settings.target_cpa else ["high_cpa_baseline@1"])


def test_versions_share_family_but_keep_own_params():
    assert HIGH_CPA_TARGET.family == HIGH_CPA_BASELINE.family == "high_cpa"
    assert "bid_change_step_pct" in HIGH_CPA_TARGET.params and "bid_change_step_pct" not in HIGH_CPA_BASELINE.params
    assert "baseline_min_conversions" in HIGH_CPA_BASELINE.params


def test_issue_key_is_same_for_target_and_baseline_and_ignores_numbers():
    """Проблема та же, если клиент задал target или CPA изменился: ключ — только из ID."""
    keys = {only(audit(snap(eval_cost=c), st)).issue_key for c in (42000, 56000) for st in (TARGET, NO_TARGET)}
    assert len(keys) == 1


def test_rules_package_is_pure():
    """rules/ не знает о БД, Pydantic, сети, текущем времени и AI-слое."""
    forbidden_modules = {"psycopg", "pydantic", "redis", "httpx", "requests", "arq", "random", "os", "time",
                         "app.ai", "app.contract", "app.db"}
    forbidden_calls = {"now", "today", "utcnow", "time"}
    for path in (Path(__file__).parents[1] / "app" / "rules").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert not any(name == m or name.startswith(m + ".") for m in forbidden_modules), (path.name, name)
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                assert node.attr not in forbidden_calls, (path.name, node.attr)


# --- Регрессии из код-ревью ----------------------------------------------------------------------

def test_zero_cost_baseline_is_not_enough_data_not_a_crash():
    """Конверсии в окне baseline при нулевом расходе: ориентира нет — NOT_ENOUGH_DATA, а не DivisionByZero."""
    assert only(audit(snap(base_cost=0, base_conv=10), NO_TARGET)) == \
        NotEnoughData("high_cpa_baseline@1", Reason.BASELINE_DATA_INSUFFICIENT, "campaign", CID)


def test_paused_campaign_in_old_account_keeps_baseline():
    """Кампания без строк в начале окна (пауза), но аккаунт старый — история есть, baseline считается."""
    other = CampaignDay(999, D - timedelta(36), Decimal(0), 0, Decimal(0))
    (f,) = [o for o in audit(snap(history_days=10, extra=(other,)), NO_TARGET) if o.object_id == CID]
    assert isinstance(f, Finding) and f.reference_type == "baseline"


def test_threshold_uses_exact_cpa_not_rounded():
    """CPA 3 299,995 ₽ → округлённо 3 300,00 (ровно +10%), точно — +9,9998%: правило не срабатывает."""
    assert audit(snap(eval_cost="32999.95", eval_conv=10), TARGET) == ()


def test_non_positive_target_is_rejected():
    with pytest.raises(ValueError):
        AuditSettings(target_cpa=Decimal(0))
