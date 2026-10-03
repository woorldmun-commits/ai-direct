"""Воркер замера для zero_conv_placements / zero_conv_campaign: методика — по имени, которое ставит триггер на 'done'
('<issue_type>_measure@2'); список площадок и ориентир CPA — из выполненного вывода, не из текущих настроек.
«Сэкономлено ≈» — только при подтверждённой сверке (manual + confirmed)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from psycopg.types.json import Jsonb

from app.sync.parse import PlacementRow, StatRow, placement_id
from app.sync.snapshot import Snapshot
from app.sync.store import write_snapshot
from app.worker.measure import Measured, Pending, counted_saved, run_measurement, verification_status
from test_direct_sync import root  # noqa: F401 — фикстура
from test_metrika_sync import metrika  # noqa: F401 — фикстура
from test_schema import chain, one, value  # noqa: F401 — фикстура
from test_snapshot_store import DATA_UNTIL
from test_worker_audit import fresh  # noqa: F401 — autouse-фикстура
from test_worker_measure import CID, GOALS, after_window, audited, done, long_subscription  # noqa: F401
from test_worker_sync import ws  # noqa: F401 — фикстура

EXCLUDED = ("avito.ru", "dzen.ru")
OTHER = "mail.ru"


def recommendation_of(rw, ws, issue_type, action, evidence, level="review"):
    """Вывод семейства issue_type в том же аудите (и снимке с тем же определением конверсии), что и high_cpa из
    audited(): issue → finding → explanation → recommendation, как пишет audit/persist.py."""
    audit_run = one(rw, """SELECT f.audit_run_id FROM findings f JOIN issues i ON i.id = f.issue_id
                           WHERE i.workspace_id = %s ORDER BY f.id DESC LIMIT 1""", ws["ws"])
    issue = one(rw, """INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                       VALUES (%s, %s, %s, %s, 'campaign', %s) RETURNING id""",
                ws["ws"], ws["account"], f"{issue_type}{ws['ws']}".encode().ljust(32, b"."), issue_type, CID)
    lost = value(calculation_type="estimated", formula="spend")
    finding = one(rw, """INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable, data_quality,
                           evidence, action, safety_policy, candidate_level, action_level)
                         VALUES (%s, %s, %s, %s, %s, 'medium', %s, %s, 'safety_policy@1', %s, %s) RETURNING id""",
                  audit_run, issue, f"{issue_type}@1", Jsonb(lost), Jsonb(lost), Jsonb(evidence), Jsonb(action),
                  level, level)
    explanation = one(rw, "INSERT INTO explanations (finding_id, source, text, release_id) "
                          "VALUES (%s, 'template', 't', %s) RETURNING id", finding, ws["release"])
    rec = one(rw, "INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s) RETURNING id",
              issue, finding, explanation)
    return rec, finding


def placements_done(rw, ws):
    audited(rw, ws)
    action = {"type": "exclude_placements", "execution": "manual", "placement_ids": [placement_id(p) for p in EXCLUDED]}
    rec, finding = recommendation_of(rw, ws, "zero_conv_placements", action, {"cost": value()})
    return rec, done(rw, ws, rec, finding)


def snapshot(rw, ws, m, campaign, placements=None, settle=3):
    """campaign = (расход до, конв. до, расход после, конв. после); placements = {имя: (до, после)} или None — отчёта
    площадок в снимке нет. Итоги — в последний день окна; окно «после» вне окна дозачёта."""
    to = m["after_to"] + timedelta(settle)
    bc, bv, ac, av = campaign
    rows = [StatRow("campaign", CID, to - timedelta(36), 1, 0, Decimal(0), Decimal(0)),
            StatRow("campaign", CID, m["before_to"], 700, 70, Decimal(bc), Decimal(bv)),
            StatRow("campaign", CID, m["after_to"], 700, 70, Decimal(ac), Decimal(av))]
    for name, (b, a) in (placements or {}).items():
        rows += [PlacementRow("placement", CID, m["before_to"], 100, 30, Decimal(b), Decimal(0), placement=name),
                 PlacementRow("placement", CID, m["after_to"], 100, 30, Decimal(a), Decimal(0), placement=name)]
    sources = frozenset({"yandex_direct"} | ({"direct_placements"} if placements is not None else set()))
    snap = Snapshot("x", to - timedelta(36), to, to - timedelta(2), sources, tuple(rows), GOALS)
    run_id = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, started_at)
                        VALUES (%s, %s, 'resync', 'running', now()) RETURNING id""", ws["ws"], ws["account"])
    return write_snapshot(rw, sync_run_id=run_id, workspace_id=ws["ws"], release_id=ws["release"], snapshot=snap,
                          data_until=DATA_UNTIL)


