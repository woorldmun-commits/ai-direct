"""Воркер аудита: состав на общий data_cutoff, исключённые аккаунты с причиной, source_failures, идемпотентность
по task_key и жизненный цикл рекомендаций (новая → seen_again → resolved; done и «недостаточно данных» не закрывают)."""

import dataclasses
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.rules.domain import CampaignDay  # noqa: F401 — тип строк снимка в помощниках
from app.sync.parse import StatRow
from app.sync.snapshot import Snapshot
from app.sync.store import write_snapshot
from app.worker import audit as audit_module
from app.worker.audit import Audited, run_audit
from app.worker.sync import Done, Skipped
from test_direct_sync import TO, campaign_tsv, root  # noqa: F401 — root: фикстура
from test_metrika_sync import METRIKA_RULE, metrika  # noqa: F401 — metrika: фикстура
from test_schema import EVENT_AT, EXECUTED, connected, chain, one  # noqa: F401 — chain: фикстура
from test_snapshot_store import DATA_UNTIL
from test_worker_sync import NOW, new_run, work, ws  # noqa: F401 — ws: фикстура

CUTOFF = TO
B_CAMPAIGN = 777


@pytest.fixture(autouse=True)
def fresh(rw, chain):
    """chain заранее создаёт открытую проблему high_cpa по кампании 12345 — закрываем, чтобы аудит начинал с чистого."""
    rw.execute("UPDATE issues SET closed_at = now(), close_reason = 'resolved' WHERE id = %s", (chain["issue"],))


@pytest.fixture
def two(rw, ws):
    """Второй аккаунт Директа (своё подключение) с кампанией 777; оба выбраны для аудита."""
    conn = connected(rw, "direct", ws["ws"], f"b{ws['ws']}")
    b = one(rw, "INSERT INTO direct_accounts (direct_connection_id, is_selected) VALUES (%s, true) RETURNING id", conn)
    ws["root"](f"b{ws['ws']}", campaign=campaign_tsv(cid=B_CAMPAIGN))
    return {**ws, "b": b}


def sync(rw, ws, account=None) -> int:
    """Синхронизация аккаунта через настоящий воркер → id снимка на TO."""
    run_id = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, metrika_counter_id, kind)
                        VALUES (%s, %s, %s, 'scheduled') RETURNING id""",
                 ws["ws"], account or ws["account"], ws["counter"])
    out = work(rw, ws, run_id)
    assert isinstance(out, Done), out
    return out.snapshot_id


def snapshot_like(rw, ws, account, snap_id, *, shift=0, eval_cost=None, eval_conv=None) -> int:
    """Записать снимок, производный от существующего: сдвиг окна на shift дней и/или другой итог последнего дня."""
    rows = rw.execute("""SELECT level, campaign_id, date, impressions, clicks, cost, conversions FROM stat_rows
                         WHERE snapshot_id = %s AND level = 'campaign'""", (snap_id,)).fetchall()
    to = TO + timedelta(shift)
    stat = []
    for level, cid, day, impr, clicks, cost, conv in rows:
        day = day + timedelta(shift)
        if day == to and eval_cost is not None:
            cost, conv = Decimal(eval_cost), Decimal(eval_conv)
        stat.append(StatRow(level, cid, day, impr, clicks, cost, conv))
    from app.sources.conversion import ConversionDefinition
    snap = Snapshot("x", to - timedelta(36), to, to - timedelta(2), frozenset({"yandex_direct"}), tuple(stat),
                    ConversionDefinition(555, (111, 222)))
    run_id = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, started_at)
                        VALUES (%s, %s, 'resync', 'running', now()) RETURNING id""", ws["ws"], account)
    return write_snapshot(rw, sync_run_id=run_id, workspace_id=ws["ws"], release_id=ws["release"], snapshot=snap,
                          data_until=DATA_UNTIL)


def audit(rw, ws, key="a1", cutoff=CUTOFF, now=NOW):
    return run_audit(rw, workspace_id=ws["ws"], task_key=f"{ws['ws']}:{key}", data_cutoff=cutoff,
                     release_id=ws["release"], now=now)


def composition(rw, audit_run_id) -> dict:
    return dict(rw.execute("SELECT direct_account_id, snapshot_id FROM audit_run_snapshots WHERE audit_run_id = %s",
                           (audit_run_id,)).fetchall())


def excluded(rw, audit_run_id):
    return one(rw, "SELECT excluded_accounts FROM audit_runs WHERE id = %s", audit_run_id)


def events(rw, ws, account=None):
    return [r[0] for r in rw.execute("""SELECT e.type FROM recommendation_events e
                                        JOIN recommendations r ON r.id = e.recommendation_id
                                        JOIN issues i ON i.id = r.issue_id
                                        WHERE i.workspace_id = %s AND i.direct_account_id = %s AND i.id <> %s
                                        ORDER BY e.id""",
                                     (ws["ws"], account or ws["account"], ws["issue"])).fetchall()]


