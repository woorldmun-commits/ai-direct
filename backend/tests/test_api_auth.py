"""Real browser auth routes with PostgreSQL; only Yandex HTTP is replaced by a local transport."""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.api import create_app
from app.api import auth
from app.api.settings import Settings, SettingsError
from app.auth.login import SCOPES, OAuthError, fetch_user
from app.auth.yandex_oauth import OAuthApp, exchange_code
from app.legal.documents import text_sha256
from test_api_support import ORIGIN, api, client_for, settings  # noqa: F401
from test_login import FakeYandex, SIGN_UP, profile

PROVIDER = OAuthApp("login-client", "synthetic-provider-secret-32-characters",
                    ORIGIN + "/api/auth/yandex/callback", SCOPES)


@pytest.fixture
def browser(db, monkeypatch):
    approvals = {d: text_sha256(d, v) for d, v in SIGN_UP.items()}  # synthetic test approvals only
    app = create_app(settings(db, oauth_login=PROVIDER, signup_approved_hashes=approvals))
    fake = FakeYandex({"c1": profile()})
    original = httpx.Client
    monkeypatch.setattr(auth.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(fake), **kw))
    with client_for(app) as c:
        c.fake = fake
        yield c


def begin(c, accepted=SIGN_UP):
    r = c.post("/api/v1/auth/yandex/start", json={"accepted": accepted}, headers={"Origin": ORIGIN})
    assert r.status_code == 200
    return parse_qs(urlsplit(r.json()["authorize_url"]).query)["state"][0], r


def finish(c, state, code="c1"):
    return c.get("/api/v1/auth/yandex/callback", params={"state": state, "code": code}, follow_redirects=False)


def test_auth_unconfigured_is_503(api):
    r = api.post("/api/v1/auth/yandex/start", json={}, headers={"Origin": ORIGIN})
    assert r.status_code == 503 and r.json()["error"]["code"] == "auth_unavailable"
    assert "set-cookie" not in r.headers


def test_busy_callback_does_not_borrow_database_or_call_provider(browser, monkeypatch):
    state, _ = begin(browser)
    slots = browser.app.state.auth_callbacks
    assert slots.acquire(blocking=False)  # This fixture's pool has one connection.
    try:
        def forbidden_connection(*args, **kwargs):
            raise AssertionError("busy callback must not acquire a database connection")
        with monkeypatch.context() as patch:
            patch.setattr(browser.app.state.pool, "connection", forbidden_connection)
            r = finish(browser, state)
        assert r.status_code == 503 and r.json()["error"]["code"] == "auth_busy"
        assert r.headers["retry-after"] == "1"
        assert browser.fake.requests == [] and browser.cookies.get(auth.FLOW_COOKIE)
    finally:
        slots.release()
    assert finish(browser, state).headers["location"] == "/workspace"


@pytest.mark.parametrize("failure", [False, True])
def test_callback_releases_capacity_after_success_or_failure(browser, monkeypatch, failure):
    state, _ = begin(browser)
    if failure:
        def unavailable(*args, **kwargs):
            raise auth.LoginError("provider_unavailable")
        monkeypatch.setattr(auth, "sign_in", unavailable)
    r = finish(browser, state)
    assert r.headers["location"] == ("/login?error=auth_failed" if failure else "/workspace")
    slots = browser.app.state.auth_callbacks
    assert slots.acquire(blocking=False)
    slots.release()


def test_new_signup_needs_approved_exact_documents(db):
    with client_for(create_app(settings(db, oauth_login=PROVIDER))) as c:
        r = c.post("/api/v1/auth/yandex/start", json={"accepted": SIGN_UP}, headers={"Origin": ORIGIN})
    assert r.status_code == 503 and r.json()["error"]["code"] == "legal_unavailable"
    assert "set-cookie" not in r.headers


def test_start_blocks_csrf_and_unpublished_consent(browser):
    for origin in ("https://attacker.example", "null", ""):
        r = browser.post("/api/v1/auth/yandex/start", json={}, headers={"Origin": origin})
        assert r.status_code == 403
    r = browser.post("/api/v1/auth/yandex/start", json={"accepted": {"offer": "unpublished"}},
                     headers={"Origin": ORIGIN})
    assert r.status_code == 400 and browser.fake.requests == []


