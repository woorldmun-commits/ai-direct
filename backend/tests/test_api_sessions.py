"""Вход через Яндекс ID по HTTP: state в httpOnly cookie, сверка до обращения к Яндексу, cookie сессии с флагами
Secure / HttpOnly / SameSite=Lax; выход; список и отзыв своих сессий. Без сети — httpx.MockTransport."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.api import create_app
from test_api_support import ORIGIN, client_for, cookie, session, settings, user, world, ws  # noqa: F401
from test_login import APP, FakeYandex, SIGN_UP, http, profile

pytestmark = pytest.mark.usefixtures("db")


def make(db, fake):
    return create_app(settings(db), login_app=APP, http=http(fake))


def authorize(c, **accepted):
    r = c.get("/api/v1/auth/yandex/authorize", params=accepted or SIGN_UP, follow_redirects=False)
    assert r.status_code == 302
    return r, parse_qs(urlparse(r.headers["location"]).query)["state"][0]


def flags(r, name) -> str:
    return next(h for h in r.headers.get_list("set-cookie") if h.startswith(name + "=")).lower()


def test_authorize_redirects_to_yandex_with_state_cookie(db):
    with client_for(make(db, FakeYandex())) as c:
        r, state = authorize(c)
    assert r.headers["location"].startswith("https://oauth.yandex.ru/authorize?")
    f = flags(r, "oauth_login")
    assert state.lower() in f and "httponly" in f and "secure" in f and "samesite=lax" in f and "path=/api/v1/auth" in f


def test_unknown_document_version_is_400(db):
    with client_for(make(db, FakeYandex())) as c:
        r = c.get("/api/v1/auth/yandex/authorize", params={"offer": "1999-01-01"}, follow_redirects=False)
        assert r.status_code == 400
        r = c.get("/api/v1/auth/yandex/authorize", params={"evil": "1"}, follow_redirects=False)
        assert r.status_code == 400


def test_full_login_sets_session_cookie_and_me_works(db):
    p = profile()
    with client_for(make(db, FakeYandex({"c1": p}))) as c:
        _, state = authorize(c)
        r = c.get("/api/v1/auth/yandex/callback", params={"code": "c1", "state": state, "cid": "x"},
                  follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
        f = flags(r, "session")
        assert "httponly" in f and "secure" in f and "samesite=lax" in f and "max-age=" in f
        assert c.get("/api/v1/me").json()["user"]["email"] == p["default_email"]


@pytest.mark.parametrize("with_cookie", [True, False])
def test_state_mismatch_never_reaches_yandex(db, with_cookie):
    fake = FakeYandex({"c1": profile()})
    with client_for(make(db, fake)) as c:
        if with_cookie:
            authorize(c)
        r = c.get("/api/v1/auth/yandex/callback", params={"code": "c1", "state": "forged"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?error=state_mismatch"
    assert fake.requests == [] and "session=" not in r.headers.get("set-cookie", "").replace("oauth_login", "")


def test_denied_on_yandex_page(db):
    with client_for(make(db, FakeYandex())) as c:
        _, state = authorize(c)
        r = c.get("/api/v1/auth/yandex/callback", params={"error": "access_denied", "state": state},
                  follow_redirects=False)
    assert r.headers["location"] == "/login?error=access_denied"


def test_sessions_list_revoke_and_logout(db, rw):
    uid, other = user(rw), user(rw)
    mine, second, foreign = session(rw, uid), session(rw, uid), session(rw, other)
    with client_for(create_app(settings(db))) as c:
        items = c.get("/api/v1/auth/sessions", headers=cookie(mine)).json()["items"]
        assert len(items) == 2 and sum(i["current"] for i in items) == 1
        assert all(set(i) == {"id", "created_at", "expires_at", "current"} for i in items)
        foreign_id = c.get("/api/v1/auth/sessions", headers=cookie(foreign)).json()["items"][0]["id"]
        h = {**cookie(mine), "Origin": ORIGIN}
        assert c.delete(f"/api/v1/auth/sessions/{foreign_id}", headers=h).status_code == 404
        assert c.delete("/api/v1/auth/sessions/ses_zz", headers=h).status_code == 404
        other_id = next(i["id"] for i in items if not i["current"])
        assert c.delete(f"/api/v1/auth/sessions/{other_id}", headers=h).status_code == 204
        assert c.get("/api/v1/me", headers=cookie(second)).status_code == 401
        assert c.get("/api/v1/me", headers=cookie(foreign)).status_code == 200
        assert c.post("/api/v1/auth/logout", headers=cookie(mine)).status_code == 403  # без Origin — CSRF
        r = c.post("/api/v1/auth/logout", headers=h)
        assert r.status_code == 204 and "session=" in r.headers["set-cookie"]
        assert c.get("/api/v1/me", headers=cookie(mine)).status_code == 401
        assert c.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 204
