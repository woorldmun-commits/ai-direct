"""Live HTTP foundation against PostgreSQL; all external transports are injected fakes."""

from datetime import datetime, timezone
import itertools
import re
import threading

import httpx
import psycopg
import pytest

from app.api import create_app
from app.api.auth_routes import router as auth_router
from app.api.integration_routes import router as integration_router
from app.api.onboarding_routes import router as onboarding_router
from app.auth.phone import PhoneAuthConfig
from app.auth.phone_login import sign_in_phone
from app.auth.providers import PhoneServices
from app.auth.yandex_oauth import OAuthApp
from test_api_support import ORIGIN, client_for, cookie, recommendation, session, settings, user

numbers = itertools.count(2000000)
ACCEPTED = {"offer": "2026-10-01", "pd_consent": "2026-10-01"}


class Sms:
    def __init__(self):
        self.sent = []

    def send(self, phone, text):
        self.sent.append((phone, text))

    def code(self):
        return re.search(r"\d{6}", self.sent[-1][1]).group()


class Captcha:
    def verify(self, token, ip):
        return token == "verified"


class Keys:
    def current_version(self):
        return 1

    def key(self, version):
        return b"x" * 32


class Integrations:
    app = OAuthApp(
        "client",
        "secret",
        "https://app.example.test/api/v1/integrations/yandex_direct/callback",
        ("direct:api", "metrika:read"),
    )
    keys = Keys()

    def __init__(self):
        self.exchanges = []
        self.http = httpx.Client(transport=httpx.MockTransport(self.reply))

    def reply(self, request):
        self.exchanges.append(request)
        return httpx.Response(
            200, json={"access_token": "provider-secret", "refresh_token": "refresh-secret", "expires_in": 3600}
        )

    def discover(self, provider, token):
        assert token == "provider-secret"
        if provider == "yandex_direct":
            return {"login": "real-business", "accounts": [{"client_login": None}]}
        return {
            "login": "real-business",
            "counters": [{"id": 101, "name": "Business", "site": None, "goals": [{"id": 501, "name": "Paid order"}]}],
        }


@pytest.fixture
def live(db):
    app = create_app(settings(db, pool_timeout=10.0))
    for router in (auth_router, integration_router, onboarding_router):
        app.include_router(router, prefix="/api/v1")
    sms = Sms()
    app.state.phone_services = PhoneServices(
        PhoneAuthConfig(True, b"k" * 32, daily_cap=10000), sms, Captcha(), b"i" * 32
    )
    app.state.integration_services = Integrations()
    with client_for(app) as client:
        yield client, app, sms
    app.state.integration_services.http.close()


