"""Правила @2 (PR-1 «Truth fixes»): источник конверсий и CPA — из реестра метрик (yandex_direct), цели и атрибуция
в доказательствах, досчёт конверсий понижает достаточность данных, пропуск — не ноль. @1 остаются вызываемыми."""

import dataclasses
from datetime import timedelta
from decimal import Decimal

import pytest

from app.audit.policy import DataHealth, decide, decide_v2
from app.intelligence.metrics.definitions import VERSION as METRICS_VERSION
from app.rules import ALL_RULES, RULES
from app.rules.domain import AuditSettings, Finding, NotEnoughData, Reason, run
from app.rules import RULES_V1, RULES_V2
from app.rules.high_cpa import HIGH_CPA_BASELINE, HIGH_CPA_BASELINE_V2, HIGH_CPA_TARGET, HIGH_CPA_TARGET_V2
from app.rules.zero_conv_campaign import ZERO_CONV_CAMPAIGN, ZERO_CONV_CAMPAIGN_V2
from app.rules.zero_conv_placements import ZERO_CONV_PLACEMENTS_V2
from app.sources.conversion import ConversionDefinition
import test_rule_high_cpa as hc
import test_rule_zero_conv_campaign as zc
import test_rule_zero_conv_placements as zp

DEF = ConversionDefinition(555, (111, 222), "last")
NEVER_PARTIAL = hc.D + timedelta(1)  # граница досчёта за последним днём снимка: всё завершено


def hc_view(partial_from=NEVER_PARTIAL, definition=DEF, days=None, **kw):
    s = hc.snap(**kw)
    if days:  # {дата: (расход, конверсии)} поверх итогового дня
        s = dataclasses.replace(s, campaign_days=tuple(
            dataclasses.replace(d, cost=Decimal(days[d.date][0]), conversions=None if days[d.date][1] is None
                                else Decimal(days[d.date][1])) if d.date in days else d for d in s.campaign_days))
    return dataclasses.replace(s, conversion_definition=definition, partial_from=partial_from)


def v2(view, settings):
    return tuple(o for r in (HIGH_CPA_TARGET_V2, HIGH_CPA_BASELINE_V2) for o in run(r, view, settings))


# --- Источник конверсий и CPA ----------------------------------------------------------------------------

@pytest.mark.parametrize("settings, lost_source", [(hc.TARGET, "yandex_direct+user_input"), (hc.NO_TARGET, "yandex_direct")])
def test_high_cpa_v2_labels_come_from_registry(settings, lost_source):
    f = hc.only(v2(hc_view(), settings))
    assert f.rule_version.endswith("@2")
    assert f.evidence["conversions"].source == "yandex_direct"
    assert f.evidence["cpa"].source == "yandex_direct"
    assert f.lost.source == lost_source
    assert all("yandex_metrika" not in x.source for x in (f.lost, f.recoverable, *f.evidence.values()))


def test_high_cpa_v2_baseline_evidence_labels():
    f = hc.only(v2(hc_view(), hc.NO_TARGET))
    assert f.evidence["baseline_conversions"].source == f.evidence["baseline_cpa"].source == "yandex_direct"


def test_high_cpa_v2_evidence_carries_goals_and_attribution():
    f = hc.only(v2(hc_view(), hc.TARGET))
    assert f.evidence_meta["goal_ids"] == "111,222"
    assert f.evidence_meta["attribution_model"] == "last"
    assert f.evidence_meta["metric_definitions"] == METRICS_VERSION


@pytest.mark.parametrize("rule", [HIGH_CPA_TARGET_V2, HIGH_CPA_BASELINE_V2])
def test_high_cpa_v2_without_conversion_definition_has_no_conversion_facts(rule):
    s = hc_view(definition=None)
    settings = hc.TARGET if rule is HIGH_CPA_TARGET_V2 else hc.NO_TARGET
    assert run(rule, s, settings) == (NotEnoughData(rule.rule_version, Reason.SOURCE_MISSING),)


