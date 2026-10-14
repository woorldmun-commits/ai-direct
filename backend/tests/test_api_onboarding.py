"""Перенесено из ветки онбординга поверх v2: личный workspace, профиль бизнеса, выход со всех устройств, выбор
кабинета Директа (PATCH …/integrations/ad-accounts/{id}, API_CONTRACT §8), команда специалистов /agents."""

import pytest

from app.api import create_app
from test_api_support import ORIGIN, client_for, cookie, session, settings, user, world, ws  # noqa: F401
from test_schema import connected, one

pytestmark = pytest.mark.usefixtures("db")
PROFILE = {"industry": "services", "business_model": "leads", "site_url": "https://shop.example.test",
           "region": "Москва", "goals": ["Заявки"], "budget": "100000.00", "target_cpa": "2500.00",
           "currency": "RUB", "constraints": []}


@pytest.fixture
def c(db):
    with client_for(create_app(settings(db))) as client:
        yield client


def auth(token: str) -> dict:
    """Изменяющие запросы проходят CSRF-проверку Origin (BoundaryMiddleware)."""
    return {**cookie(token), "Origin": ORIGIN}


def test_personal_workspace_is_created_once(c, rw):
    token = session(rw, user(rw))
    first = c.post("/api/v1/workspaces", json={"name": "Мой бизнес"}, headers=auth(token))
    again = c.post("/api/v1/workspaces", json={"name": "Другое имя"}, headers=auth(token))
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"] and again.json()["name"] == "Мой бизнес"


def test_business_profile_round_trip_and_target_cpa(c, rw, world):
    h = auth(session(rw, world["owner"]))
    url = f"/api/v1/workspaces/{ws(world, 'a1')}/business-profile"
    assert c.put(url, json=PROFILE, headers=h).status_code == 200
    assert c.get(url, headers=h).json()["target_cpa"] == "2500.00"
    assert str(one(rw, "SELECT target_cpa FROM workspace_settings WHERE workspace_id = %s", world["a1"])) == "2500.00"


@pytest.mark.parametrize("bad", [{"site_url": "javascript:alert(1)"}, {"budget": 100}, {"evil": 1}])
def test_business_profile_rejects_bad_input(c, rw, world, bad):
    h = auth(session(rw, world["owner"]))
    r = c.put(f"/api/v1/workspaces/{ws(world, 'a1')}/business-profile", json={**PROFILE, **bad}, headers=h)
    assert r.status_code in (400, 422)


def test_viewer_cannot_change_profile_and_other_org_is_404(c, rw, world):
    url = f"/api/v1/workspaces/{ws(world, 'a1')}/business-profile"
    assert c.put(url, json=PROFILE, headers=auth(session(rw, world["viewer"]))).status_code == 403
    assert c.get(url, headers=cookie(session(rw, world["owner_b"]))).status_code == 404


def test_logout_all_ends_every_own_session_only(c, rw):
    uid, other = user(rw), user(rw)
    mine, second, foreign = session(rw, uid), session(rw, uid), session(rw, other)
    assert c.post("/api/v1/auth/logout-all", headers=auth(mine)).status_code == 204
    assert c.get("/api/v1/me", headers=cookie(second)).status_code == 401
    assert c.get("/api/v1/me", headers=cookie(foreign)).status_code == 200


def test_select_direct_account(c, rw, world):
    acc = world_account(rw, world["a1"])
    url = f"/api/v1/workspaces/{ws(world, 'a1')}/integrations/ad-accounts/acc_{acc}"
    r = c.patch(url, json={"selected": False}, headers=auth(session(rw, world["owner"])))
    assert r.status_code == 200 and r.json() == {"id": f"acc_{acc}", "selected": False}
    assert one(rw, "SELECT is_selected FROM direct_accounts WHERE id = %s", acc) is False


def test_account_of_another_workspace_is_404_and_viewer_403(c, rw, world):
    foreign = world_account(rw, world["b1"])
    owner = auth(session(rw, world["owner"]))
    assert c.patch(f"/api/v1/workspaces/{ws(world, 'a1')}/integrations/ad-accounts/acc_{foreign}", json={"selected": False},
                 headers=owner).status_code == 404
    own = world_account(rw, world["a1"])
    assert c.patch(f"/api/v1/workspaces/{ws(world, 'a1')}/integrations/ad-accounts/acc_{own}", json={"selected": False},
                 headers=auth(session(rw, world["viewer"]))).status_code == 403


