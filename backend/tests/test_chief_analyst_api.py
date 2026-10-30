"""Chief API always respects existing tenant and real-data gates."""
from dataclasses import replace
from datetime import datetime, timedelta

from app.intelligence.specialist_runtime import ADDITIONAL_AGENTS
from test_campaign_stats import funded, insights_api, req  # noqa: F401
from test_api_support import user
from test_schema import chain  # noqa: F401


def test_chief_endpoint_read_only_gated_and_dispatched(insights_api, rw, funded, monkeypatch):
    path = "intelligence/chief-analyst?days=7"
    assert req(insights_api, rw, funded, path).json() == {
        "available": False, "reason": "real_data_approval_required"
    }
    insights_api.app.state.settings = replace(
        insights_api.app.state.settings, intelligence_enabled=True,
        intelligence_real_data_approved=True)
    assert req(insights_api, rw, funded, path).status_code == 403
    rw.execute("SELECT start_registration_trial(%s,%s)", (funded["user"], funded["ws"]))
    from app.api import intelligence
    started = rw.execute("SELECT started_at FROM workspace_trial(%s)",
                         (funded["ws"],)).fetchone()[0]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return started + timedelta(minutes=1)

    monkeypatch.setattr(intelligence, "datetime", Clock)
    response = req(insights_api, rw, funded, path)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["available"] is True
    assert report["chief"] == "chief_analyst"
    assert len(report["specialists"]) == 8
    assert {item["role"] for item in report["specialists"]} == set(ADDITIONAL_AGENTS)
    assert report["publication_allowed"] is False
    assert report["advertising_write_allowed"] is False
    assert report["external_llm"] is False
    assert report["independent_review_verified"] is False
    assert req(insights_api, rw, funded, path, actor=user(rw)).status_code == 404
    rw.execute("UPDATE direct_accounts SET is_selected=false WHERE id=%s",
               (funded["account"],))
    assert req(insights_api, rw, funded, path).json() == {
        "available": False, "reason": "no_snapshot"
    }


def test_chief_endpoint_rejects_changed_snapshot_between_reads(
        insights_api, rw, funded, monkeypatch):
    from app.api import intelligence
    insights_api.app.state.settings = replace(
        insights_api.app.state.settings, intelligence_enabled=True,
        intelligence_real_data_approved=True)
    rw.execute("SELECT start_registration_trial(%s,%s)", (funded["user"], funded["ws"]))
    started = rw.execute("SELECT started_at FROM workspace_trial(%s)",
                         (funded["ws"],)).fetchone()[0]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return started + timedelta(minutes=1)

    monkeypatch.setattr(intelligence, "datetime", Clock)
    original = intelligence.campaign_stats.build
    counter = 0

    def competing_snapshot(*args, **kwargs):
        nonlocal counter
        counter += 1
        value = original(*args, **kwargs)
        if counter == 2:
            value["provenance"] = []
        return value

    monkeypatch.setattr(intelligence.campaign_stats, "build", competing_snapshot)
    response = req(insights_api, rw, funded, "intelligence/chief-analyst?days=7")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "snapshot_changed"