def open_issues(rw, ws, account=None):
    return one(rw, """SELECT count(*) FROM issues WHERE workspace_id = %s AND direct_account_id = %s
                      AND closed_at IS NULL AND id <> %s""", ws["ws"], account or ws["account"], ws["issue"])


# --- Состав аудита -------------------------------------------------------------------------------

def test_two_accounts_same_cutoff_one_audit(rw, two):
    sa, sb = sync(rw, two), sync(rw, two, two["b"])
    out = audit(rw, two)
    assert isinstance(out, Audited)
    assert composition(rw, out.audit_run_id) == {two["account"]: sa, two["b"]: sb}
    assert excluded(rw, out.audit_run_id) == []
    objects = sorted(r[0] for r in rw.execute("""SELECT i.object_id FROM findings f JOIN issues i ON i.id = f.issue_id
                                                 WHERE f.audit_run_id = %s""", (out.audit_run_id,)).fetchall())
    assert objects == [B_CAMPAIGN, 12345]  # по выводу на каждый аккаунт, проблемы — у своих аккаунтов


def test_different_cutoffs_are_not_mixed(rw, two):
    """A: снимки на 30-е и на 1-е; B: только на 29-е. Аудит на 30-е берёт A@30, B исключён — не подменяется 29-м."""
    sa = sync(rw, two)
    snapshot_like(rw, two, two["account"], sa, shift=1)                 # более свежий снимок A — на 1-е
    sb = snapshot_like(rw, two, two["b"], sa, shift=-1)                 # у B только 29-е
    out = audit(rw, two)
    assert composition(rw, out.audit_run_id) == {two["account"]: sa}
    assert excluded(rw, out.audit_run_id) == [{"account": two["b"], "reason": "no_snapshot_for_cutoff",
                                               "detail": CUTOFF.isoformat()}]
    assert sb not in composition(rw, out.audit_run_id).values()


def test_unavailable_account_is_excluded_with_reason(rw, two):
    sync(rw, two), sync(rw, two, two["b"])
    first = audit(rw, two, "first")
    assert open_issues(rw, two, two["b"]) == 1
    rw.execute("UPDATE direct_accounts SET status = 'unavailable', unavailable_reason = 'access_denied' WHERE id = %s",
               (two["b"],))
    second = audit(rw, two, "second")
    assert isinstance(second, Audited) and second != first               # аудит не падает целиком
    assert list(composition(rw, second.audit_run_id)) == [two["account"]]
    assert excluded(rw, second.audit_run_id) == [{"account": two["b"], "reason": "direct_unavailable",
                                                  "detail": "access_denied"}]
    assert open_issues(rw, two, two["b"]) == 1                          # не проверяли — не «исчезла»


def test_source_failure_skips_only_rules_that_need_it(rw, ws, monkeypatch, tmp_path):
    """Метрика отказала: CPA по отчёту Директа — вывод; правило, которому нужна Метрика, — SOURCE_MISSING."""
    from app.sources.metrika import MetrikaFixture
    run_id = new_run(rw, ws)
    assert isinstance(work(rw, ws, run_id, metrika_source=MetrikaFixture(tmp_path / "none")), Done)
    monkeypatch.setattr(audit_module, "RULES", audit_module.RULES + (METRIKA_RULE,))
    out = audit(rw, ws)
    assert one(rw, "SELECT count(*) FROM findings WHERE audit_run_id = %s", out.audit_run_id) == 1
    assert one(rw, "SELECT rules_skipped FROM audit_runs WHERE id = %s", out.audit_run_id) == [
        {"account": ws["account"], "rule": "site_goal_health@1", "reason": "source_missing",
         "object_type": None, "object_id": None}]


# --- Идемпотентность и фиксированный cutoff ------------------------------------------------------

def test_same_task_is_one_audit(rw, ws):
    sync(rw, ws)
    first = audit(rw, ws)
    counts = lambda: [one(rw, f"SELECT count(*) FROM {t}") for t in  # noqa: E731
                      ("audit_runs", "findings", "recommendations", "recommendation_events")]
    before = counts()
    assert audit(rw, ws) == first and counts() == before


def test_retry_does_not_pick_snapshot_that_appeared_later(rw, ws):
    """Снимок того же дня, записанный после аудита, не попадает в уже выполненный аудит; новая задача — берёт его."""
    old = sync(rw, ws)
    first = audit(rw, ws, "morning")
    newer = sync(rw, ws)                                                 # досинхронизация в 14:00 на тот же cutoff
    assert audit(rw, ws, "morning") == first and composition(rw, first.audit_run_id) == {ws["account"]: old}
    second = audit(rw, ws, "afternoon")
    assert composition(rw, second.audit_run_id) == {ws["account"]: newer}


