"""Паспорт рекомендации, решения человека и команда специалистов через HTTP: роли, версии, изоляция workspace."""

from test_api_support import ORIGIN, api, cookie, session, world  # noqa: F401 — фикстуры


def url(world, name="a1", rec="rec_a1"):
    return f"/api/v1/workspaces/ws_{world[name]}/recommendations/rec_{world[rec]['rec']}"


def decide(api, rw, world, who="owner", **body):
    body.setdefault("version_id", f"rv_{world['rec_a1']['finding']}")
    return api.post(url(world) + "/actions", json=body,
                    headers={**cookie(session(rw, world[who])), "Origin": ORIGIN})


def test_passport_of_new_recommendation(api, rw, world):
    r = api.get(url(world), headers=cookie(session(rw, world["owner"])))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version_id"] == f"rv_{world['rec_a1']['finding']}"
    assert body["allowed_actions"] == ["view", "postpone", "reject", "accept"] and body["blocked_actions"] == []
    assert body["decision"] is None and body["history"] == []
    assert body["explanation"] == {"text": "CPA выше цели", "source": "template"}


def test_accept_is_recorded_and_keeps_recommendation_active(api, rw, world):
    r = decide(api, rw, world, action="accept")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"]["event"] == "accepted" and "accept" not in body["allowed_actions"]
    assert body["execution"]["accepted_at"] is not None
    events = rw.execute("SELECT type, finding_id FROM recommendation_events WHERE recommendation_id = %s",
                        (world["rec_a1"]["rec"],)).fetchall()
    assert events == [("accepted", world["rec_a1"]["finding"])]
    today = api.get(f"/api/v1/workspaces/ws_{world['a1']}/today", headers=cookie(session(rw, world["owner"]))).json()
    assert today["counts"] == {"active": 1}  # принятие не означает выполнение и не убирает расход из оценки


def test_reject_requires_reason_and_stale_version_is_refused(api, rw, world):
    assert decide(api, rw, world, action="reject").status_code in (400, 422)
    r = decide(api, rw, world, action="accept", version_id="rv_999999999")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "stale_version")


def test_postpone_date_must_be_within_a_year(api, rw, world):
    assert decide(api, rw, world, action="postpone", until="2999-01-01").status_code == 400


def test_viewer_sees_passport_but_cannot_decide(api, rw, world):
    r = api.get(url(world), headers=cookie(session(rw, world["viewer"])))
    assert r.status_code == 200 and r.json()["allowed_actions"] == ["view"]
    assert [b["action"] for b in r.json()["blocked_actions"]] == ["accept", "postpone", "reject", "check"]
    r = decide(api, rw, world, who="viewer", action="accept")
    assert (r.status_code, r.json()["error"]["code"]) == (403, "forbidden_role")


def test_recommendation_of_other_workspace_is_not_found(api, rw, world):
    r = api.get(url(world, name="a1", rec="rec_a2"), headers=cookie(session(rw, world["owner"])))
    assert r.status_code == 404


def test_agents_reflect_latest_audit(api, rw, world):
    r = api.get(f"/api/v1/workspaces/ws_{world['a1']}/agents", headers=cookie(session(rw, world["owner"])))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "recommendations_only" and body["coordinator"]["status"] == "available"
    assert body["audit"]["rules"] == ["high_cpa_target@1"]
