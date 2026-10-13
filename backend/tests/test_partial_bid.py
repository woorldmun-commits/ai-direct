"""high_cpa_target@2 на днях досчёта конверсий: «снизить ставку» как изменение (change) не выдаётся. Правила (rules/)
здесь не меняются — тест фиксирует, что гарантирует связка правило → safety_policy@2 → показ, а что нет."""

from datetime import timedelta

import pytest

from app.audit.policy import decide_v2
from app.audit.present import present_action
from app.audit.templates import explain
from app.sources.strategy import Strategy
import test_rule_high_cpa as hc
from test_rules_v2 import hc_view, v2

PARTIAL_FROM = hc.D - timedelta(2)
# завершённые дни: CPA = цели (вывод не держится) → medium; всё превышение — за дни досчёта
NOT_SOLID = {hc.D - timedelta(3): (30000, 10), hc.D: (33000, 2)}
ONLY_PARTIAL = None  # всё окно — за дни досчёта: завершённых конверсий нет → low


def partial_finding(days):
    kw = dict(eval_cost=0, eval_conv=0, days=days) if days else dict(eval_cost=63000, eval_conv=12)
    f = hc.only(v2(hc_view(partial_from=PARTIAL_FROM, **kw), hc.TARGET))
    assert f.action["type"] == "decrease_bid" and f.evidence_meta["level_reason"] == "conversions_partial"
    return f


@pytest.mark.parametrize("days", [NOT_SOLID, ONLY_PARTIAL])
@pytest.mark.parametrize("strategy", [None, Strategy.MANUAL_BIDDING, Strategy.AUTO_CPA])
def test_partial_days_never_give_bid_change(days, strategy):
    f = partial_finding(days)
    d = decide_v2(f, strategy=strategy)
    assert d.level != "change" and "conversions_partial" in d.reasons
    meta = {"strategy": strategy.value} if strategy else {}
    assert present_action(dict(f.action), d.level, "high_cpa", meta)["type"] != "decrease_bid"


@pytest.mark.xfail(strict=True, reason="дыра: на review при ручной стратегии показ предлагает снизить ставку на N% "
                                       "(рычаг lower_cpa.decrease_bid и текст объяснения), хотя конверсии досчитываются")
def test_partial_days_do_not_suggest_bid_at_review_with_manual_strategy():
    f = partial_finding(NOT_SOLID)
    d = decide_v2(f, strategy=Strategy.MANUAL_BIDDING)
    assert d.level == "review"
    shown = present_action(dict(f.action), d.level, "high_cpa", {"strategy": "manual_bidding"})
    assert all(lever["lever"] != "decrease_bid" for lever in shown.get("levers", ()))
    assert "снизить ставку" not in explain(f, d, "manual")
