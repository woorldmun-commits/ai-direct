"""Правила за флагом audit_rules_candidates (zero_conv_queries@1, anomaly@2, budget_underuse@1): выключены по умолчанию,
не предлагают ставок и бюджета, тексты запросов не попадают ни в вывод, ни в объяснение. Пороги и суммы — golden-кейсы
evals/cases/{zero_conv_queries,anomaly,budget_underuse}/."""

import dataclasses

from app.rules import ALL_RULES, FLAGGED, RULES, active_rules
from app.rules.domain import BID_OR_BUDGET_ACTIONS, QueryDay, SnapshotView
from evals.golden import evaluate, load_cases

CANDIDATES = FLAGGED["audit_rules_candidates"]
CASES = [c for c in load_cases() if c.name.split("/")[0] in {r.family for r in CANDIDATES}]


def test_flag_is_off_by_default_and_adds_rules_when_on():
    versions = {r.rule_version for r in CANDIDATES}
    assert not versions & {r.rule_version for r in RULES}
    on = active_rules({"AUDIT_RULES_CANDIDATES": "1"})
    assert on[-3:] == CANDIDATES and versions <= {r.rule_version for r in ALL_RULES}
    assert versions == {"zero_conv_queries@1", "anomaly@2", "budget_underuse@1"}


def test_query_text_cannot_reach_rules():
    """Ни у QueryDay, ни у SnapshotView нет поля под текст запроса: правилам нечего передать дальше."""
    assert {f.name for f in dataclasses.fields(QueryDay)} == {"campaign_id", "query_id", "date", "cost", "clicks",
                                                              "conversions"}
    assert not any("text" in f.name for f in dataclasses.fields(SnapshotView))


def test_candidates_only_investigate_and_never_bid_or_budget():
    for case in CASES:
        for o in evaluate(case)[0]:
            if o.rule_version in {r.rule_version for r in CANDIDATES}:
                assert o.action["type"] not in BID_OR_BUDGET_ACTIONS, case.name
                assert o.candidate_level == o.action_level == "inspect_only", case.name
                assert o.shown["type"] == "investigate", case.name
                assert o.card.lost.calculation_type in ("estimated", "unavailable"), case.name


def test_budget_underuse_is_an_opportunity_not_spend_at_risk():
    """У недоиспользования бюджета нет суммы потерь: в итог «Расход с признаками неэффективности» оно не входит."""
    outcomes = [o for c in CASES for o in evaluate(c)[0] if o.rule_version == "budget_underuse@1"]
    assert outcomes and all(o.exposure is None and o.can_save == "unavailable" for o in outcomes)
