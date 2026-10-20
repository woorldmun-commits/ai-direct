"""Подключения Директа и Метрики по HTTP (API_CONTRACT §8): state в cookie и сверка до Яндекса, привязка к
workspace и пользователю, owner/admin, мандат агентства, токен — через set_connection_token после enter_workspace,
отключение, изоляция workspace. Без сети — httpx.MockTransport."""

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.api import create_app
from app.auth.tokens import ConnectionRef, EnvKeys, load
from app.auth.yandex_oauth import OAuthApp
from test_api_support import ORIGIN, client_for, session, settings, world, ws  # noqa: F401

API = OAuthApp("api-client", "api-secret", "https://app.test/api/v1/integrations/cb", ("direct:api", "metrika:read"))
KEYS = EnvKeys({"TOKEN_ENCRYPTION_KEY_VERSION": "1", "TOKEN_ENCRYPTION_KEY_1": base64.b64encode(b"k" * 32).decode()})
H = {"Origin": ORIGIN}


class FakeYandex:
    def __init__(self, login="direct-login"):
        self.login, self.requests = login, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        if request.url.path == "/token":
            if parse_qs(request.content.decode())["code"][0] != "good":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "acc-1", "refresh_token": "ref-1", "expires_in": 3600})
        if request.url.path == "/info":
            return httpx.Response(200, json={"id": "1", "login": self.login, "client_id": API.client_id})
        if request.url.path == "/management/v1/counters":
            return httpx.Response(200, text=json.dumps({"counters": [{"id": 777, "name": "site"}]}))
        return httpx.Response(404)


@pytest.fixture
def fake():
    return FakeYandex()


@pytest.fixture
def c(db, fake):
    app = create_app(settings(db), api_app=API, http=httpx.Client(transport=httpx.MockTransport(fake)),
                     token_keys=KEYS)
    with client_for(app) as client:
        yield client


def as_user(c, rw, uid):
    c.cookies.set("session", session(rw, uid))


def connect(c, ids, name, provider="yandex_direct"):
    return c.post(f"/api/v1/workspaces/{ws(ids, name)}/integrations/{provider}/connect", headers=H)


def finish(c, r, provider="yandex_direct", code="good", state=None):
    state = state or parse_qs(urlparse(r.json()["redirect_url"]).query)["state"][0]
    return c.get(f"/api/v1/integrations/{provider}/callback", params={"code": code, "state": state},
                 follow_redirects=False)


def test_connect_returns_yandex_url_and_bound_cookie(c, rw, world):
    as_user(c, rw, world["owner_b"])
    r = connect(c, world, "b1")
    assert r.status_code == 200
    q = parse_qs(urlparse(r.json()["redirect_url"]).query)
    assert q["client_id"] == ["api-client"] and q["scope"] == ["direct:api metrika:read"]
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("oauth_connect=")).lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert f".{world['b1']}.yandex_direct.{world['owner_b']}" in cookie


@pytest.mark.parametrize("who, target, status", [("viewer", "a1", 403), ("owner", "b1", 404), ("owner_b", "a1", 404),
                                                 ("member", "a1", 404)])
def test_connect_rights_and_isolation(c, rw, world, who, target, status):
    as_user(c, rw, world[who])
    assert connect(c, world, target).status_code == status


def test_unknown_provider_is_404(c, rw, world):
    as_user(c, rw, world["owner_b"])
    assert connect(c, world, "b1", "vk_ads").status_code == 404


def test_agency_needs_mandate_before_direct(c, rw, world, fake):
    as_user(c, rw, world["admin"])
    r = connect(c, world, "a2")
    assert r.status_code == 422 and r.json()["error"] == {**r.json()["error"], "code": "acceptance_required",
                                                          "reason": "agency_client_mandate"}
    assert connect(c, world, "a2", "yandex_metrika").status_code == 200  # Метрике мандат не нужен
    bad = c.post(f"/api/v1/workspaces/{ws(world, 'a2')}/legal/agency-client-mandate", json={"version": "1999-01-01"},
                 headers=H)
    assert bad.status_code == 400
    ok = c.post(f"/api/v1/workspaces/{ws(world, 'a2')}/legal/agency-client-mandate", json={"version": "2026-10-01"},
                headers=H)
    assert ok.status_code == 204
    r = connect(c, world, "a2")
    assert r.status_code == 200
    assert finish(c, r).headers["location"] == "/settings/integrations?connected=yandex_direct"


