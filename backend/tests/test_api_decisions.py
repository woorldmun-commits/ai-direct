"""Паспорт рекомендации и решения человека по HTTP (API_CONTRACT §4–6): права по роли (viewer не решает), порядок
проверок, причины отклонения, идемпотентность повтора, version_outdated, outbox в той же транзакции, изоляция."""

from datetime import timedelta

import pytest

from app.api.active import today_msk
from test_api_support import ORIGIN, api, cookie, recommendation, session, world, ws  # noqa: F401

H = {"Origin": ORIGIN}


def url(ids, name, rec):
    return f"/api/v1/workspaces/{ws(ids, name)}/recommendations/rec_{rec['rec']}"


def post(api, token, ids, name, rec, **body):
    body.setdefault("version_id", f"rv_{rec['finding']}")
    return api.post(url(ids, name, rec) + "/actions", json=body, headers={**cookie(token), **H})


def events(rw, rec):
    return rw.execute("SELECT type FROM recommendation_events WHERE recommendation_id = %s ORDER BY id",
                      (rec["rec"],)).fetchall()


def tomorrow(days=1):
    return (today_msk() + timedelta(days=days)).isoformat()


def test_passport(api, rw, world):
    rec = world["rec_a1"]
    r = api.get(url(world, "a1", rec), headers=cookie(session(rw, world["owner"])))
    assert r.status_code == 200
    p = r.json()
    assert p["id"] == f"rec_{rec['rec']}" and p["version_id"] == f"rv_{rec['finding']}" and p["status"] == "new"
    assert p["allowed_actions"] == ["mark_done_manually", "postpone", "reject"] and p["blocked_actions"] == []
    assert p["exposure"]["amount"] == "12500.00" and p["exposure_overlap"]["unit"] == "rub"
    assert p["evidence"]["facts"]["clicks"]["amount"] == "487" and "snapshot_id" not in str(p)
    assert p["explanation"] == {"text": "CPA выше цели", "source": "template"}
    assert p["history"][0]["event"] == "created" and p["decision"] is None
    assert p["action"]["type"] == "lower_cpa" and p["candidate_action"]["type"] == "decrease_bid"


@pytest.mark.parametrize("who, name, rec", [("owner_b", "a1", "rec_a1"), ("owner", "a1", "rec_a2"),
                                            ("member", "a1", "rec_a1"), ("viewer", "a2", "rec_a2")])
def test_foreign_recommendation_is_404(api, rw, world, who, name, rec):
    token = session(rw, world[who])
    assert api.get(url(world, name, world[rec]), headers=cookie(token)).status_code == 404
    assert post(api, token, world, name, world[rec], action="postpone", until=tomorrow()).status_code == 404
    assert events(rw, world[rec]) == []


@pytest.mark.parametrize("bad", ["1", "rec_", "rec_0", "rec_abc", "rec_99999999999999999999"])
def test_malformed_id_is_404(api, rw, world, bad):
    r = api.get(f"/api/v1/workspaces/{ws(world, 'a1')}/recommendations/{bad}",
                headers=cookie(session(rw, world["owner"])))
    assert r.status_code == 404


def test_viewer_sees_but_cannot_decide(api, rw, world):
    token = session(rw, world["viewer"])
    p = api.get(url(world, "a1", world["rec_a1"]), headers=cookie(token)).json()
    assert p["allowed_actions"] == [] and {b["reason"] for b in p["blocked_actions"]} == {"role_forbidden"}
    r = post(api, token, world, "a1", world["rec_a1"], action="reject", reason="too_risky")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    assert post(api, token, world, "a1", world["rec_a1"], action="view").status_code == 200
    assert events(rw, world["rec_a1"]) == []


@pytest.mark.parametrize("body", [
    {"action": "reject"}, {"action": "reject", "reason": "bad_reason"}, {"action": "reject", "reason": "other"},
    {"action": "reject", "reason": "other", "comment": "  "}, {"action": "postpone"},
    {"action": "postpone", "until": "2026-01-01", "reason": "too_risky"}, {"action": "check", "comment": "x"},
    {"action": "reject", "reason": "too_risky", "comment": "x" * 501}, {"action": "approve"},
    {"action": "check", "extra": 1}, {"action": "check", "version_id": "77"}])
