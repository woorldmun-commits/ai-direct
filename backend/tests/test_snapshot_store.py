"""Запись снимка в PostgreSQL: атомарность, идемпотентность, запечатанность, частично доступные аккаунты.
Путь целиком: TSV → парсер → санитизация → Snapshot → транзакция БД → снимок из БД → правила."""

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal

import psycopg
import pytest

from app.rules import RULES
from app.rules.domain import AuditSettings, run
from app.sources.direct import DirectFixture
from app.sync.snapshot import Snapshot, SyncFailure, sync_account, sync_accounts, to_view
from app.sync.store import SnapshotNotComplete, SyncRunStateError, load_view, record_failure, write_snapshot
from test_direct_sync import CAMPAIGN_RULES, GOALS, TO, campaign_tsv, query_tsv, root  # noqa: F401 — root: фикстура
from test_schema import chain, one  # noqa: F401 — chain: фикстура

DATA_UNTIL = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)
QUERIES = query_tsv((("диван 8 916 123 45 67", "100.00", ("1", "0")), ("кресло", "40.00", ("0", "0"))))


def sync_run(rw, chain, status="running") -> int:
    return one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, started_at)
                      VALUES (%s, %s, 'scheduled', %s, now()) RETURNING id""", chain["ws"], chain["account"], status)


def fetch(root, login="acc", **kw) -> Snapshot:
    root(login, **kw)
    snap = sync_account(DirectFixture(root.path), login, GOALS, TO)
    assert isinstance(snap, Snapshot), snap
    return snap


def write(rw, chain, run_id, snap) -> int:
    return write_snapshot(rw, sync_run_id=run_id, workspace_id=chain["ws"], release_id=chain["release"],
                          snapshot=snap, data_until=DATA_UNTIL)


def counts(rw, run_id) -> dict:
    return {
        "snapshots": one(rw, "SELECT count(*) FROM snapshots WHERE sync_run_id = %s", run_id),
        "stat_rows": one(rw, """SELECT count(*) FROM stat_rows r JOIN snapshots s ON s.id = r.snapshot_id
                                WHERE s.sync_run_id = %s""", run_id),
        "status": one(rw, "SELECT status FROM sync_runs WHERE id = %s", run_id),
    }


def audit(view, settings=AuditSettings()):
    return tuple(out for rule in CAMPAIGN_RULES for out in run(rule, view, settings))


# --- Запись и чтение -----------------------------------------------------------------------------

def test_write_then_load_gives_same_view_and_same_findings(rw, chain, root):
    snap = fetch(root, query=QUERIES)
    run_id = sync_run(rw, chain)
    snapshot_id = write(rw, chain, run_id, snap)

    assert counts(rw, run_id) == {"snapshots": 1, "stat_rows": len(snap.rows), "status": "succeeded"}
    status, sealed = rw.execute("SELECT status, sealed_at FROM snapshots WHERE id = %s", (snapshot_id,)).fetchone()
    assert status == "complete" and sealed is not None
    loaded = load_view(rw, snapshot_id)
    assert loaded == to_view(snap, snapshot_id, chain["ws"], chain["account"])
    assert audit(loaded) == audit(to_view(snap, snapshot_id, chain["ws"], chain["account"]))
    (finding,) = audit(loaded)
    assert finding.actual == Decimal("5250.00")  # пример PRD §4.1 — теперь из БД

    texts = [r[0] for r in rw.execute("""SELECT t.text_sanitized FROM stat_rows r
                                         JOIN search_query_texts t ON t.id = r.object_id
                                         WHERE r.snapshot_id = %s AND r.level = 'query' ORDER BY 1""",
                                      (snapshot_id,)).fetchall()]
    assert texts == ["диван ***", "кресло"]  # в БД — только санитизированный текст
    assert one(rw, """SELECT count(*) FROM search_query_sightings g JOIN search_query_texts t ON t.id = g.query_id
                      WHERE t.workspace_id = %s""", chain["ws"]) == 2


def test_building_snapshot_cannot_be_loaded_for_audit(rw, chain):
    run_id = sync_run(rw, chain)
    building = one(rw, """INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to,
                            data_until, partial_from, sources)
                          VALUES (%s, %s, %s, '2026-08-25', '2026-09-30', now(), '2026-09-28', '{yandex_direct}')
                          RETURNING id""", chain["ws"], run_id, chain["release"])
    with pytest.raises(SnapshotNotComplete):
        load_view(rw, building)


# --- Атомарность ---------------------------------------------------------------------------------

def test_one_bad_row_rolls_back_everything(rw, chain, root):
    """Последняя строка нарушает CHECK → нет ни снимка, ни уже записанных строк, ни текстов запросов;
    sync_run остаётся running, повтор с правильными данными проходит."""
    snap = fetch(root, query=query_tsv((("уникальный запрос отката", "10.00", ("0", "0")),)))
    bad = dataclasses.replace(snap.rows[-1], clicks=-1)
    run_id = sync_run(rw, chain)
    with pytest.raises(psycopg.errors.CheckViolation):
        write(rw, chain, run_id, dataclasses.replace(snap, rows=snap.rows[:-1] + (bad,)))

    assert counts(rw, run_id) == {"snapshots": 0, "stat_rows": 0, "status": "running"}
    assert one(rw, "SELECT count(*) FROM search_query_texts WHERE text_sanitized = 'уникальный запрос отката'") == 0

    write(rw, chain, run_id, snap)
    assert counts(rw, run_id) == {"snapshots": 1, "stat_rows": len(snap.rows), "status": "succeeded"}


# --- Идемпотентность -----------------------------------------------------------------------------

def test_same_sync_run_written_twice_is_one_snapshot(rw, chain, root):
    snap = fetch(root, query=QUERIES)
    run_id = sync_run(rw, chain)
    first = write(rw, chain, run_id, snap)
    sightings = one(rw, "SELECT count(*) FROM search_query_sightings")
    assert write(rw, chain, run_id, snap) == first
    assert counts(rw, run_id) == {"snapshots": 1, "stat_rows": len(snap.rows), "status": "succeeded"}
    assert one(rw, "SELECT count(*) FROM search_query_sightings") == sightings


def test_new_sync_run_for_same_period_is_new_snapshot(rw, chain, root):
    """Досинхронизация (14:00, 20:00) — намеренно новый снимок: данные дозачитываются."""
    snap = fetch(root)
    assert write(rw, chain, sync_run(rw, chain), snap) != write(rw, chain, sync_run(rw, chain), snap)


def test_cannot_write_into_finished_sync_run(rw, chain, root):
    snap = fetch(root)
    run_id = sync_run(rw, chain)
    record_failure(rw, run_id, SyncFailure("acc", "access_denied"))
    with pytest.raises(SyncRunStateError):
        write(rw, chain, run_id, snap)
    assert counts(rw, run_id) == {"snapshots": 0, "stat_rows": 0, "status": "failed"}


# --- Частично доступные аккаунты -----------------------------------------------------------------

def test_partial_accounts_are_recorded_per_sync_run(rw, chain, root):
    """A — успех, B — нет доступа, C — битый отчёт. У каждого аккаунта свой sync_run и свой снимок:
    снимок B или C не появляется, а по sync_runs видно, какие аккаунты не вошли и почему."""
    root("A")
    root("B", unavailable="access_denied")
    root("C", campaign=campaign_tsv(eval_cost="-1.00"))
    results = sync_accounts(DirectFixture(root.path), ("A", "B", "C"), GOALS, TO)
    runs = {login: sync_run(rw, chain) for login in results}
    for login, result in results.items():
        if isinstance(result, Snapshot):
            write(rw, chain, runs[login], result)
        else:
            record_failure(rw, runs[login], result)

    assert counts(rw, runs["A"])["status"] == "succeeded"
    failed = {login: rw.execute("SELECT status, error_code, error_reason FROM sync_runs WHERE id = %s",
                                (runs[login],)).fetchone() for login in ("B", "C")}
    assert failed == {"B": ("failed", "access_denied", None),
                      "C": ("failed", "invalid_report_format", "negative_value")}
    assert counts(rw, runs["B"])["snapshots"] == counts(rw, runs["C"])["snapshots"] == 0