def measure(rw, ws, m, days=1):
    return run_measurement(rw, m["id"], release_id=ws["release"], now=after_window(m, days))


def result(rw, out):
    return rw.execute("SELECT verdict, saved, effect FROM recommendation_results WHERE id = %s",
                      (out.result_id,)).fetchone()


# --- zero_conv_placements -------------------------------------------------------------------------

def test_placements_measured_by_the_excluded_list_of_the_done_finding(rw, ws):
    """Golden: avito.ru 5 000 → 0, dzen.ru 3 000 → 0 (исключены), mail.ru 2 000 → 2 000 (не исключалась — не в счёт).
    Кампания 50 000 → 42 000, конверсии 10 → 10 → Сэкономлено 8 000 ₽."""
    rec, m = placements_done(rw, ws)
    assert m["policy"] == "zero_conv_placements_measure@2"                 # имя, которое ставит триггер сейчас
    snap = snapshot(rw, ws, m, (50000, 10, 42000, 10), {"avito.ru": (5000, 0), "dzen.ru": (3000, 0), OTHER: (2000, 2000)})
    out = measure(rw, ws, m)
    assert isinstance(out, Measured) and out.verdict == "effect"
    verdict, saved, effect = result(rw, out)
    assert (Decimal(saved["amount"]), saved["snapshot_id"], saved["rule_version"]) == \
        (Decimal("8000.00"), snap, "zero_conv_placements_measure@2")
    assert effect["reason"] == "placements_spend_left_campaign"
    assert measure(rw, ws, m) == out                                       # идемпотентно: тот же итог, без дубля
    assert one(rw, "SELECT count(*) FROM recommendation_results WHERE recommendation_id = %s", rec) == 1


def test_budget_reallocated_is_not_saved(rw, ws):
    _, m = placements_done(rw, ws)
    snapshot(rw, ws, m, (50000, 10, 47000, 11), {"avito.ru": (5000, 0), "dzen.ru": (3000, 0)})
    verdict, saved, effect = result(rw, measure(rw, ws, m))
    assert (verdict, saved, effect["reason"], effect["reallocated"]) == \
        ("not_confirmed", None, "budget_reallocated", "5000.00")


def test_snapshot_without_placement_report_is_insufficient(rw, ws):
    """«Площадки перестали тратить» не выводится из того, что отчёт площадок не запрашивали."""
    _, m = placements_done(rw, ws)
    snapshot(rw, ws, m, (50000, 10, 42000, 10), placements=None)
    verdict, saved, effect = result(rw, measure(rw, ws, m))
    assert (verdict, saved, effect["reason"]) == ("insufficient", None, "placements_not_in_snapshot")


def test_placements_wait_for_final_data_then_insufficient(rw, ws):
    _, m = placements_done(rw, ws)
    assert measure(rw, ws, m, days=0) == Pending("window_open")
    assert measure(rw, ws, m) == Pending("data_not_final")
    snapshot(rw, ws, m, (50000, 10, 42000, 10), {"avito.ru": (5000, 0)}, settle=1)   # конец окна ещё в дозачёте
    assert measure(rw, ws, m, days=14) == Pending("data_not_final")
    out = measure(rw, ws, m, days=15)                                      # 14 дней ожидания прошли
    assert result(rw, out)[0] == "insufficient"