def test_bad_format_is_400(api, rw, world, body):
    r = post(api, session(rw, world["admin"]), world, "a1", world["rec_a1"], **body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("days", [0, 91, -1])
def test_postpone_range(api, rw, world, days):
    r = post(api, session(rw, world["admin"]), world, "a1", world["rec_a1"], action="postpone", until=tomorrow(days))
    assert r.status_code == 400


def test_reject_is_idempotent_and_final(api, rw, world):
    token, rec = session(rw, world["admin"]), world["rec_a1"]
    r = post(api, token, world, "a1", rec, action="reject", reason="other", comment="Кампания сезонная")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["decision"] | {} == {**r.json()["decision"], "event": "rejected", "reason": "other",
                                       "comment": "Кампания сезонная"}
    assert post(api, token, world, "a1", rec, action="reject", reason="too_risky").status_code == 200
    assert events(rw, rec) == [("rejected",)]
    r = post(api, token, world, "a1", rec, action="postpone", until=tomorrow())
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    outbox = rw.execute("""SELECT event_type, payload FROM outbox_events WHERE aggregate_type = 'recommendation'
                           AND aggregate_id = %s""", (rec["rec"],)).fetchall()
    assert outbox == [("recommendation_rejected", {"finding_id": rec["finding"]})]


def test_version_outdated_returns_current(api, rw, world):
    r = post(api, session(rw, world["owner"]), world, "a1", world["rec_a1"], action="reject", reason="too_risky",
             version_id="rv_1")
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_outdated"
    assert r.json()["recommendation"]["version_id"] == f"rv_{world['rec_a1']['finding']}"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]


def test_postpone_then_mark_done(api, rw, world):
    token, rec, until = session(rw, world["owner"]), world["rec_a1"], tomorrow(3)
    r = post(api, token, world, "a1", rec, action="postpone", until=until)
    assert r.json()["status"] == "postponed" and r.json()["postponed_until"] == until
    assert post(api, token, world, "a1", rec, action="postpone", until=until).status_code == 200  # повтор
    assert post(api, token, world, "a1", rec, action="postpone", until=tomorrow(4)).status_code == 200  # перенос
    r = post(api, token, world, "a1", rec, action="mark_done_manually")
    assert r.status_code == 200 and r.json()["status"] == "applied"
    assert r.json()["execution"]["execution_mode"] == "manual" and r.json()["execution"]["verification_status"] \
        == "pending"
    assert events(rw, rec) == [("postponed",), ("postponed",), ("done",)]
    assert rw.execute("SELECT count(*) FROM measurements WHERE recommendation_id = %s",
                      (rec["rec"],)).fetchone()[0] == 1
    assert post(api, token, world, "a1", rec, action="mark_done_manually").status_code == 200
    assert len(events(rw, rec)) == 3
    hist = [h["event"] for h in api.get(url(world, "a1", rec), headers=cookie(token)).json()["history"]]
    assert hist == ["created", "postponed", "postponed", "manual_claimed"]


@pytest.mark.parametrize("action", ["check", "accept"])
def test_unavailable_actions_are_422(api, rw, world, action):
    r = post(api, session(rw, world["owner"]), world, "a1", world["rec_a1"], action=action)
    assert r.status_code == 422 and r.json()["error"]["code"] == "action_unavailable"


def test_inspect_only_is_checked_not_done(api, rw, world):
    rec = recommendation(rw, world["a1"], "client-inspect", "100.00", level="inspect_only",
                         action={"type": "investigate_cpa_growth"})
    token = session(rw, world["admin"])
    p = api.get(url(world, "a1", rec), headers=cookie(token)).json()
    assert p["allowed_actions"] == ["check", "postpone"]
    assert post(api, token, world, "a1", rec, action="mark_done_manually").status_code == 422
    assert post(api, token, world, "a1", rec, action="reject", reason="too_risky").status_code == 422
    r = post(api, token, world, "a1", rec, action="check")
    assert r.status_code == 200 and r.json()["execution"] | {} == {**r.json()["execution"], "execution_mode": "none",
                                                                   "verification_status": "not_required"}