def test_signup_me_and_logout_revoke_the_actual_session(browser):
    state, r = begin(browser)
    flow = r.headers["set-cookie"]
    assert all(v in flow for v in ("HttpOnly", "Secure", "SameSite=lax", "Max-Age=600", "Path=/"))
    r = finish(browser, state)
    assert r.status_code == 303 and r.headers["location"] == "/workspace"
    assert "session=" in str(r.headers.get_list("set-cookie"))
    assert browser.get("/api/v1/me").status_code == 200
    me = browser.get("/api/v1/me").json()
    assert len(me["organizations"]) == 1
    workspace = me["organizations"][0]["workspaces"][0]
    assert workspace["name"] == "Мой кабинет"
    assert browser.get(f"/api/v1/workspaces/{workspace['id']}/today").status_code == 200
    token = browser.cookies.get("session")
    r = browser.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
    assert r.status_code == 200 and r.json() == {"status": "signed_out"}
    assert browser.get("/api/v1/me", headers={"Cookie": f"session={token}"}).status_code == 401


@pytest.mark.parametrize("mutation", ["missing", "tampered", "wrong_state", "expired", "missing_code", "provider_error"])
def test_invalid_flow_never_exchanges_the_code_or_acquires_database(browser, mutation, monkeypatch):
    state, _ = begin(browser)
    value = browser.cookies.get(auth.FLOW_COOKIE)
    browser.cookies.clear()
    if mutation == "tampered":
        browser.cookies.set(auth.FLOW_COOKIE, value[:-3] + "abc", domain="testserver.local", path="/")
    elif mutation == "expired":
        flow = auth._cipher(PROVIDER).decrypt(value.encode())
        browser.cookies.set(auth.FLOW_COOKIE, auth._cipher(PROVIDER).encrypt_at_time(flow, 1).decode(),
                            domain="testserver.local", path="/")
    elif mutation == "wrong_state":
        browser.cookies.set(auth.FLOW_COOKIE, value, domain="testserver.local", path="/")
        state = "other"
    elif mutation in ("missing_code", "provider_error"):
        browser.cookies.set(auth.FLOW_COOKIE, value, domain="testserver.local", path="/")

    def forbidden_connection(*args, **kwargs):
        raise AssertionError("invalid callback must not acquire a database connection")

    monkeypatch.setattr(browser.app.state.pool, "connection", forbidden_connection)
    r = browser.get("/api/v1/auth/yandex/callback", params={"state": state,
                    "code": "" if mutation == "missing_code" else "c1",
                    "error": "access_denied" if mutation == "provider_error" else ""}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=auth_failed"
    assert browser.fake.requests == [] and not browser.cookies.get(auth.FLOW_COOKIE)


def test_consent_is_rechecked_after_start(browser):
    state, _ = begin(browser)
    browser.app.state.settings.signup_approved_hashes.clear()
    r = finish(browser, state)
    assert r.headers["location"] == "/login?error=auth_failed" and browser.fake.requests == []


def test_existing_user_can_login_without_new_acceptance(browser):
    state, _ = begin(browser)
    assert finish(browser, state).headers["location"] == "/workspace"
    old_token = browser.cookies.get("session")
    browser.app.state.settings.signup_approved_hashes.clear()
    state, _ = begin(browser, accepted={})
    assert finish(browser, state).headers["location"] == "/workspace"
    assert browser.cookies.get("session") != old_token
    assert len(browser.get("/api/v1/me").json()["organizations"]) == 1
    assert browser.get("/api/v1/me", headers={"Cookie": f"session={old_token}"}).status_code == 401


def test_new_user_cannot_bypass_registration_consent(browser):
    state, _ = begin(browser, accepted={})
    assert finish(browser, state).headers["location"] == "/login?error=auth_failed"
    assert browser.get("/api/v1/me").status_code == 401


@pytest.mark.parametrize("body", [[], None, {"id": None, "login": "x"}, {"id": "", "login": "x"},
                                  {"id": "1", "login": {}}, {"id": "1", "login": "x", "default_email": []}])
def test_malformed_provider_identity_is_rejected(body):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))) as c:
        with pytest.raises(OAuthError, match="bad_response"):
            fetch_user(c, PROVIDER, "synthetic-token")


@pytest.mark.parametrize("uri", ["https://attacker.example/api/auth/yandex/callback",
                                  ORIGIN + "/other", ORIGIN + "/api/auth/yandex/callback?next=evil",
                                  "http://app.example.test/api/auth/yandex/callback"])
def test_provider_redirect_config_is_fail_closed(db, uri):
    with pytest.raises(SettingsError):
        settings(db, oauth_login=OAuthApp("id", "synthetic-secret", uri, SCOPES))


