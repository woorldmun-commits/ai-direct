"""Durable, scoped, read-only analysis after the completed scheduled audit."""
import json
import os
from datetime import datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from app.insights import campaign_stats
from app.intelligence.contracts import AnalysisContext, SourceReference, decimal_number
from app.intelligence.economics import calculate_metrics
from app.intelligence.specialist_runtime import chief_analyze
from app.tenancy import workspace_scope
from app.worker.guard import load_state
from app.worker.measure import DATA_TIMEZONE


def enabled(env=None):
    env = os.environ if env is None else env
    return all((env.get(key) or "").lower() in ("1", "true")
               for key in ("INROU_AGENT_AUTOMATION_ENABLED",
                           "INROU_INTELLIGENCE_ENABLED",
                           "INROU_INTELLIGENCE_REAL_DATA_APPROVED"))


def enqueue_recent(conn, now):
    return len(conn.execute("""
        INSERT INTO chief_analysis_jobs(workspace_id,audit_run_id)
        SELECT a.workspace_id,a.id FROM audit_runs a JOIN workspaces w ON w.id=a.workspace_id
        WHERE a.task_key LIKE 'pilot-sync:%%' AND a.created_at >= %s - interval '7 days'
          AND w.status='active'
          AND EXISTS(SELECT 1 FROM audit_run_snapshots s WHERE s.audit_run_id=a.id)
        ON CONFLICT(audit_run_id) DO NOTHING RETURNING id
    """, (now,)).fetchall())


def due(conn, now):
    return conn.execute("""
        SELECT id,workspace_id FROM chief_analysis_jobs
        WHERE status IN ('queued','running') AND available_at<=%s
        ORDER BY available_at,id LIMIT 12
    """, (now,)).fetchall()


def claim(conn, job_id, ws, now):
    with conn.transaction():
        row = conn.execute("""
            SELECT attempts FROM chief_analysis_jobs WHERE id=%s AND workspace_id=%s
              AND status IN ('queued','running') AND available_at<=%s FOR UPDATE SKIP LOCKED
        """, (job_id, ws, now)).fetchone()
        if row is None:
            return None
        attempt = row[0] + 1
        if attempt > 4:
            conn.execute("""UPDATE chief_analysis_jobs SET status='failed',finished_at=%s,
                error_code='retry_exhausted' WHERE id=%s""", (now, job_id))
            return None
        conn.execute("""UPDATE chief_analysis_jobs SET status='running', attempts=%s,
            available_at=%s WHERE id=%s""", (attempt, now+timedelta(minutes=3), job_id))
        return attempt