def test_mandate_only_for_agency(c, rw, world):
    as_user(c, rw, world["owner_b"])
    r = c.post(f"/api/v1/workspaces/{ws(world, 'b1')}/legal/agency-client-mandate", json={"version": "2026-10-01"},
               headers=H)
    assert r.status_code == 422 and r.json()["error"]["reason"] == "not_agency"


def test_direct_callback_stores_encrypted_token(c, db, rw, world):
    as_user(c, rw, world["owner_b"])
    r = finish(c, connect(c, world, "b1"))
    assert r.status_code == 303 and r.headers["location"] == "/settings/integrations?connected=yandex_direct"
    cid, status, scopes = rw.execute("""SELECT id, status, scopes FROM direct_connections
                                        WHERE workspace_id = %s AND yandex_login = 'direct-login'""",
                                     (world["b1"],)).fetchone()
    assert status == "connected" and scopes == ["direct:api"]
    with db("app_token") as token_conn:
        stored = load(token_conn, KEYS, ConnectionRef("direct", world["b1"], cid))
    assert (stored.access_token, stored.refresh_token) == ("acc-1", "ref-1")
    items = c.get(f"/api/v1/workspaces/{ws(world, 'b1')}/integrations").json()["items"]
    mine = next(i for i in items if i["account"] == "direct-login")
    assert mine["status"] == "connected" and mine["ad_accounts"][0]["selected"] is False
    assert "token" not in json.dumps(items).replace("token_", "")


def test_metrika_callback_saves_counters_and_lists_goals(c, rw, world):
    as_user(c, rw, world["owner_b"])
    assert finish(c, connect(c, world, "b1", "yandex_metrika"), "yandex_metrika").status_code == 303
    goals = c.get(f"/api/v1/workspaces/{ws(world, 'b1')}/integrations/yandex_metrika/goals").json()
    assert goals == {"items": [{"counter_id": "777", "selected": False, "goal_ids": []}], "candidates": None}


def test_state_mismatch_does_not_reach_yandex(c, rw, world, fake):
    as_user(c, rw, world["owner_b"])
    connect(c, world, "b1")
    r = finish(c, None, state="forged")
    assert r.headers["location"] == "/settings/integrations?error=state_mismatch" and fake.requests == []


def test_callback_by_another_user_saves_nothing(c, rw, world):
    as_user(c, rw, world["owner"])
    r = connect(c, world, "a1", "yandex_metrika")
    as_user(c, rw, world["admin"])  # тот же браузер, но вошёл другой пользователь
    assert finish(c, r, "yandex_metrika").headers["location"] == "/settings/integrations?error=state_mismatch"
    assert rw.execute("SELECT count(*) FROM metrika_connections WHERE workspace_id = %s",
                      (world["a1"],)).fetchone()[0] == 0


def test_tampered_cookie_workspace_is_refused(c, rw, world):
    as_user(c, rw, world["owner"])
    r = connect(c, world, "a1", "yandex_metrika")
    state = parse_qs(urlparse(r.json()["redirect_url"]).query)["state"][0]
    token = c.cookies.get("session")
    c.cookies.clear()
    c.cookies.set("session", token)
    c.cookies.set("oauth_connect", f"{state}.{world['b1']}.yandex_metrika.{world['owner']}")
    out = finish(c, None, "yandex_metrika", state=state)
    assert out.headers["location"] == "/settings/integrations?error=not_found"
    assert rw.execute("SELECT count(*) FROM metrika_connections WHERE workspace_id = %s",
                      (world["b1"],)).fetchone()[0] == 0


def test_bad_code_redirects_with_error(c, rw, world):
    as_user(c, rw, world["owner_b"])
    out = finish(c, connect(c, world, "b1"), code="bad")
    assert out.headers["location"] == "/settings/integrations?error=invalid_grant"


def test_disconnect_drops_token(c, rw, world):
    as_user(c, rw, world["owner_b"])
    finish(c, connect(c, world, "b1"))
    as_user(c, rw, world["owner"])
    assert c.post(f"/api/v1/workspaces/{ws(world, 'b1')}/integrations/yandex_direct/disconnect",
                  headers=H).status_code == 404
    as_user(c, rw, world["owner_b"])
    assert c.post(f"/api/v1/workspaces/{ws(world, 'b1')}/integrations/yandex_direct/disconnect",
                  headers=H).status_code == 204
    rows = rw.execute("SELECT status, has_token FROM direct_connections WHERE workspace_id = %s",
                      (world["b1"],)).fetchall()
    assert rows and all(r == ("disconnected", False) for r in rows)
