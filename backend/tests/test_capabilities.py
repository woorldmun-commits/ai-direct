"""Capability Resolver (docs/INTELLIGENCE_V2_CONTRACTS.md §3): что система вправе утверждать и делать."""

import dataclasses

import pytest

from app.intelligence.actions.capabilities import (
    ActionCandidate, ActionType, AnalysisInputs, CapabilityResult, CapabilityStatus, RejectedAction,
    action_capabilities, resolve_action, resolve_analysis, usable_in_recommendation)
from app.intelligence.contracts.sufficiency import ActionLevel as L
from app.sources.campaigns import STRATEGY_ACTIONS, Strategy

S = CapabilityStatus
DIRECT_METRIKA = frozenset({"yandex_direct", "yandex_metrika"})


def inputs(**kw):
    base = dict(sources=DIRECT_METRIKA, has_conversion_definition=True, has_revenue=False,
                has_search_query_stats=False, has_placement_stats=True, has_experiment_control=False)
    return AnalysisInputs(**{**base, **kw})


def statuses(**kw):
    return {k: v.status for k, v in resolve_analysis(inputs(**kw)).items()}


def test_docs_example_direct_metrika_without_revenue():
    got = statuses()
    assert got["cpa"] is S.SUPPORTED
    assert got["revenue"] is S.UNSUPPORTED and got["roas"] is S.UNSUPPORTED
    assert got["search_analysis"] is S.PARTIAL
    assert got["placement_analysis"] is S.SUPPORTED
    assert got["experiment"] is S.UNSUPPORTED


def test_placement_analysis_only_with_placement_stats():
    assert statuses(has_placement_stats=False)["placement_analysis"] is S.UNSUPPORTED


def test_search_analysis_supported_with_query_stats():
    assert statuses(has_search_query_stats=True)["search_analysis"] is S.SUPPORTED


def test_revenue_enables_roas():
    got = statuses(has_revenue=True)
    assert got["revenue"] is S.SUPPORTED and got["roas"] is S.SUPPORTED


def test_cpa_needs_conversion_definition_and_direct():
    assert statuses(has_conversion_definition=False)["cpa"] is S.UNSUPPORTED
    assert statuses(sources=frozenset({"yandex_metrika"}))["cpa"] is S.UNSUPPORTED


def test_experiment_supported_with_control():
    assert statuses(has_experiment_control=True)["experiment"] is S.SUPPORTED


def test_no_direct_means_nothing_supported_with_reason():
    res = resolve_analysis(inputs(sources=frozenset()))
    for key in ("cpa", "roas", "search_analysis", "placement_analysis"):
        assert res[key].status is S.UNSUPPORTED and "source_missing" in res[key].reasons


def test_unknown_presence_gives_unknown_not_false():
    got = statuses(has_placement_stats=None, has_revenue=None, has_experiment_control=None)
    assert got["placement_analysis"] is S.UNKNOWN and got["revenue"] is S.UNKNOWN and got["roas"] is S.UNKNOWN
    assert got["experiment"] is S.UNKNOWN


def test_unknown_is_never_usable_in_recommendation():
    assert {s: usable_in_recommendation(s) for s in S} == {
        S.SUPPORTED: True, S.PARTIAL: True, S.UNSUPPORTED: False, S.UNKNOWN: False}


def test_unsupported_results_carry_a_reason():
    for res in resolve_analysis(inputs()).values():
        assert res.status is S.SUPPORTED or res.reasons


# --- действия по стратегии ------------------------------------------------------------------------

def test_manual_strategy_allows_bid_not_target_cpa():
    caps = action_capabilities(Strategy.MANUAL_BIDDING)
    assert caps["change_bid"].status is S.SUPPORTED
    assert caps["change_target_cpa"].status is S.UNSUPPORTED


def test_auto_cpa_allows_target_cpa_not_bid():
    caps = action_capabilities(Strategy.AUTO_CPA)
    assert caps["change_target_cpa"].status is S.SUPPORTED
    assert caps["change_bid"].status is S.UNSUPPORTED and "auto_strategy" in caps["change_bid"].reasons


@pytest.mark.parametrize("strategy", [None, Strategy.UNKNOWN])
def test_missing_or_unknown_strategy_is_unknown(strategy):
    caps = action_capabilities(strategy)
    assert caps["change_bid"].status is S.UNKNOWN and caps["change_target_cpa"].status is S.UNKNOWN
    assert not usable_in_recommendation(caps["change_bid"].status)


def test_strategy_capabilities_use_existing_matrix_ceiling():
    """Потолок уровня берётся из STRATEGY_ACTIONS, таблица не дублируется."""
    for strategy, (lever, ceiling) in STRATEGY_ACTIONS.items():
        if strategy is Strategy.UNKNOWN:
            continue
        caps = action_capabilities(strategy)
        for r in caps.values():
            if r.status is S.SUPPORTED:
                assert r.max_level.value == {"change": "change_candidate"}.get(ceiling, ceiling)
        assert (lever in ("change_bid", "change_target_cpa")) == any(
            r.status is S.SUPPORTED for r in caps.values())


@pytest.mark.parametrize("strategy", [Strategy.AUTO_CLICKS, Strategy.AUTO_CPC, Strategy.MAX_CONVERSIONS,
                                      Strategy.PAY_FOR_CONVERSION, Strategy.SERVING_OFF, Strategy.UNSUPPORTED])