def test_oauth_config_is_opt_in_and_missing_config_stays_disabled():
    env = {"API_DATABASE_URL": "postgresql://app_rw@localhost/inrou", "API_ALLOWED_ORIGINS": ORIGIN,
           "YANDEX_LOGIN_CLIENT_ID": "id", "YANDEX_LOGIN_CLIENT_SECRET": "synthetic-secret",
           "YANDEX_LOGIN_REDIRECT_URI": PROVIDER.redirect_uri}
    assert Settings.from_env(env).oauth_login is None
    assert Settings.from_env({**env, "YANDEX_LOGIN_ENABLED": "1"}).oauth_login is not None
    del env["YANDEX_LOGIN_CLIENT_SECRET"]
    assert Settings.from_env({**env, "YANDEX_LOGIN_ENABLED": "1"}).oauth_login is None


@pytest.mark.parametrize("body", [[], {"access_token": "", "expires_in": 60},
                                  {"access_token": [], "expires_in": 60},
                                  {"access_token": "x", "expires_in": -1},
                                  {"access_token": "x", "expires_in": 10 ** 80},
                                  {"access_token": "x", "refresh_token": [], "expires_in": 60}])
def test_malformed_provider_token_is_rejected(body):
    from datetime import datetime, timezone

    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))) as c:
        with pytest.raises(OAuthError, match="bad_response"):
            exchange_code(c, PROVIDER, "synthetic-code", datetime.now(timezone.utc))


def test_exact_document_endpoint_and_approval(browser):
    import hashlib

    r = browser.get("/api/v1/legal/documents/offer", params={"version": SIGN_UP["offer"]})
    assert r.status_code == 200
    data = r.json()
    assert data["document"] == "offer" and data["version"] == SIGN_UP["offer"] and data["locale"] == "ru-RU"
    assert hashlib.sha256(data["text"].encode()).hexdigest() == data["sha256"] == text_sha256("offer", SIGN_UP["offer"])
    assert data["approved"] is True  # synthetic fixture, never deployed approval
    browser.app.state.settings.signup_approved_hashes.clear()
    assert browser.get(r.url).json()["approved"] is False
    assert browser.get("/api/v1/legal/documents/no_such_document", params={"version": "2026-10-01"}).status_code == 404
    assert browser.get("/api/v1/legal/documents/offer", params={"version": "../unknown"}).status_code == 404


def test_successful_callback_clears_flow_and_replay_has_no_provider_request(browser):
    state, _ = begin(browser)
    assert finish(browser, state).headers["location"] == "/workspace"
    assert not browser.cookies.get(auth.FLOW_COOKIE)
    before = len(browser.fake.requests)
    assert finish(browser, state).headers["location"] == "/login?error=auth_failed"
    assert len(browser.fake.requests) == before


def test_concurrent_first_login_provisions_one_workspace(browser):
    from concurrent.futures import ThreadPoolExecutor

    browser.fake.codes["c2"] = browser.fake.codes["c1"]
    with client_for(create_app(browser.app.state.settings)) as second:
        a, _ = begin(browser)
        b, _ = begin(second)
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(finish, browser, a, "c1")
            other = workers.submit(finish, second, b, "c2")
            assert first.result().headers["location"] == other.result().headers["location"] == "/workspace"
        left, right = browser.get("/api/v1/me").json(), second.get("/api/v1/me").json()
        assert left == right
        assert len(left["organizations"]) == len(left["organizations"][0]["workspaces"]) == 1


def test_callback_failure_rolls_back_identity_session_and_provisioning(browser, rw, monkeypatch):
    original = auth.sign_in

    def fail_after_signin(conn, *args, **kwargs):
        signed = original(conn, *args, **kwargs)
        org = conn.execute("SELECT create_organization(%s, 'rollback-test', 'business')",
                           (signed.user_id,)).fetchone()[0]
        conn.execute("SELECT create_workspace(%s, %s, 'rollback-test')", (signed.user_id, org))
        raise RuntimeError("synthetic provisioning failure")

    monkeypatch.setattr(auth, "sign_in", fail_after_signin)
    state, _ = begin(browser)
    assert finish(browser, state).status_code == 500
    uid = browser.fake.codes["c1"]["id"]
    assert rw.execute("SELECT count(*) FROM yandex_identities WHERE yandex_uid = %s", (uid,)).fetchone()[0] == 0
    assert rw.execute("SELECT count(*) FROM organizations WHERE name = 'rollback-test'").fetchone()[0] == 0
    assert browser.get("/api/v1/me").status_code == 401
