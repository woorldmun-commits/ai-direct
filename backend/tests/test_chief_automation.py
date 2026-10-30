"""Durable Chief queue: synthetic DB fixtures, no Yandex calls or external LLM."""
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from types import SimpleNamespace

from app.insights import campaign_stats
from app.tenancy import workspace_scope
from app.worker import chief
from test_campaign_stats import funded, insights_api, req  # noqa: F401
from test_schema import chain, new_workspace  # noqa: F401

NOW = datetime.now(timezone.utc) + timedelta(hours=2)


def audit_job(rw, funded):
    snapshot = rw.execute("SELECT id FROM snapshots WHERE workspace_id=%s"
                          " ORDER BY sealed_at DESC,id DESC LIMIT 1",
                          (funded["ws"],)).fetchone()[0]
    report = campaign_stats.build(rw, funded["ws"], NOW.date(), NOW, days=7)
    cutoff = date.fromisoformat(report["period"]["to"])
    audit = rw.execute("""INSERT INTO audit_runs
        (workspace_id,release_id,kind,task_key,data_cutoff,settings,rules_run)
        VALUES (%s,%s,'scheduled',%s,%s,'{}','{high_cpa_target@1}') RETURNING id""",
        (funded["ws"],funded["release"],f"pilot-sync:test-{snapshot}",cutoff)).fetchone()[0]
    rw.execute("INSERT INTO audit_run_snapshots(audit_run_id,direct_account_id,snapshot_id)"
               " VALUES (%s,%s,%s)", (audit,funded["account"],snapshot))
    return audit


def test_runtime_disabled_by_default_and_requiring_both_approvals():
    assert chief.enabled({}) is False
    assert chief.enabled({"INROU_AGENT_AUTOMATION_ENABLED":"1"}) is False
    assert chief.enabled({"INROU_AGENT_AUTOMATION_ENABLED":"1",
                          "INROU_INTELLIGENCE_ENABLED":"1",
                          "INROU_INTELLIGENCE_REAL_DATA_APPROVED":"1"}) is True


def test_one_job_per_audit_with_fenced_retry_and_history(rw, funded, insights_api):
    rw.execute("SELECT start_registration_trial(%s,%s)", (funded["user"],funded["ws"]))
    audit = audit_job(rw, funded)
    assert chief.enqueue_recent(rw, NOW) == 1
    assert chief.enqueue_recent(rw, NOW) == 0
    job_id, ws = chief.due(rw, NOW)[0]
    assert ws == funded["ws"]
    assert chief.process(rw, job_id, ws, NOW)
    status, attempts, payload = rw.execute(
        "SELECT status,attempts,report FROM chief_analysis_jobs WHERE id=%s",(job_id,)).fetchone()
    assert status in ("completed","blocked","skipped")
    assert attempts == 1
    assert payload["publication_allowed"] is False
    assert chief.process(rw,job_id,ws,NOW) is False
    history = req(insights_api,rw,funded,"intelligence/chief-history")
    assert history.status_code == 200, history.text
    rows = history.json()["items"]
    assert len(rows) == 1 and rows[0]["audit_run_id"] == str(audit)


def test_job_is_tenant_scoped_and_cannot_be_created_by_client(db, rw, funded):
    audit = audit_job(rw, funded)
    assert chief.enqueue_recent(rw,NOW)==1
    with db("app_rw") as client, workspace_scope(client,funded["ws"]):
        assert client.execute("SELECT count(*) FROM chief_analysis_jobs").fetchone()[0]==1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            client.execute("INSERT INTO chief_analysis_jobs(workspace_id,audit_run_id)"
                           " VALUES(%s,%s)",(funded["ws"],audit))
    other = new_workspace(rw)
    with db("app_rw") as client, workspace_scope(client,other):
        assert client.execute("SELECT count(*) FROM chief_analysis_jobs").fetchone()[0]==0


def test_crashed_claim_is_recovered_without_duplicate(rw,funded):
    audit_job(rw,funded)
    chief.enqueue_recent(rw,NOW)
    jid,ws=chief.due(rw,NOW)[0]
    assert chief.claim(rw,jid,ws,NOW)==1
    assert (jid,ws) not in chief.due(rw,NOW)
    assert chief.claim(rw,jid,ws,NOW+timedelta(minutes=4))==2
    assert rw.execute("SELECT attempts FROM chief_analysis_jobs WHERE id=%s",(jid,)).fetchone()[0]==2


def test_wrong_workspace_audit_reference_is_blocked_by_db(rw,funded):
    audit = audit_job(rw,funded)
    other = new_workspace(rw)
    with pytest.raises(psycopg.Error):
        rw.execute("INSERT INTO chief_analysis_jobs(workspace_id,audit_run_id)"
                   " VALUES(%s,%s)",(other,audit))


def test_changed_selected_snapshot_cannot_be_silently_used(rw,funded,monkeypatch):
    rw.execute("SELECT start_registration_trial(%s,%s)",(funded["user"],funded["ws"]))
    audit_job(rw,funded)
    chief.enqueue_recent(rw,NOW)
    jid,ws=chief.due(rw,NOW)[0]
    monkeypatch.setattr(chief, "load_state", lambda *_: SimpleNamespace(
        workspace_status="active",has_analysis_access=True))
    rw.execute("UPDATE direct_accounts SET is_selected=false WHERE id=%s",(funded["account"],))
    assert chief.process(rw,jid,ws,NOW)
    status, report = rw.execute("SELECT status,report FROM chief_analysis_jobs WHERE id=%s",(jid,)).fetchone()
    assert status=="blocked"
    assert "snapshot_scope_changed" in report["reason_codes"]
    assert report["publication_allowed"] is False