def test_nothing_to_audit_and_guard(rw, ws):
    empty_day = CUTOFF - timedelta(5)
    assert audit(rw, ws, "empty", cutoff=empty_day) == Skipped("no_snapshots_for_cutoff", empty_day.isoformat())
    sync(rw, ws)
    rw.execute("UPDATE subscriptions SET status = 'expired' WHERE workspace_id = %s", (ws["ws"],))
    assert audit(rw, ws, "late") == Skipped("subscription_inactive", "expired")
    assert one(rw, "SELECT count(*) FROM audit_runs WHERE task_key LIKE %s", f"{ws['ws']}:%") == 0


# --- Жизненный цикл рекомендаций -----------------------------------------------------------------

def test_same_problem_next_audit_is_seen_again_with_recalculated_action(rw, ws):
    snap = sync(rw, ws)
    audit(rw, ws, "d1")
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws["ws"],))
    snapshot_like(rw, ws, ws["account"], snap)                           # новый снимок того же дня
    second = audit(rw, ws, "d2")
    assert one(rw, "SELECT count(*) FROM recommendations r JOIN issues i ON i.id = r.issue_id "
                   "WHERE i.workspace_id = %s AND i.id <> %s", ws["ws"], ws["issue"]) == 1  # рекомендация та же
    assert events(rw, ws) == ["seen_again"]
    action = one(rw, """SELECT f.action FROM recommendation_events e JOIN findings f ON f.id = e.finding_id
                        WHERE e.type = 'seen_again' AND f.audit_run_id = %s""", second.audit_run_id)
    assert action == {"type": "decrease_bid", "change_pct": -15}        # клиент задал target → ставка, та же проблема
    assert one(rw, "SELECT settings->>'target_cpa' FROM audit_runs WHERE id = %s", second.audit_run_id) == "3000.00"


def test_problem_gone_is_resolved(rw, ws):
    snap = sync(rw, ws)
    audit(rw, ws, "d1")
    snapshot_like(rw, ws, ws["account"], snap, eval_cost=38400, eval_conv=10)  # CPA вернулся к базовому уровню
    audit(rw, ws, "d2")
    assert events(rw, ws) == ["resolved"] and open_issues(rw, ws) == 0
    assert one(rw, "SELECT close_reason FROM issues WHERE workspace_id = %s AND id <> %s",
               ws["ws"], ws["issue"]) == "resolved"


def test_not_enough_data_does_not_resolve(rw, ws):
    snap = sync(rw, ws)
    audit(rw, ws, "d1")
    snapshot_like(rw, ws, ws["account"], snap, eval_cost=42000, eval_conv=0)   # за неделю ноль конверсий
    second = audit(rw, ws, "d2")
    assert events(rw, ws) == [] and open_issues(rw, ws) == 1
    assert {"account": ws["account"], "rule": "high_cpa_baseline@1", "reason": "no_conversions",
            "object_type": "campaign", "object_id": 12345} in \
        one(rw, "SELECT rules_skipped FROM audit_runs WHERE id = %s", second.audit_run_id)


def test_done_recommendation_is_left_for_measurement(rw, ws):
    snap = sync(rw, ws)
    audit(rw, ws, "d1")
    rec, finding = rw.execute("""SELECT r.id, r.finding_id FROM recommendations r JOIN issues i ON i.id = r.issue_id
                                 WHERE i.workspace_id = %s AND i.closed_at IS NULL""", (ws["ws"],)).fetchone()
    rw.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, execution_date,
                                                     created_at)
                  VALUES (%s, 'done', %s, %s, %s, %s)""", (rec, ws["user"], finding, EXECUTED, EVENT_AT))
    snapshot_like(rw, ws, ws["account"], snap, eval_cost=38400, eval_conv=10)
    audit(rw, ws, "d2")
    assert events(rw, ws) == ["done"] and open_issues(rw, ws) == 1      # закроет замер, не resolved


def test_problem_returns_after_resolve_as_new_lifecycle(rw, ws):
    snap = sync(rw, ws)
    audit(rw, ws, "d1")
    snapshot_like(rw, ws, ws["account"], snap, eval_cost=38400, eval_conv=10)
    audit(rw, ws, "d2")
    snapshot_like(rw, ws, ws["account"], snap)                           # CPA снова высокий
    audit(rw, ws, "d3")
    assert one(rw, "SELECT count(*) FROM issues WHERE workspace_id = %s AND id <> %s", ws["ws"], ws["issue"]) == 2
    assert open_issues(rw, ws) == 1
