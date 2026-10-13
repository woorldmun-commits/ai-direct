"""Перенесено из ветки онбординга поверх v2: личный workspace, профиль бизнеса, выход со всех устройств, выбор
кабинета Директа, команда специалистов /agents."""

import pytest

from app.api import create_app
from test_api_support import ORIGIN, client_for, cookie, session, settings, user, world, ws  # noqa: F401
from test_schema import one

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
    url = f"/api/v1/workspaces/{ws(world, 'a1')}/accounts/acc_{acc}"
    r = c.put(url, json={"is_selected": False}, headers=auth(session(rw, world["owner"])))
    assert r.status_code == 200 and r.json() == {"id": f"acc_{acc}", "is_selected": False}
    assert one(rw, "SELECT is_selected FROM direct_accounts WHERE id = %s", acc) is False


def test_account_of_another_workspace_is_404_and_viewer_403(c, rw, world):
    foreign = world_account(rw, world["b1"])
    owner = auth(session(rw, world["owner"]))
    assert c.put(f"/api/v1/workspaces/{ws(world, 'a1')}/accounts/acc_{foreign}", json={"is_selected": False},
                 headers=owner).status_code == 404
    own = world_account(rw, world["a1"])
    assert c.put(f"/api/v1/workspaces/{ws(world, 'a1')}/accounts/acc_{own}", json={"is_selected": False},
                 headers=auth(session(rw, world["viewer"]))).status_code == 403


def test_agents_lists_chief_and_specialists_read_only(c, rw, world):
    body = c.get(f"/api/v1/workspaces/{ws(world, 'a1')}/agents", headers=cookie(session(rw, world["owner"]))).json()
    assert body["mode"] == "recommendations_only" and body["coordinator"]["id"] == "chief_analyst"
    ids = {s["id"]: s for s in body["specialists"]}
    assert set(ids) == {"data_quality", "campaign_performance", "search_queries", "rsya_placements", "anomaly",
                        "budget"}
    assert ids["campaign_performance"]["status"] in ("issue_found", "no_material_issue", "insufficient_data",
                                                     "not_supported")


def world_account(rw, workspace: int) -> int:
    return one(rw, """SELECT da.id FROM direct_accounts da JOIN direct_connections dc ON dc.id = da.direct_connection_id
                      WHERE dc.workspace_id = %s ORDER BY da.id LIMIT 1""", workspace)