def test_agents_lists_chief_and_specialists_read_only(c, rw, world):
    body = c.get(f"/api/v1/workspaces/{ws(world, 'a1')}/agents", headers=cookie(session(rw, world["owner"]))).json()
    assert body["mode"] == "recommendations_only" and body["coordinator"]["id"] == "chief_analyst"
    ids = {s["id"]: s for s in body["specialists"]}
    assert set(ids) == {"data_quality", "campaign_performance", "search_queries", "rsya_placements", "anomaly",
                        "budget", "goals_attribution", "root_cause"}
    assert ids["campaign_performance"]["status"] in ("issue_found", "no_material_issue", "insufficient_data",
                                                     "not_supported")


def world_account(rw, workspace: int) -> int:
    return one(rw, """SELECT da.id FROM direct_accounts da JOIN direct_connections dc ON dc.id = da.direct_connection_id
                      WHERE dc.workspace_id = %s ORDER BY da.id LIMIT 1""", workspace)


def test_agents_goals_attribution_reads_metrika_state(c, rw, world):
    url, h = f"/api/v1/workspaces/{ws(world, 'a1')}/agents", cookie(session(rw, world["owner"]))
    goals = {s["id"]: s for s in c.get(url, headers=h).json()["specialists"]}["goals_attribution"]
    assert (goals["status"], goals["missing_data"]) == ("insufficient_data", ["metrika_missing"])
    conn_id = connected(rw, "metrika", world["a1"], f"metrika-agents-{world['a1']}")
    rw.execute("INSERT INTO metrika_counters (metrika_connection_id, counter_id) VALUES (%s, 555)", (conn_id,))
    goals = {s["id"]: s for s in c.get(url, headers=h).json()["specialists"]}["goals_attribution"]
    assert (goals["status"], goals["missing_data"]) == ("issue_found", ["conversion_definition_missing"])
    rw.execute("UPDATE metrika_counters SET is_selected = true, goal_ids = '{7}' WHERE counter_id = 555")
    goals = {s["id"]: s for s in c.get(url, headers=h).json()["specialists"]}["goals_attribution"]
    assert goals["status"] == "no_material_issue"


def test_agents_root_cause_without_campaign_stats_is_not_supported(c, rw, world):
    body = c.get(f"/api/v1/workspaces/{ws(world, 'a1')}/agents", headers=cookie(session(rw, world["owner"]))).json()
    assert {s["id"]: s for s in body["specialists"]}["root_cause"]["status"] == "not_supported"


def test_profile_without_target_cpa_keeps_settings(c, rw, world):
    """target_cpa не прислан — настройка аудита не стирается в NULL; прислан null — сбрасывается явно."""
    h = auth(session(rw, world["owner"]))
    url = f"/api/v1/workspaces/{ws(world, 'a1')}/business-profile"
    assert c.put(url, json=PROFILE, headers=h).status_code == 200
    without = {k: v for k, v in PROFILE.items() if k != "target_cpa"}
    assert c.put(url, json=without, headers=h).status_code == 200
    assert str(one(rw, "SELECT target_cpa FROM workspace_settings WHERE workspace_id = %s", world["a1"])) == "2500.00"
    assert c.put(url, json={**PROFILE, "target_cpa": None}, headers=h).status_code == 200
    assert one(rw, "SELECT target_cpa FROM workspace_settings WHERE workspace_id = %s", world["a1"]) is None


def test_personal_workspace_after_deletion_starts_again(c, rw):
    """Личный workspace в удалении не возвращает 410 навсегда: пользователь начинает с нового."""
    token = session(rw, user(rw))
    first = c.post("/api/v1/workspaces", json={"name": "Старый"}, headers=auth(token)).json()["id"]
    rw.execute("UPDATE workspaces SET status = 'deletion_pending', deactivated_at = now() WHERE id = %s",
               (int(first.removeprefix("ws_")),))
    again = c.post("/api/v1/workspaces", json={"name": "Новый"}, headers=auth(token))
    assert again.status_code == 201
    assert again.json()["id"] != first and again.json()["name"] == "Новый"
