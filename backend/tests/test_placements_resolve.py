"""zero_conv_placements: открытая проблема закрывается как «решённая» только если её действительно проверили.
Отчёт площадок не пришёл (выключен, упал) или площадка ушла ниже порога — «недостаточно данных», а не resolved
(находка ревью: без отчёта площадок проблема закрывалась сама)."""

from datetime import timedelta
from decimal import Decimal

from app.rules.domain import DIRECT_PLACEMENTS
from app.sources.conversion import ConversionDefinition
from app.sync.parse import PlacementRow, StatRow
from app.sync.snapshot import Snapshot
from app.sync.store import write_snapshot
from test_direct_sync import root  # noqa: F401 — фикстура
from test_metrika_sync import metrika  # noqa: F401 — фикстура
from test_schema import chain  # noqa: F401 — фикстура
from test_worker_audit import DATA_UNTIL, TO, audit, fresh, one, sync  # noqa: F401 — fresh: фикстура
from test_worker_sync import ws  # noqa: F401 — фикстура


def snap_with(rw, ws, base, *, placements: bool, cost="2000", clicks=30, report=None) -> int:
    """Снимок, производный от base: кампании те же; площадка junk-site.example 7 дней с расходом cost и 0 конверсий.
    report — был ли отчёт площадок в синхронизации (по умолчанию — если есть строки площадок)."""
    rows = rw.execute("""SELECT level, campaign_id, date, impressions, clicks, cost, conversions FROM stat_rows
                         WHERE snapshot_id = %s AND level = 'campaign'""", (base,)).fetchall()
    stat = [StatRow(*r) for r in rows]
    cid = rows[0][1]
    if placements:
        stat += [PlacementRow("placement", cid, TO - timedelta(i), 100, clicks, Decimal(cost), Decimal(0),
                              placement="junk-site.example") for i in range(7)]
    sources = {"yandex_direct"} | ({DIRECT_PLACEMENTS} if (placements if report is None else report) else set())
    snap = Snapshot("x", TO - timedelta(36), TO, TO - timedelta(2), frozenset(sources), tuple(stat),
                    ConversionDefinition(555, (111, 222)))
    run_id = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, started_at)
                        VALUES (%s, %s, 'resync', 'running', now()) RETURNING id""", ws["ws"], ws["account"])
    return write_snapshot(rw, sync_run_id=run_id, workspace_id=ws["ws"], release_id=ws["release"], snapshot=snap,
                          data_until=DATA_UNTIL)


def placement_issue(rw, ws):
    return rw.execute("""SELECT closed_at IS NULL, close_reason FROM issues
                         WHERE workspace_id = %s AND issue_type = 'zero_conv_placements'""", (ws["ws"],)).fetchall()


def opened(rw, ws) -> int:
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws["ws"],))
    base = sync(rw, ws)
    snap_with(rw, ws, base, placements=True)
    audit(rw, ws, "p1")
    assert placement_issue(rw, ws) == [(True, None)]
    return base


def skipped(rw, ws, key):
    return one(rw, "SELECT rules_skipped FROM audit_runs WHERE task_key = %s", f"{ws['ws']}:{key}")


def test_placements_report_missing_does_not_resolve(rw, ws):
    """Отчёт площадок выключили (DIRECT_PLACEMENTS_REPORT) или он не пришёл: правило не проверено — не resolved."""
    base = opened(rw, ws)
    snap_with(rw, ws, base, placements=False)
    audit(rw, ws, "p2")
    assert placement_issue(rw, ws) == [(True, None)]
    assert {"account": ws["account"], "rule": "zero_conv_placements@2", "reason": "source_missing",
            "object_type": None, "object_id": None} in skipped(rw, ws, "p2")


def test_placement_below_threshold_keeps_issue_open(rw, ws):
    """Площадка ушла ниже порога, но конверсий так и нет: «недостаточно данных» удерживает проблему открытой."""
    base = opened(rw, ws)
    snap_with(rw, ws, base, placements=True, cost="10", clicks=1)
    audit(rw, ws, "p2")
    assert placement_issue(rw, ws) == [(True, None)]
    assert any(s["rule"] == "zero_conv_placements@2" and s["reason"] == "volume_insufficient"
               for s in skipped(rw, ws, "p2"))


def test_no_network_spend_with_report_resolves(rw, ws):
    """Отчёт пришёл, а расхода в сетях за окно нет: проверено — проблема действительно ушла."""
    base = opened(rw, ws)
    snap_with(rw, ws, base, placements=False, report=True)
    audit(rw, ws, "p2")
    assert placement_issue(rw, ws) == [(False, "resolved")]