def ask(live):
    client, _, sms = live
    number = f"+7912{next(numbers):07d}"
    response = client.post(
        "/api/v1/auth/code/request", json={"phone": number, "captcha_token": "verified"}, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 202, response.text
    assert response.json() == {"status": "code_requested"}
    assert number not in response.text
    return number, sms.code()


def verify(live, number, code, accepted=None):
    return live[0].post(
        "/api/v1/auth/code/verify",
        headers={"Origin": ORIGIN},
        json={"phone": number, "code": code, "accepted": ACCEPTED if accepted is None else accepted},
    )


def test_sms_session_onboarding_profile_and_logout(live):
    number, code = ask(live)
    client, _, _ = live
    response = verify(live, number, code)
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] is None
    assert number not in response.text and code not in response.text
    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header and "Secure" in cookie_header and "SameSite=lax" in cookie_header
    me = client.get("/api/v1/me")
    assert me.status_code == 200 and me.json()["user"]["phone"].endswith(number[-2:])
    assert me.json()["workspaces"] == []
    created = client.post("/api/v1/workspaces", headers={"Origin": ORIGIN}, json={"name": "Business"})
    assert created.status_code == 201, created.text
    ws = created.json()["id"]
    repeated = client.post("/api/v1/workspaces", headers={"Origin": ORIGIN}, json={"name": "Another"})
    assert repeated.json()["id"] == ws
    path = f"/api/v1/workspaces/{ws}/business-profile"
    payload = {"industry": "services", "budget": "1000.50", "target_cpa": "200.00", "goals": ["Sales"]}
    saved = client.put(path, headers={"Origin": ORIGIN}, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["budget"] == "1000.50" and client.get(path).json() == saved.json()
    assert client.put(path, headers={"Origin": ORIGIN}, json={"budget": "NaN"}).status_code == 400
    assert client.put(path, headers={"Origin": ORIGIN}, json={"budget": "1.001"}).status_code == 400
    assert verify(live, number, code).status_code == 401
    assert client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_consent_does_not_consume_code_and_boolean_versions_rejected(live):
    number, code = ask(live)
    response = verify(live, number, code, {})
    assert response.status_code == 422 and response.json()["error"]["code"] == "acceptance_required"
    assert verify(live, number, code, {"offer": True}).status_code == 400
    assert verify(live, number, code).status_code == 200


def test_invalid_attempts_persist_and_limits_have_retry_header(live):
    number, code = ask(live)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert verify(live, number, wrong).status_code == 401
    assert verify(live, number, code).status_code == 401
    request = live[0].post("/api/v1/auth/code/request", headers={"Origin": ORIGIN}, json={"phone": number})
    assert request.status_code == 429 and int(request.headers["retry-after"]) > 0


def test_no_production_fake_when_not_configured(db, monkeypatch):
    monkeypatch.delenv("PHONE_AUTH_ENABLED", raising=False)
    app = create_app(settings(db))
    app.include_router(auth_router, prefix="/api/v1")
    with client_for(app) as client:
        result = client.post("/api/v1/auth/code/request", headers={"Origin": ORIGIN}, json={"phone": "+79123456789"})
        assert result.status_code == 503 and result.json()["error"]["code"] == "provider_not_configured"


def test_registration_failure_rolls_back_consumption(live, db, monkeypatch):
    import app.auth.phone_login as login

    number, code = ask(live)
    original = login.record_acceptance

    def fail(*args, **kwargs):
        raise RuntimeError("database failure")

    monkeypatch.setattr(login, "record_acceptance", fail)
    assert verify(live, number, code).status_code == 500
    monkeypatch.setattr(login, "record_acceptance", original)
    assert verify(live, number, code).status_code == 200


def test_parallel_verification_has_one_success(live, db):
    number, code = ask(live)
    configured = live[1].state.phone_services
    results = []
    failures = []

    def work():
        try:
            with db("app_rw") as conn:
                results.append(
                    sign_in_phone(
                        conn,
                        configured,
                        phone=number,
                        code=code,
                        ip="127.0.0.1",
                        now=datetime.now(timezone.utc),
                        accepted=ACCEPTED,
                    )
                )
        except Exception as exc:
            failures.append(exc)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not failures
    assert len(results) == 2 and sum("user_id" in result for result in results) == 1


def workspace(live):
    number, code = ask(live)
    assert verify(live, number, code).status_code == 200
    return live[0].post("/api/v1/workspaces", headers={"Origin": ORIGIN}, json={"name": "OAuth business"}).json()["id"]


@pytest.mark.parametrize("provider", ["yandex_direct", "yandex_metrika"])
def test_oauth_once_discovery_and_selection(live, provider):
    ws = workspace(live)
    client, app, _ = live
    response = client.post(f"/api/v1/workspaces/{ws}/integrations/{provider}/connect", headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    from urllib.parse import parse_qs, urlsplit

    state = parse_qs(urlsplit(response.json()["redirect_url"]).query)["state"][0]
    path = f"/api/v1/integrations/{provider}/callback"
    connected = client.get(path, params={"code": "valid-code", "state": state}, follow_redirects=False)
    assert connected.status_code == 303, connected.text
    assert len(app.state.integration_services.exchanges) == 1
    repeated = client.get(path, params={"code": "valid-code", "state": state}, follow_redirects=False)
    assert repeated.status_code == 400 and len(app.state.integration_services.exchanges) == 1
    listed = client.get(f"/api/v1/workspaces/{ws}/integrations").json()["items"]
    [item] = listed
    assert item["status"] == "connected"
    assert "provider-secret" not in str(item) and "refresh-secret" not in str(item)
    if provider == "yandex_direct":
        aid = item["accounts"][0]["id"]
        result = client.put(
            f"/api/v1/workspaces/{ws}/accounts/{aid}", headers={"Origin": ORIGIN}, json={"is_selected": True}
        )
    else:
        cid = item["counters"][0]["id"]
        path = f"/api/v1/workspaces/{ws}/metrika-counters/{cid}"
        assert (
            client.put(path, headers={"Origin": ORIGIN}, json={"is_selected": True, "goal_ids": [999]}).status_code
            == 422
        )
        result = client.put(path, headers={"Origin": ORIGIN}, json={"is_selected": True, "goal_ids": [501]})
    assert result.status_code == 200, result.text


def test_state_is_session_bound_and_wrong_provider_never_exchanges(live, rw):
    ws = workspace(live)
    client, app, _ = live
    from urllib.parse import parse_qs, urlsplit

    response = client.post(f"/api/v1/workspaces/{ws}/integrations/yandex_direct/connect", headers={"Origin": ORIGIN})
    state = parse_qs(urlsplit(response.json()["redirect_url"]).query)["state"][0]
    assert (
        client.get("/api/v1/integrations/yandex_metrika/callback", params={"code": "x", "state": state}).status_code
        == 400
    )
    foreign = session(rw, user(rw))
    assert (
        client.get(
            "/api/v1/integrations/yandex_direct/callback", params={"code": "x", "state": state}, headers=cookie(foreign)
        ).status_code
        == 400
    )
    assert app.state.integration_services.exchanges == []


def test_workspace_profile_isolation(live, rw):
    ws = workspace(live)
    foreign = session(rw, user(rw))
    path = f"/api/v1/workspaces/{ws}/business-profile"
    assert live[0].get(path, headers=cookie(foreign)).status_code == 404
    assert (
        live[0].put(path, headers={**cookie(foreign), "Origin": ORIGIN}, json={"industry": "retail"}).status_code == 404
    )


def test_reconnect_truncated_counter_catalog_preserves_prior_selection(live, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    ws = workspace(live)
    client, app, _ = live
    catalog = {"login": None, "counters": [{"id": 202, "name": "Selected counter", "goals": [{"id": 601}]}]}
    monkeypatch.setattr(app.state.integration_services, "discover", lambda provider, token: catalog)

    def connect_again():
        result = client.post(f"/api/v1/workspaces/{ws}/integrations/yandex_metrika/connect", headers={"Origin": ORIGIN})
        state = parse_qs(urlsplit(result.json()["redirect_url"]).query)["state"][0]
        response = client.get(
            "/api/v1/integrations/yandex_metrika/callback",
            params={"code": "valid", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text

    connect_again()
    counter = client.get(f"/api/v1/workspaces/{ws}/integrations").json()["items"][0]["counters"][0]
    assert (
        client.put(
            f"/api/v1/workspaces/{ws}/metrika-counters/{counter['id']}",
            headers={"Origin": ORIGIN},
            json={"is_selected": True, "goal_ids": [601]},
        ).status_code
        == 200
    )
    catalog = {
        "login": None,
        "catalog_truncated": True,
        "counters": [{"id": n, "name": "Counter", "goals": []} for n in range(101, 121)],
    }
    connect_again()
    item = client.get(f"/api/v1/workspaces/{ws}/integrations").json()["items"][0]
    selected = next(c for c in item["counters"] if c["counter_id"] == 202)
    assert selected["is_selected"] and selected["goal_ids"] == [601]
    assert item["catalog_truncated"] is True
    # When the provider supplies a complete catalog, absence can invalidate the old selection.
    catalog = {**catalog, "catalog_truncated": False}
    connect_again()
    item = client.get(f"/api/v1/workspaces/{ws}/integrations").json()["items"][0]
    selected = next(c for c in item["counters"] if c["counter_id"] == 202)
    assert not selected["is_selected"] and selected["goal_ids"] == []


def test_metrika_discovery_failure_returns_controlled_error(live, monkeypatch):
    from app.sources.metrika import MetrikaUnavailable
    from urllib.parse import parse_qs, urlsplit

    ws = workspace(live)
    client, app, _ = live
    connected = client.post(f"/api/v1/workspaces/{ws}/integrations/yandex_metrika/connect", headers={"Origin": ORIGIN})
    state = parse_qs(urlsplit(connected.json()["redirect_url"]).query)["state"][0]

    def unavailable(provider, token):
        raise MetrikaUnavailable(101, "access_denied")

    monkeypatch.setattr(app.state.integration_services, "discover", unavailable)
    response = client.get(
        "/api/v1/integrations/yandex_metrika/callback", params={"state": state, "code": "valid"}, follow_redirects=False
    )
    assert response.status_code == 502 and response.json()["error"]["code"] == "integration_unavailable"
    assert "provider-secret" not in response.text


def test_accepted_requires_actor_and_shown_finding_and_rowlock_stays_append_only(live, rw, db):
    from app.tenancy import enter_workspace

    ws = int(workspace(live).split("_")[1])
    uid = int(live[0].get("/api/v1/me").json()["user"]["id"].split("_")[1])
    chain = recommendation(rw, ws, f"acceptance-{next(numbers)}", "100.00")
    with db("app_rw") as conn:
        with conn.transaction():
            enter_workspace(conn, uid, ws)
            assert conn.execute("SELECT id FROM recommendations WHERE id=%s FOR UPDATE", (chain["rec"],)).fetchone()
            with pytest.raises(psycopg.errors.GeneratedAlways), conn.transaction():
                conn.execute("UPDATE recommendations SET id=id WHERE id=%s", (chain["rec"],))
            with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                conn.execute("UPDATE recommendations SET id=DEFAULT WHERE id=%s", (chain["rec"],))
            for actor, finding in ((None, chain["finding"]), (uid, None)):
                with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                    conn.execute(
                        "INSERT INTO recommendation_events(recommendation_id,type,actor_user_id,finding_id) "
                        "VALUES(%s,'accepted',%s,%s)",
                        (chain["rec"], actor, finding),
                    )
            conn.execute(
                "INSERT INTO recommendation_events(recommendation_id,type,actor_user_id,finding_id) "
                "VALUES(%s,'accepted',%s,%s)",
                (chain["rec"], uid, chain["finding"]),
            )