# --- zero_conv_campaign ---------------------------------------------------------------------------

def campaign_done(rw, ws, evidence):
    """В v1.0 действие zero_conv_campaign — «проверить» (inspect_only): 'done' по нему БД не пустит и замера не будет.
    Здесь вывод уровня review — так методика проверяется на случай, когда действие станет выполнимым."""
    audited(rw, ws)
    rec, finding = recommendation_of(rw, ws, "zero_conv_campaign",
                                     {"type": "investigate_zero_conversions"}, evidence)
    return rec, done(rw, ws, rec, finding)


def test_zero_conv_campaign_uses_reference_of_the_done_finding(rw, ws):
    """Ориентир — target_cpa из evidence выполненного вывода (3 000), не из текущих настроек workspace (меняем на
    100 после 'done' — на замер не влияет). До 21 000 / 0, после 6 000 / 3 → Сэкономлено 15 000 ₽."""
    _, m = campaign_done(rw, ws, {"target_cpa": value(amount="3000.00", source="user_input")})
    assert m["policy"] == "zero_conv_campaign_measure@2"
    rw.execute("UPDATE workspace_settings SET target_cpa = 100 WHERE workspace_id = %s", (ws["ws"],))
    snapshot(rw, ws, m, (21000, 0, 6000, 3))
    verdict, saved, effect = result(rw, measure(rw, ws, m))
    assert (verdict, Decimal(saved["amount"]), effect["reference_cpa"]) == ("effect", Decimal("15000.00"), "3000.00")


def test_zero_conv_campaign_without_reference_is_not_confirmed(rw, ws):
    _, m = campaign_done(rw, ws, {"cost": value()})                       # абсолютный порог: ориентира нет
    snapshot(rw, ws, m, (21000, 0, 6000, 3))
    verdict, saved, effect = result(rw, measure(rw, ws, m))
    assert (verdict, saved, effect["reason"]) == ("not_confirmed", None, "no_reference_cpa")


# --- «Сэкономлено ≈» и сверка ---------------------------------------------------------------------

@pytest.mark.parametrize("status, counted", [("confirmed", True), ("pending", False), ("not_confirmed", False)])
def test_saved_counts_only_after_confirmed_verification(rw, ws, status, counted):
    """Сверку пишет другой воркер; её статус подставлен. Сам замер от сверки не зависит — меняется только то, входит
    ли его saved в сумму."""
    rec, m = placements_done(rw, ws)
    snapshot(rw, ws, m, (50000, 10, 42000, 10), {"avito.ru": (5000, 0), "dzen.ru": (3000, 0)})
    out = measure(rw, ws, m)
    seen = []

    def reader(conn, recommendation_id, done_event_id):
        seen.append((recommendation_id, done_event_id))
        return status
    got = counted_saved(rw, out.result_id, verification=reader)
    assert (got is not None) == counted and seen == [(rec, one(rw, "SELECT done_event_id FROM measurements "
                                                                  "WHERE id = %s", m["id"]))]
    if counted:
        assert Decimal(got["amount"]) == Decimal("8000.00")


def test_without_verification_events_status_is_pending_and_not_counted(rw, ws):
    rec, m = placements_done(rw, ws)
    snapshot(rw, ws, m, (50000, 10, 42000, 10), {"avito.ru": (5000, 0), "dzen.ru": (3000, 0)})
    out = measure(rw, ws, m)
    done_event = one(rw, "SELECT done_event_id FROM measurements WHERE id = %s", m["id"])
    assert verification_status(rw, rec, done_event) == "pending"
    assert counted_saved(rw, out.result_id) is None
    assert counted_saved(rw, -1) is None