def test_strategies_without_supported_lever_reject_both(strategy):
    assert all(r.status is S.UNSUPPORTED and r.reasons for r in action_capabilities(strategy).values())


# --- ActionCandidate ------------------------------------------------------------------------------

def candidate(action=ActionType.CHANGE_BID, **kw):
    base = dict(action_type=action, object="campaign:1", current_state={"bid": "10"}, target_state={"bid": "8"},
                preconditions=("manual strategy",), reason="CPA выше цели", evidence_ids=("ev1",), risk="medium",
                reversibility="reversible", execution_mode="recommend_only", verification_plan="сравнить CPA через 7 дней")
    return ActionCandidate(**{**base, **kw})


def test_action_vocabulary_matches_spec_54():
    assert {a.value for a in ActionType} == {
        "inspect", "monitor", "fix_tracking", "fix_goal", "investigate", "change_target_cpa", "change_bid",
        "exclude_placement", "add_negative_keyword", "adjust_geo", "adjust_device", "adjust_schedule",
        "redistribute_budget", "change_creative", "run_experiment", "do_nothing"}


def test_candidate_fields_match_spec_54():
    assert [f.name for f in dataclasses.fields(ActionCandidate)] == [
        "action_type", "object", "current_state", "target_state", "preconditions", "reason", "evidence_ids",
        "risk", "reversibility", "execution_mode", "verification_plan"]


def test_evidence_required_except_inspect_monitor_do_nothing():
    with pytest.raises(ValueError, match="evidence"):
        candidate(evidence_ids=())
    for a in (ActionType.INSPECT, ActionType.MONITOR, ActionType.DO_NOTHING):
        assert candidate(a, evidence_ids=(), target_state=None, verification_plan=None).evidence_ids == ()


def test_candidate_validates_enums_and_text():
    for bad in ({"risk": "huge"}, {"reversibility": "maybe"}, {"execution_mode": "auto"}, {"reason": " "},
                {"object": ""}, {"preconditions": ["x"]}):
        with pytest.raises(ValueError):
            candidate(**bad)


def test_candidate_state_is_immutable():
    c = candidate()
    with pytest.raises(TypeError):
        c.target_state["bid"] = "1"


# --- resolve_action -------------------------------------------------------------------------------

def test_manual_strategy_bid_allowed_at_requested_level():
    caps = action_capabilities(Strategy.MANUAL_BIDDING)
    assert resolve_action(candidate(), caps, L.CHANGE_CANDIDATE) == (L.CHANGE_CANDIDATE, ())


def test_auto_strategy_bid_rejected_with_reason():
    caps = action_capabilities(Strategy.AUTO_CPA)
    level, reasons = resolve_action(candidate(), caps, L.CHANGE_CANDIDATE)
    assert level is L.NO_ACTION and reasons and "auto_strategy" in "".join(reasons)


def test_unknown_strategy_rejects_bid_and_target_cpa():
    caps = action_capabilities(None)
    for a in (ActionType.CHANGE_BID, ActionType.CHANGE_TARGET_CPA):
        level, reasons = resolve_action(candidate(a), caps, L.CHANGE_CANDIDATE)
        assert level is L.NO_ACTION and reasons


def test_missing_capability_key_is_treated_as_unknown():
    level, reasons = resolve_action(candidate(), {}, L.REVIEW)
    assert level is L.NO_ACTION and reasons


def test_partial_capability_caps_at_review():
    caps = {"search_analysis": CapabilityResult(S.PARTIAL, ("query_stats_limited",))}
    c = candidate(ActionType.ADD_NEGATIVE_KEYWORD)
    assert resolve_action(c, caps, L.CHANGE_CANDIDATE)[0] is L.REVIEW


def test_non_changing_actions_need_no_capability():
    for a in (ActionType.INSPECT, ActionType.MONITOR, ActionType.DO_NOTHING):
        c = candidate(a, evidence_ids=(), verification_plan=None)
        assert resolve_action(c, {}, L.INSPECT_ONLY) == (L.INSPECT_ONLY, ())


def test_action_without_defined_capability_is_rejected():
    level, _ = resolve_action(candidate(ActionType.ADJUST_GEO), {}, L.CHANGE_CANDIDATE)
    assert level is L.NO_ACTION


@pytest.mark.parametrize("strategy", [None, *Strategy])
@pytest.mark.parametrize("action", list(ActionType))
@pytest.mark.parametrize("level", list(L))
def test_resolve_never_raises_the_level(strategy, action, level):
    c = candidate(action, evidence_ids=("ev1",))
    allowed, _ = resolve_action(c, {**action_capabilities(strategy), **{
        k: v for k, v in resolve_analysis(inputs(has_search_query_stats=True)).items()}}, level)
    assert allowed.rank <= level.rank


def test_supported_lever_respects_strategy_ceiling_lowering_only():
    caps = {"change_bid": CapabilityResult(S.SUPPORTED, (), max_level=L.REVIEW)}
    assert resolve_action(candidate(), caps, L.CHANGE_CANDIDATE)[0] is L.REVIEW
    assert resolve_action(candidate(), caps, L.INSPECT_ONLY)[0] is L.INSPECT_ONLY


def test_rejected_action_record():
    r = RejectedAction(ActionType.CHANGE_BID, "auto_strategy")
    assert r.action_type is ActionType.CHANGE_BID
    with pytest.raises(ValueError):
        RejectedAction(ActionType.CHANGE_BID, "")