# --- Деление, пропуски, округление -----------------------------------------------------------------------

def test_high_cpa_v2_zero_conversions_is_not_a_division():
    out = hc.only(v2(hc_view(eval_conv=0), hc.TARGET))
    assert out == NotEnoughData("high_cpa_target@2", Reason.NO_CONVERSIONS, "campaign", hc.CID)


def test_high_cpa_v2_unknown_conversions_are_not_zero():
    s = hc_view(days={hc.D: (42000, None)})
    out = hc.only(v2(s, hc.TARGET))
    assert out == NotEnoughData("high_cpa_target@2", Reason.SOURCE_MISSING, "campaign", hc.CID)


def test_high_cpa_v2_unknown_baseline_conversions_are_not_zero():
    s = hc_view(days={hc.D - timedelta(7): (115200, None)})
    out = hc.only(v2(s, hc.NO_TARGET))
    assert out == NotEnoughData("high_cpa_baseline@2", Reason.SOURCE_MISSING, "campaign", hc.CID)


def test_high_cpa_v2_money_has_two_decimals():
    f = hc.only(v2(hc_view(eval_cost=10000, eval_conv=3), hc.TARGET))  # 3333,333… → 3333,33
    assert f.actual == Decimal("3333.33") and f.evidence["cpa"].amount == Decimal("3333.33")
    assert f.actual.as_tuple().exponent == -2 and f.lost.amount == Decimal("999.99")


# --- Досчёт конверсий (partial) --------------------------------------------------------------------------

def test_high_cpa_v2_partial_only_conversions_cap_data_quality_and_policy():
    s = hc_view(partial_from=hc.D - timedelta(2), eval_cost=63000, eval_conv=12)  # всё окно — за дни досчёта
    f = hc.only(v2(s, hc.TARGET))
    assert f.evidence_meta["level_reason"] == "conversions_partial"
    assert f.current_data_quality == "low"  # завершённых конверсий 0: 12 за дни досчёта не считаются
    d = decide_v2(f)
    assert d.level != "change" and "conversions_partial" in d.reasons


def test_high_cpa_v2_complete_days_keep_data_quality():
    f = hc.only(v2(hc_view(eval_cost=63000, eval_conv=12), hc.TARGET))
    assert f.current_data_quality == "high" and "level_reason" not in f.evidence_meta


def test_high_cpa_v2_unknown_partial_boundary_counts_as_partial():
    f = hc.only(v2(hc_view(partial_from=None, eval_cost=63000, eval_conv=12), hc.TARGET))
    assert f.evidence_meta["level_reason"] == "conversions_partial"


def test_high_cpa_v2_mixed_days_are_solid_if_complete_days_alone_exceed_trigger():
    days = {hc.D - timedelta(3): (40000, 10), hc.D: (23000, 2)}  # завершённые дни: CPA 4000 > 3000 на 33%
    f = hc.only(v2(hc_view(partial_from=hc.D - timedelta(2), eval_cost=0, eval_conv=0, days=days), hc.TARGET))
    assert f.actual == Decimal("5250.00") and "level_reason" not in f.evidence_meta
    assert f.current_data_quality == "high"


@pytest.mark.parametrize("complete, quality", [((40000, 0), "low"),       # конверсий нет
                                               ((30000, 10), "medium")])  # CPA завершённых дней = цели, вывод не держится
def test_high_cpa_v2_mixed_days_not_solid_when_complete_days_alone_do_not_trigger(complete, quality):
    days = {hc.D - timedelta(3): complete, hc.D: (63000 - complete[0], 12 - complete[1])}
    f = hc.only(v2(hc_view(partial_from=hc.D - timedelta(2), eval_cost=0, eval_conv=0, days=days), hc.TARGET))
    assert f.evidence_meta["level_reason"] == "conversions_partial" and f.current_data_quality == quality