def analyze(conn, ws, audit_id, now):
    audit = conn.execute("SELECT data_cutoff,task_key FROM audit_runs WHERE id=%s AND workspace_id=%s",
                         (audit_id, ws)).fetchone()
    if not audit or not audit[1].startswith("pilot-sync:"):
        return "blocked", {"reason_codes": ["audit_unavailable"], "publication_allowed": False}
    pinned = {int(row[0]) for row in conn.execute(
        "SELECT snapshot_id FROM audit_run_snapshots WHERE audit_run_id=%s", (audit_id,))}
    state = load_state(conn, ws, None, now)
    if state.workspace_status != "active" or not state.has_analysis_access:
        return "skipped", {"reason_codes": ["access_expired"], "publication_allowed": False}
    today = now.astimezone(DATA_TIMEZONE).date()
    data = campaign_stats.build(conn, ws, today, now, days=7)
    provenance = data["provenance"]
    actual = {int(p["snapshot_id"]) for p in provenance}
    if (not pinned or pinned != actual or not data["scope"]["complete"]
            or data["period"]["to"] != audit[0].isoformat()):
        return "blocked", {"reason_codes": ["snapshot_scope_changed"], "publication_allowed": False}
    end = datetime.fromisoformat(data["period"]["to"]).date()
    start = datetime.fromisoformat(data["period"]["from"]).date()
    sealed = max(datetime.fromisoformat(p["sealed_at"]) for p in provenance)
    if sealed.tzinfo is None:
        return "blocked", {"reason_codes": ["snapshot_clock_invalid"], "publication_allowed": False}
    definitions = {json.dumps(p["conversion_definition"], sort_keys=True) for p in provenance}
    definition = next(iter(definitions)) if len(definitions) == 1 and all(
        p["conversion_definition"] is not None for p in provenance) else None
    partial = any(m["amount"] is None or m["data_status"] != "complete"
                  for m in data["summary"].values())
    partial |= any(d["metrics"]["cost"]["amount"] is None
                   or d["metrics"]["cost"]["data_status"] != "complete" for d in data["daily"])
    quality = ("stale" if now-sealed > timedelta(hours=72) or (today-end).days > 3
               else "partial" if partial else "complete")
    accounts = tuple(sorted(int(p["ad_account"].removeprefix("acc_")) for p in provenance))
    context = AnalysisContext(workspace_id=ws, account_ids=accounts, currency="RUB",
        timezone="Europe/Moscow", period_start=start, period_end=end+timedelta(days=1),
        as_of=now, quality_status=quality, conversion_definition=definition,
        cost_definition="Direct Reports Cost as stored in sealed snapshots")
    source = SourceReference(id="audit-snapshots",workspace_id=ws,account_ids=accounts,
        provider="yandex_direct",source_kind="live_read",fetched_at=sealed,
        period_start=context.period_start,period_end=context.period_end,currency="RUB",
        conversion_definition=definition,cost_definition=context.cost_definition,quality_status=quality,
        raw_record_refs=tuple("snapshot:"+str(i) for i in sorted(pinned)))
    inputs = {key: decimal_number(data["summary"][key]["amount"])
              for key in ("cost","impressions","clicks","conversions")}
    result = calculate_metrics(context, inputs, (source,))
    cost, conv = inputs["cost"], inputs["conversions"]
    expected_cpa = cost/conv if cost is not None and conv is not None and conv>0 else None
    if expected_cpa != result.metrics["cpa"].value:
        raise ValueError("financial_verification_failed")
    profile = conn.execute("SELECT payload FROM intelligence_profiles WHERE workspace_id=%s"
                           " ORDER BY revision DESC LIMIT 1", (ws,)).fetchone()
    report = chief_analyze(result,daily=tuple(data["daily"]),profile=profile[0] if profile else None)
    report["audit_run_id"] = str(audit_id)
    report["snapshot_ids"] = [str(i) for i in sorted(pinned)]
    report["limitations"] = ["Только проверка агрегатов", "Причинная экономия не доказана",
                             "Внешний LLM и изменение рекламы выключены"]
    return ("completed" if report["status"] == "review_required" else "blocked"), report


def process(conn, job_id, ws, now):
    """Lease + fencing attempt makes concurrent/restarted workers safe."""
    attempt = claim(conn, job_id, ws, now)
    if attempt is None:
        return False
    try:
        row = conn.execute("SELECT audit_run_id FROM chief_analysis_jobs "
                           "WHERE id=%s AND workspace_id=%s AND status='running' AND attempts=%s",
                           (job_id, ws, attempt)).fetchone()
        if row is None:
            return False
        with workspace_scope(conn, ws):
            status, report = analyze(conn, ws, row[0], now)
        conn.execute("""UPDATE chief_analysis_jobs SET status=%s,report=%s,finished_at=%s,
            error_code=NULL WHERE id=%s AND workspace_id=%s
            AND status='running' AND attempts=%s""",
            (status, Jsonb(report), now, job_id, ws, attempt))
        return True
    except psycopg.OperationalError:
        raise
    except Exception:
        # No external source values, text or tokens in the error log or database.
        final = attempt >= 4
        conn.execute("""UPDATE chief_analysis_jobs SET status=%s,finished_at=%s,
            error_code='diagnostic_failed',available_at=%s
            WHERE id=%s AND workspace_id=%s AND status='running' AND attempts=%s""",
            ("failed" if final else "queued", now if final else None,
             now + timedelta(seconds=min(600, 30 * (2 ** attempt))),
             job_id, ws, attempt))
        return False
