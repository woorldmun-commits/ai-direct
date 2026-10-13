"""Стратегия кампании в снимке: пишется вместе со снимком (append-only), аудит берёт её оттуда, safety_policy@2
режет уровень по матрице STRATEGY_ACTIONS, действие для человека — рычаги этой стратегии. Тот же снимок → те же рычаги."""

import dataclasses
from datetime import timedelta

import psycopg
import pytest

from app.audit.policy import decide_v2
from app.audit.present import present_action
from app.sources.conversion import ConversionDefinition
from app.sources.strategy import Strategy
from app.sync.parse import StatRow
from app.sync.snapshot import Snapshot
from app.sync.store import load_strategies, write_snapshot
import test_rule_high_cpa as hc
from test_direct_sync import TO, root  # noqa: F401 — фикстура
from test_metrika_sync import metrika  # noqa: F401 — фикстура
from test_rules_v2 import hc_view, v2
from test_schema import chain, one  # noqa: F401 — фикстура
from test_snapshot_store import DATA_UNTIL
from test_worker_audit import audit, fresh, sync  # noqa: F401 — fresh: autouse-фикстура
from test_worker_sync import ws  # noqa: F401 — фикстура

CID = 12345


def bid_finding(conv=12):
    return hc.only(v2(hc_view(eval_cost=5250 * conv, eval_conv=conv), hc.TARGET))


# --- Политика по стратегии -----------------------------------------------------------------------------------

@pytest.mark.parametrize("strategy, level, reasons", [
    (None, "review", ("strategy_unknown",)),                       # стратегии в снимке нет — как раньше
    (Strategy.MANUAL_BIDDING, "change", ()),
    (Strategy.AUTO_CPA, "change", ()),                             # рычаг — целевой CPA, а не ставка
    (Strategy.PAY_FOR_CONVERSION, "review", ("strategy_pay_for_conversion",)),
    (Strategy.MAX_CONVERSIONS, "inspect_only", ("strategy_max_conversions",)),  # рычага против CPA нет
    (Strategy.UNKNOWN, "inspect_only", ("strategy_unknown",)),     # API вернул незнакомое — только наблюдение
])
def test_bid_change_level_follows_strategy_matrix(strategy, level, reasons):
    d = decide_v2(bid_finding(), strategy=strategy)
    assert (d.candidate_level, d.level, d.reasons) == ("change", level, reasons)


def test_strategy_does_not_cap_placement_exclusion():
    from test_rule_zero_conv_placements import CID as PCID, DONE, evaluate, pday
    (f,) = evaluate([pday(PCID, "a.ru", DONE, "15000.00", 500, "0")])
    assert decide_v2(dataclasses.replace(f, current_data_quality="high"), strategy=Strategy.MAX_CONVERSIONS).level \
        == "review"


@pytest.mark.parametrize("strategy, shown", [
    ("manual_bidding", {"type": "decrease_bid", "change_pct": "-15.00", "execution": "manual"}),
    ("auto_cpa", {"type": "lower_cpa", "strategy": "auto", "execution": "manual", "levers": [
        {"strategy": "auto", "lever": "lower_target_cpa", "change_pct": None},
        {"strategy": "auto", "lever": "check_conversion_goals", "change_pct": None}]}),
])
def test_action_shown_by_strategy_from_meta(strategy, shown):
    raw = {"type": "decrease_bid", "change_pct": -15}
    assert present_action(raw, "change", "high_cpa", {"strategy": strategy}) == shown


# --- Снимок ------------------------------------------------------------------------------------------------

def snapshot_with(rw, ws, base_snapshot, strategies) -> int:
    rows = rw.execute("""SELECT level, campaign_id, date, impressions, clicks, cost, conversions FROM stat_rows
                         WHERE snapshot_id = %s AND level = 'campaign'""", (base_snapshot,)).fetchall()
    snap = Snapshot("x", TO - timedelta(36), TO, TO + timedelta(1), frozenset({"yandex_direct"}),
                    tuple(StatRow(*r) for r in rows), ConversionDefinition(555, (111, 222)),
                    campaign_strategies=strategies)
    run_id = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, started_at)
                        VALUES (%s, %s, 'resync', 'running', now()) RETURNING id""", ws["ws"], ws["account"])
    return write_snapshot(rw, sync_run_id=run_id, workspace_id=ws["ws"], release_id=ws["release"], snapshot=snap,
                          data_until=DATA_UNTIL)


def test_strategy_is_stored_with_snapshot_and_frozen(rw, ws):
    snap = snapshot_with(rw, ws, sync(rw, ws), {CID: Strategy.MANUAL_BIDDING})
    assert load_strategies(rw, snap) == {CID: Strategy.MANUAL_BIDDING}
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("UPDATE snapshots SET campaign_strategies = '{}' WHERE id = %s", (snap,))
    with pytest.raises(psycopg.errors.CheckViolation):
        snapshot_with(rw, ws, snap, {CID: "bogus"})


def test_snapshot_without_strategy_reads_as_empty(rw, ws):
    assert load_strategies(rw, sync(rw, ws)) == {}


def levers(rw, audit_run_id):
    f = rw.execute("""SELECT action, action_level, policy_reasons, evidence_meta FROM findings
                      WHERE audit_run_id = %s AND rule_version = 'high_cpa_target@2'""", (audit_run_id,)).fetchone()
    return f[1], f[2], present_action(f[0], f[1], "high_cpa", f[3])


def test_same_snapshot_gives_same_levers(rw, ws):
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws["ws"],))
    snapshot_with(rw, ws, sync(rw, ws), {CID: Strategy.AUTO_CPA})
    first, second = (levers(rw, audit(rw, ws, key).audit_run_id) for key in ("r1", "r2"))
    assert first == second
    assert first[2]["type"] == "lower_cpa" and first[2]["strategy"] == "auto"   # рычаги автостратегии, не ставка
    assert "strategy_unknown" not in first[1]