@pytest.mark.parametrize("complete_conv, quality", [(1, "low"), (2, "low"), (3, "medium"), (9, "medium")])
def test_high_cpa_v2_quality_comes_from_complete_days_conversions(complete_conv, quality):
    """Завершённые дни держат вывод (CPA выше порога), но конверсий в них мало; 10 в сумме с досчётом — не high."""
    days = {hc.D - timedelta(3): (5000 * complete_conv, complete_conv),
            hc.D: (63000 - 5000 * complete_conv, 10 - complete_conv)}
    f = hc.only(v2(hc_view(partial_from=hc.D - timedelta(2), eval_cost=0, eval_conv=0, days=days), hc.TARGET))
    assert f.current_data_quality == quality and f.evidence_meta["level_reason"] == "conversions_partial"
    assert decide_v2(f).level != "change"


# завершённые дни: 10 конверсий; CPA ровно на trigger_delta_pct (10%) выше ориентира → держит; на копейку ниже → нет
@pytest.mark.parametrize("settings, cost, solid", [
    (hc.TARGET, "33000.00", True), (hc.TARGET, "32999.90", False),        # ориентир 3000 → 3300
    (hc.NO_TARGET, "42240.00", True), (hc.NO_TARGET, "42239.00", False),  # baseline 3840 → 4224
])
def test_high_cpa_v2_solid_boundary_is_inclusive_at_trigger(settings, cost, solid):
    days = {hc.D - timedelta(3): (cost, 10), hc.D: ("30000.00", 2)}
    f = hc.only(v2(hc_view(partial_from=hc.D - timedelta(2), eval_cost=0, eval_conv=0, days=days), settings))
    assert ("level_reason" not in f.evidence_meta) is solid
    assert f.current_data_quality == ("high" if solid else "medium")


# --- safety_policy@2: только понижает ----------------------------------------------------------------------

def test_policy_v2_keeps_v1_behaviour_without_new_signals():
    f = hc.only(v2(hc_view(eval_cost=63000, eval_conv=12), hc.TARGET))
    d1, d2 = decide(f), decide_v2(f)
    assert (d2.candidate_level, d2.level, d2.reasons) == (d1.candidate_level, d1.level, d1.reasons)
    assert d2.version == "safety_policy@2" and d1.version == "safety_policy@1"


@pytest.mark.parametrize("conv", [1, 3, 12, 50, 500])
@pytest.mark.parametrize("partial_from", [None, hc.D - timedelta(2), NEVER_PARTIAL])
@pytest.mark.parametrize("health", [DataHealth(), DataHealth(source_failed=False, stale=False)])
def test_policy_v2_unknown_strategy_never_reaches_change(conv, partial_from, health):
    s = hc_view(partial_from=partial_from, eval_cost=5250 * conv, eval_conv=conv)
    f = hc.only(v2(s, hc.TARGET))
    assert f.action["type"] == "decrease_bid"  # кандидат — change
    d = decide_v2(f, health)
    assert d.candidate_level == "change" and d.level != "change" and "strategy_unknown" in d.reasons


def test_policy_v2_unknown_health_does_not_escalate():
    f = hc.only(v2(hc_view(eval_cost=63000, eval_conv=12), hc.TARGET))
    assert decide_v2(f, DataHealth()) == decide_v2(f)
    assert decide_v2(f, DataHealth(source_failed=False, stale=False)) == decide_v2(f)


@pytest.mark.parametrize("health, reason", [(DataHealth(source_failed=True), "source_failed"),
                                            (DataHealth(stale=True), "source_stale")])
def test_policy_v2_failed_or_stale_source_lowers_to_inspect_only(health, reason):
    f = hc.only(v2(hc_view(eval_cost=63000, eval_conv=12), hc.TARGET))
    d = decide_v2(f, health)
    assert d.level == "inspect_only" and reason in d.reasons


@pytest.mark.parametrize("conv", [1, 3, 8, 12, 50])
@pytest.mark.parametrize("health", [DataHealth(), DataHealth(source_failed=True), DataHealth(stale=True)])
def test_policy_v2_never_raises_level(conv, health):
    from app.audit.policy import LEVELS
    s = hc_view(partial_from=hc.D - timedelta(2), eval_cost=5250 * conv, eval_conv=conv)
    d = decide_v2(hc.only(v2(s, hc.TARGET)), health)
    assert LEVELS.index(d.level) <= LEVELS.index(d.candidate_level)
    assert (d.level == d.candidate_level) == (d.reasons == ())


