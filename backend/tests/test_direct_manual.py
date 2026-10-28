"""Manual Yandex codes are bound to the signed-in workspace and a private PKCE verifier."""
import base64
import hashlib
import time
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.api import direct_connect
from app.api.settings import SettingsError
from app.auth.yandex_oauth import OAuthApp, authorize_url, exchange_code
from test_api_support import ORIGIN, session, user
from test_direct_connect import PROVIDER, begin, fake_yandex, pilot  # noqa: F401
from test_schema import one

MANUAL = replace(PROVIDER, redirect_uri="https://oauth.yandex.ru/verification_code")


@pytest.fixture
def manual(pilot):
    client, ws, owner = pilot
    client.app.state.settings = replace(client.app.state.settings, oauth_direct=MANUAL)
    return client, ws, owner


def complete(client, ws, state, code="synthetic-code", origin=ORIGIN):
    return client.post(f"/api/v1/workspaces/ws_{ws}/direct/complete",
                       json={"state": state, "code": code}, headers={"Origin": origin})


def test_pkce_code_is_bound_to_private_verifier():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    q = parse_qs(urlsplit(authorize_url(MANUAL, "state", code_verifier=verifier)).query)
    assert q["code_challenge"] == ["E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"]
    assert q["code_challenge_method"] == ["S256"]
    assert verifier not in str(q)
    requests = []
    def token(request):
        requests.append(parse_qs(request.content.decode()))
        return httpx.Response(200, json={"access_token": "synthetic", "expires_in": 3600})
    with httpx.Client(transport=httpx.MockTransport(token)) as http:
        exchange_code(http, MANUAL, "synthetic-code", datetime.now(timezone.utc), code_verifier=verifier)
    assert requests[0]["code_verifier"] == [verifier]


@pytest.mark.parametrize("uri", ["https://oauth.yandex.ru/verification_code?x=1",
                                  "https://oauth.yandex.ru.evil.test/verification_code",
                                  "http://oauth.yandex.ru/verification_code"])
def test_only_exact_yandex_manual_redirect_is_allowed(pilot, uri):
    client, _, _ = pilot
    with pytest.raises(SettingsError):
        replace(client.app.state.settings, oauth_direct=replace(PROVIDER, redirect_uri=uri))


def test_manual_start_pkce_and_complete_store_encrypted_connection(manual, rw, monkeypatch):
    client, ws, _ = manual
    response = begin(client, ws, counter_id=555, goal_ids=[111])
    assert response.status_code == 200
    body = response.json()
    assert body["completion_mode"] == "manual_code"
    q = parse_qs(urlsplit(body["authorize_url"]).query)
    assert q["redirect_uri"] == [MANUAL.redirect_uri]
    flow = direct_connect.Flow.model_validate_json(direct_connect._cipher(MANUAL).decrypt(
        client.cookies.get(direct_connect.FLOW_COOKIE).encode()))
    assert len(flow.code_verifier) >= 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.code_verifier.encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == [challenge]
    assert flow.code_verifier not in response.text
    calls = fake_yandex(monkeypatch)
    original_exchange = direct_connect.exchange_code
    def checked_exchange(http, provider, code, now, **kwargs):
        assert kwargs["code_verifier"] == flow.code_verifier
        return original_exchange(http, provider, code, now, **kwargs)
    monkeypatch.setattr(direct_connect, "exchange_code", checked_exchange)
    result = complete(client, ws, body["state"])
    assert result.status_code == 200 and result.json() == {"connected": True}
    assert calls == ["/token", "/json/v5/campaigns", "/management/v1/counter/555/goals"]
    assert one(rw, "SELECT has_token FROM direct_connections WHERE workspace_id=%s", ws)
    assert one(rw, "SELECT count(*) FROM sync_runs WHERE workspace_id=%s", ws) == 1
    assert client.cookies.get(direct_connect.FLOW_COOKIE) is None
    assert complete(client, ws, body["state"]).status_code == 400


@pytest.mark.parametrize("invalid", ["state", "actor", "expired", "workspace", "origin", "missing_verifier"])
def test_manual_rejects_mismatched_flow_before_network(manual, rw, monkeypatch, invalid):
    client, ws, owner = manual
    body = begin(client, ws).json()
    state = body["state"]
    cookie = client.cookies.get(direct_connect.FLOW_COOKIE)
    if invalid == "state":
        state = "x" * 43
    elif invalid == "actor":
        client.cookies.clear()
        client.cookies.set(direct_connect.FLOW_COOKIE, cookie)
        client.cookies.set("session", session(rw, user(rw)))
    elif invalid in ("expired", "missing_verifier"):
        raw = direct_connect._cipher(MANUAL).decrypt(cookie.encode())
        if invalid == "missing_verifier":
            flow = direct_connect.Flow.model_validate_json(raw)
            raw = flow.model_copy(update={"code_verifier": ""}).model_dump_json().encode()
        cookie = direct_connect._cipher(MANUAL).encrypt_at_time(raw, int(time.time()) - (601 if invalid == "expired" else 0))
        client.cookies.clear()
        client.cookies.set("session", session(rw, owner))
        client.cookies.set(direct_connect.FLOW_COOKIE, cookie.decode())
    elif invalid == "workspace":
        org = one(rw, "SELECT organization_id FROM workspaces WHERE id=%s", ws)
        ws = one(rw, "SELECT create_workspace(%s,%s,'Other')", owner, org)
    calls = fake_yandex(monkeypatch)
    response = complete(client, ws, state, origin="https://evil.test" if invalid == "origin" else ORIGIN)
    assert response.status_code in (400, 403, 404)
    assert calls == []


def test_manual_completion_is_not_available_for_web_callback(pilot, monkeypatch):
    client, ws, _ = pilot
    response = begin(client, ws)
    state = parse_qs(urlsplit(response.json()["authorize_url"]).query)["state"][0]
    calls = fake_yandex(monkeypatch)
    assert complete(client, ws, state).status_code == 400
    assert calls == []
