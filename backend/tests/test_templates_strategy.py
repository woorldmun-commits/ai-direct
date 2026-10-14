"""Шаблонный текст не советует снижать ставку, если рычага «ручная ставка» нет или стратегия неизвестна."""

import pytest

from app.audit.policy import Decision
from app.audit.templates import explain
from test_rule_high_cpa import TARGET, audit, only, snap

REVIEW = Decision("change", "review", ("strategy_unknown",))
CHANGE = Decision("change", "change", ())


def finding():
    return only(audit(snap(eval_cost=63000, eval_conv=12), TARGET))


@pytest.mark.parametrize("decision", [REVIEW, CHANGE])
@pytest.mark.parametrize("strategy", ["unknown", "auto"])
def test_no_bid_cut_text_without_manual_strategy(decision, strategy):
    text = explain(finding(), decision, strategy)
    assert "снизить ставку" not in text and "ставк" not in text.replace("рычаг", "")
    assert "рычаги кампании" in text


def test_strategy_defaults_to_unknown_and_is_neutral():
    assert explain(finding(), REVIEW) == explain(finding(), REVIEW, "unknown")


def test_manual_strategy_keeps_bid_advice():
    f = finding()
    assert f"снизить ставку на {abs(f.action['change_pct'])}%" in explain(f, REVIEW, "manual")
    assert f"Рекомендуется снизить ставку на {abs(f.action['change_pct'])}%." in explain(f, CHANGE, "manual")


def test_numbers_still_come_only_from_the_finding():
    f = finding()
    text = explain(f, REVIEW, "auto")
    assert str(f.delta_pct) in text and "5 250" in text