# --- Выбор версий по флагам ---------------------------------------------------------------------------------

def test_active_rules_follow_source_of_truth_flag():
    from app.rules import active_rules
    assert active_rules({}) == RULES_V2 and active_rules({"SOURCE_OF_TRUTH_V2": "0"}) == RULES_V1


def test_mixed_versions_rules_v1_with_policy_v2_are_allowed():
    """Флаги независимы: правила @1 (прежние метки) + safety_policy@2 — рабочая смесь, политика только понижает."""
    from app.audit.policy import decide_active
    from app.rules import active_rules
    env = {"SOURCE_OF_TRUTH_V2": "0"}
    (rule,) = [r for r in active_rules(env) if r.rule_version == "high_cpa_target@1"]
    f = hc.only(run(rule, hc.snap(eval_cost=63000, eval_conv=12), hc.TARGET))
    assert f.rule_version == "high_cpa_target@1"
    assert decide_active(f, env=env).version == "safety_policy@2"
    assert decide_active(f, env={"SAFETY_ENGINE_V2": "0"}).version == "safety_policy@1"


def test_partial_reason_is_one_shared_constant():
    import inspect
    import app.audit.policy as policy
    import app.audit.templates as templates
    from app.rules.evidence import PARTIAL_REASON
    assert PARTIAL_REASON == "conversions_partial"
    assert '"conversions_partial"' not in inspect.getsource(policy)
    assert '"conversions_partial"' not in inspect.getsource(templates)


# --- @1 остаются вызываемыми -------------------------------------------------------------------------------

def test_v1_rules_still_run_with_legacy_labels():
    f = hc.only(tuple(run(HIGH_CPA_TARGET, hc.snap(), hc.TARGET)))
    assert f.rule_version == "high_cpa_target@1" and f.evidence["conversions"].source == "yandex_metrika"
    assert f.evidence["cpa"].source == "yandex_direct+yandex_metrika"
    assert HIGH_CPA_BASELINE.rule_version == "high_cpa_baseline@1"
    f = zc.only(run(ZERO_CONV_CAMPAIGN, zc.snap(), zc.TARGET))
    assert f.rule_version == "zero_conv_campaign@1" and f.evidence["conversions"].source == "yandex_metrika"


def test_registry_of_rules_keeps_both_versions_and_activates_v2_by_default():
    assert {r.rule_version for r in ALL_RULES} >= {"high_cpa_target@1", "high_cpa_baseline@1", "zero_conv_campaign@1",
                                                   "zero_conv_placements@1", "high_cpa_target@2",
                                                   "high_cpa_baseline@2", "zero_conv_campaign@2",
                                                   "zero_conv_placements@2"}
    assert {r.rule_version for r in RULES} == {"high_cpa_target@2", "high_cpa_baseline@2", "zero_conv_campaign@2",
                                               "zero_conv_placements@2"}


def test_old_findings_resolve_to_their_family():
    from app.api.active import FAMILY_OF
    assert FAMILY_OF["high_cpa_target@1"] == FAMILY_OF["high_cpa_target@2"] == "high_cpa"
    assert FAMILY_OF["zero_conv_placements@1"] == "zero_conv_placements"


def test_v2_params_equal_v1_params():
    """Меняются источник, доказательства и досчёт, а не пороги."""
    for new, old in ((HIGH_CPA_TARGET_V2, HIGH_CPA_TARGET), (HIGH_CPA_BASELINE_V2, HIGH_CPA_BASELINE),
                     (ZERO_CONV_CAMPAIGN_V2, ZERO_CONV_CAMPAIGN)):
        assert dict(new.params) == dict(old.params)


# --- zero_conv_campaign@2 -----------------------------------------------------------------------------------

