"""Сверка ручного выполнения (audit/verify.py): каждая ветка таблицы исходов, площадки (частично исключены),
reduced reliability, правило сроков. Чистые функции — без БД и сети."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.audit.present import lower_cpa, present_action
from app.audit.verify import (CONFIRMED, NOT_CONFIRMED, PENDING, VERIFY_WINDOW_DAYS, Verification, diff, settle,
                              verify, verify_claim)
from app.sources.direct_params import BidsSummary, ParamsUnavailable, StrategyParams, parse_campaign_params
from test_direct_params import MANUAL, campaign

CLAIMED = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
LATE = CLAIMED + timedelta(days=VERIFY_WINDOW_DAYS)
EARLY = CLAIMED + timedelta(days=1)


def params(read_at=LATE, **kw):
    return parse_campaign_params(campaign(**kw), read_at)


def bids(search, network=None, sig=None):
    s = None if search is None else Decimal(search)
    n = None if network is None else Decimal(network)
    return BidsSummary(10, s, n, sig or f"{search}/{network}")


def manual(search_bid, network_bid=None, read_at=LATE, **kw):
    return replace(params(read_at, search=MANUAL, **kw), bids=bids(search_bid, network_bid))


def auto_cpa(cpa_micros, goal=101, read_at=LATE, **kw):
    return params(read_at, search={"BiddingStrategyType": "AVERAGE_CPA",
                                   "AverageCpa": {"AverageCpa": cpa_micros, "GoalId": goal}}, **kw)


DECREASE = {"type": "decrease_bid", "change_pct": "-15.00", "execution": "manual"}
LOWER_ANY = lower_cpa("-15.00", "unknown")
LOWER_AUTO = lower_cpa("-15.00", "auto")
PLACEMENTS = present_action({"type": "exclude_placements", "placement_ids": [1, 2]}, "review", "zero_conv_placements",
                            {"placement_1_name": "a.ru", "placement_2_name": "games.example.com"})


def investigate(*checks):
    return {"type": "investigate", "topic": "high_cpa", "checks": list(checks), "suggest": None,
            "placements": None, "execution": "manual"}


# --- Нет данных → pending -------------------------------------------------------------------------------------

def test_no_before_state():
    v = verify(DECREASE, None, manual("10"))
    assert (v.status, v.detail, v.final, v.event_type) == (PENDING, "no_before_state", False, None)


def test_after_unavailable():
    v = verify(DECREASE, manual("10"), ParamsUnavailable("access_denied"))
    assert (v.status, v.detail, v.facts) == (PENDING, "after_unavailable", {"reason": "access_denied"})
    assert verify(DECREASE, manual("10"), None).detail == "after_unavailable"


def test_unknown_action_not_verifiable():
    assert verify({"type": "something_new"}, params(), params()).detail == "action_not_verifiable"


def test_different_objects_is_programmer_error():
    with pytest.raises(ValueError):
        verify(DECREASE, params(cid=1), params(cid=2))


def test_bad_reliability():
    with pytest.raises(ValueError):
        verify(DECREASE, params(), params(), reliability="low")


# --- decrease_bid ---------------------------------------------------------------------------------------------

def test_decrease_bid_confirmed():
    v = verify(DECREASE, manual("12.00"), manual("10.20"))
    assert (v.status, v.detail, v.event_type) == (CONFIRMED, "expected_change", "verification_confirmed")
    assert "bids" in v.changed
    assert v.facts["bids_search_mean_before"] == "12.00" and v.facts["bids_search_mean_after"] == "10.20"


def test_decrease_bid_mixed_counts_as_confirmed():
    assert verify(DECREASE, manual("12", "5"), manual("10", "6")).status == CONFIRMED


def test_decrease_bid_opposite():
    v = verify(DECREASE, manual("10"), manual("12"))
    assert (v.status, v.detail) == (NOT_CONFIRMED, "opposite_direction")


def test_decrease_bid_no_change():
    v = verify(DECREASE, manual("10"), manual("10"))
    assert (v.status, v.detail, v.changed) == (NOT_CONFIRMED, "no_change", ())


def test_decrease_bid_irrelevant_change():
    v = verify(DECREASE, manual("10"), manual("10", sites=("b.ru",)))
    assert (v.status, v.detail, v.changed) == (NOT_CONFIRMED, "irrelevant_change", ("excluded_sites",))


def test_decrease_bid_unreadable_bids_pending():
    v = verify(DECREASE, manual("10"), params(search=MANUAL))  # after без ставок (too_many_keywords)
    assert (v.status, v.detail) == (PENDING, "bids_unreadable")


def test_decrease_bid_strategy_switched_away():
    v = verify(DECREASE, manual("10"), auto_cpa(800_000_000))
    assert (v.status, v.detail) == (NOT_CONFIRMED, "irrelevant_change") and "search_strategy" in v.changed


# --- lower_cpa ------------------------------------------------------------------------------------------------

def test_lower_cpa_target_cpa_down():
    v = verify(LOWER_AUTO, auto_cpa(850_000_000), auto_cpa(700_000_000))
    assert (v.status, v.detail, v.changed) == (CONFIRMED, "expected_change", ("search_target_cpa",))
    assert (v.facts["search_target_cpa_before"], v.facts["search_target_cpa_after"]) == ("850.00", "700.00")


def test_lower_cpa_target_cpa_up_is_opposite():
    v = verify(LOWER_AUTO, auto_cpa(700_000_000), auto_cpa(850_000_000))
    assert (v.status, v.detail) == (NOT_CONFIRMED, "opposite_direction")


@pytest.mark.parametrize("after_kw", [{"goal": 202}, {"goals": ((101, 500_000_000), (7, None))}])
def test_lower_cpa_goals_changed(after_kw):
    goals = after_kw.pop("goals", ((101, 500_000_000),))
    v = verify(LOWER_AUTO, auto_cpa(850_000_000), auto_cpa(850_000_000, goals=goals, **after_kw))
    assert (v.status, v.detail) == (CONFIRMED, "expected_change")


def test_lower_cpa_manual_lever_for_unknown_strategy():
    assert verify(LOWER_ANY, manual("10"), manual("9")).status == CONFIRMED


def test_lower_cpa_goal_change_beats_raised_target():
    v = verify(LOWER_AUTO, auto_cpa(700_000_000), auto_cpa(850_000_000, goal=202))
    assert v.status == CONFIRMED


def test_lower_cpa_auto_lever_ignores_bids():
    """Рычаги только авто: ставки (которые на автостратегии не действуют) не подтверждают."""
    v = verify(LOWER_AUTO, manual("10"), manual("9"))
    assert (v.status, v.detail) == (NOT_CONFIRMED, "irrelevant_change")


def test_lower_cpa_no_change_and_irrelevant():
    assert verify(LOWER_AUTO, auto_cpa(850_000_000), auto_cpa(850_000_000)).detail == "no_change"
    v = verify(LOWER_AUTO, auto_cpa(850_000_000), auto_cpa(850_000_000, budget=900_000_000))
    assert (v.detail, v.changed) == ("irrelevant_change", ("daily_budget",))


def test_lower_cpa_unreadable_bids_pending():
    assert verify(LOWER_ANY, manual("10"), params(search=MANUAL)).detail == "bids_unreadable"


# --- exclude_placements ---------------------------------------------------------------------------------------

def test_placements_all_excluded():
    v = verify(PLACEMENTS, params(sites=()), params(sites=("A.ru", "www.games.example.com", "c.ru")))
    assert (v.status, v.detail) == (CONFIRMED, "placements_excluded")
    assert v.facts == {"placements_total": "2", "placements_excluded": "2", "placements_already_excluded": "0"}


def test_placements_partially_excluded_is_not_confirmed():
    v = verify(PLACEMENTS, params(sites=()), params(sites=("a.ru",)))
    assert (v.status, v.detail) == (NOT_CONFIRMED, "placements_partially_excluded")
    assert (v.facts["placements_excluded"], v.facts["placements_total"]) == ("1", "2")
    assert settle(v, CLAIMED, EARLY).final is False  # до конца окна — ещё ждём остальные
    assert settle(v, CLAIMED, LATE).event_type == "verification_not_confirmed"


def test_placements_none_excluded():
    v = verify(PLACEMENTS, params(sites=()), params(sites=("c.ru",)))
    assert (v.status, v.detail) == (NOT_CONFIRMED, "no_change")


@pytest.mark.parametrize("name", [None, "***", ""])
def test_placements_without_names_pending(name):
    action = {**PLACEMENTS, "placements": [{"id": "1", "name": "a.ru"}, {"id": "2", "name": name}]}
    v = verify(action, params(sites=()), params(sites=("a.ru",)))
    assert (v.status, v.detail) == (PENDING, "placement_names_unknown")


# --- investigate ----------------------------------------------------------------------------------------------

def test_investigate_relevant_change():
    v = verify(investigate("search_queries_negative_keywords"), params(), params(negatives=("бесплатно", "даром")))
    assert (v.status, v.detail, v.changed) == (CONFIRMED, "relevant_change", ("negative_keywords",))


def test_investigate_state_always_relevant():
    after = replace(params(), state="SUSPENDED")
    assert verify(investigate("conversion_goals"), params(), after).status == CONFIRMED


def test_investigate_irrelevant_or_no_change_stays_pending():
    v = verify(investigate("conversion_goals"), params(), params(sites=("b.ru",)))
    assert (v.status, v.detail) == (PENDING, "investigate_no_change")
    v = settle(verify(investigate("strategy"), params(), params()), CLAIMED, LATE + timedelta(days=30))
    assert (v.status, v.event_type) == (PENDING, None)  # окно investigate в not_confirmed не переводит


# --- reduced reliability --------------------------------------------------------------------------------------

def test_reduced_placements_already_in_before_confirmed():
    """before прочитан в момент отметки и уже содержит исключение — конечное состояние верно."""
    before = params(sites=("a.ru", "games.example.com"))
    v = verify(PLACEMENTS, before, params(sites=("a.ru", "games.example.com")), reliability="reduced")
    assert (v.status, v.reliability) == (CONFIRMED, "reduced")
    assert v.facts["placements_already_excluded"] == "2"
    assert v.to_payload()["reliability"] == "reduced"


def test_reduced_bid_change_inside_before_not_confirmed():
    """Ставку снизили до отметки: before уже снижен, разницы нет → not_confirmed с пометкой reduced."""
    v = verify_claim(DECREASE, manual("9"), manual("9"), claimed_at=CLAIMED, reliability="reduced")
    assert (v.status, v.detail, v.reliability, v.final) == (NOT_CONFIRMED, "no_change", "reduced", True)


def test_reduced_bid_further_decrease_confirmed():
    v = verify(DECREASE, manual("10"), manual("9"), reliability="reduced")
    assert (v.status, v.reliability) == (CONFIRMED, "reduced")


# --- Правило сроков -------------------------------------------------------------------------------------------

def test_not_confirmed_waits_for_window():
    early = verify_claim(DECREASE, manual("10"), manual("10", read_at=EARLY), claimed_at=CLAIMED)
    assert (early.status, early.final, early.event_type) == (NOT_CONFIRMED, False, None)
    late = verify_claim(DECREASE, manual("10"), manual("10", read_at=LATE), claimed_at=CLAIMED)
    assert late.event_type == "verification_not_confirmed"


def test_confirmed_is_final_immediately():
    v = verify_claim(DECREASE, manual("10"), manual("9", read_at=EARLY), claimed_at=CLAIMED)
    assert v.event_type == "verification_confirmed"


def test_settle_without_read_time_waits():
    v = verify(DECREASE, manual("10"), manual("10"))
    assert settle(v, CLAIMED, None).final is False
    assert settle(v, CLAIMED, LATE - timedelta(seconds=1)).final is False


def test_unavailable_after_window_stays_pending():
    v = verify_claim(DECREASE, manual("10"), ParamsUnavailable("api_unavailable", 60), claimed_at=CLAIMED)
    assert (v.status, v.event_type) == (PENDING, None)


# --- diff и контракт Verification -----------------------------------------------------------------------------

def test_diff_codes():
    before = auto_cpa(850_000_000)
    after = replace(auto_cpa(800_000_000, goal=5, negatives=("x",), budget=1), state="OFF", network=StrategyParams(
        "MAXIMUM_COVERAGE"))
    assert set(diff(before, after)) == {"state", "daily_budget", "search_target_cpa", "search_goal",
                                        "network_strategy", "negative_keywords"}
    limits = params(search={"BiddingStrategyType": "AVERAGE_CPA",
                            "AverageCpa": {"AverageCpa": 850_000_000, "GoalId": 101, "WeeklySpendLimit": 1}})
    assert diff(params(), limits) == ("search_strategy_params",)


def test_verification_contract():
    with pytest.raises(ValueError):
        Verification("done", "no_change")
    with pytest.raises(ValueError):
        Verification(CONFIRMED, "made_up")
    assert Verification(PENDING, "no_before_state").final is False