def zc_view(**kw):
    return dataclasses.replace(zc.snap(**kw), conversion_definition=DEF)


def test_zero_conv_campaign_v2_labels_and_definition():
    f = zc.only(run(ZERO_CONV_CAMPAIGN_V2, zc_view(), zc.TARGET))
    assert f.rule_version == "zero_conv_campaign@2"
    assert f.evidence["conversions"].source == "yandex_direct"
    assert f.lost.source == "yandex_direct" and f.recoverable.source == "yandex_direct"
    assert f.evidence["spend_threshold"].source == "user_input"
    assert (f.evidence_meta["goal_ids"], f.evidence_meta["attribution_model"]) == ("111,222", "last")


def test_zero_conv_campaign_v2_baseline_labels():
    s = dataclasses.replace(zc.snap(base_cost=30000, base_conv=10), conversion_definition=DEF)
    f = zc.only(run(ZERO_CONV_CAMPAIGN_V2, s, zc.NO_TARGET))
    assert f.evidence["baseline_conversions"].source == f.evidence["baseline_cpa"].source == "yandex_direct"
    assert f.evidence["spend_threshold"].source == "yandex_direct"


def test_zero_conv_campaign_v2_without_definition():
    out = run(ZERO_CONV_CAMPAIGN_V2, zc.snap(), zc.TARGET)
    assert out == (NotEnoughData("zero_conv_campaign@2", Reason.SOURCE_MISSING),)


def test_zero_conv_campaign_v2_unknown_conversions_stay_unknown():
    s = dataclasses.replace(zc.snap(eval_conv=None), conversion_definition=DEF)
    assert zc.only(run(ZERO_CONV_CAMPAIGN_V2, s, zc.TARGET)).reason is Reason.SOURCE_MISSING


def test_zero_conv_campaign_v2_partial_only_is_capped():
    f = zc.only(run(ZERO_CONV_CAMPAIGN_V2, zc_view(eval_day=zc.D, eval_clicks=150), zc.TARGET))
    assert f.evidence_meta["level_reason"] == "conversions_partial" and f.current_data_quality == "medium"


# --- zero_conv_placements@2 ---------------------------------------------------------------------------------

def zp_run(placements, settings=AuditSettings(), campaign=zp.CAMPAIGN, definition=DEF):
    s = dataclasses.replace(zp.view(campaign, placements), conversion_definition=definition)
    return run(ZERO_CONV_PLACEMENTS_V2, s, settings)


FLAGGED = [zp.pday(zp.CID, "a.ru", zp.DONE, "15000.00", 500, "0")]


def test_zero_conv_placements_v2_labels_and_definition():
    f = zc.only(zp_run(FLAGGED))
    assert f.rule_version == "zero_conv_placements@2"
    assert f.evidence["conversions"].source == "yandex_direct"
    assert f.evidence["campaign_conversions"].source == "yandex_direct"
    assert f.evidence["reference_cpa"].source == "yandex_direct" and f.lost.source == "yandex_direct"
    assert (f.evidence_meta["goal_ids"], f.evidence_meta["attribution_model"]) == ("111,222", "last")


def test_zero_conv_placements_v2_target_mode_keeps_user_input_suffix():
    f = zc.only(zp_run(FLAGGED, AuditSettings(target_cpa=Decimal("1500"))))
    assert f.evidence["reference_cpa"].source == "user_input" and f.lost.source == "yandex_direct+user_input"


def test_zero_conv_placements_v2_without_definition():
    assert zp_run(FLAGGED, definition=None) == (NotEnoughData("zero_conv_placements@2", Reason.SOURCE_MISSING),)


def test_zero_conv_placements_v2_unknown_campaign_conversions_are_not_zero():
    campaign = [zp.cday(zp.CID, zp.TO - timedelta(20), "30000.00", 1000, None)]
    assert zc.only(zp_run(FLAGGED, campaign=campaign)) == NotEnoughData(
        "zero_conv_placements@2", Reason.SOURCE_MISSING, "campaign", zp.CID)
