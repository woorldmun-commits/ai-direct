"""Вход через Яндекс ID и общий OAuth-слой: без сети, Яндекс подменён httpx.MockTransport.
Пользователь привязан к Yandex id, не к login; токен приложения входа не хранится; в БД — только хэш сессии."""

import hashlib
import itertools
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import psycopg
import pytest

from app.auth.login import SCOPES, LoginError, sign_in
from app.auth.yandex_oauth import OAuthApp, OAuthError, ReauthorizationRequired, authorize_url, refresh
from test_schema import one

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
APP = OAuthApp("login-client", "login-secret", "https://app.test/auth/callback", SCOPES)
_uid = itertools.count(1)


class FakeYandex:
    """codes: код авторизации → профиль Яндекс ID (или ошибка токена). Записывает запросы."""

    def __init__(self, codes=None, token_status=200, info_client_id=APP.client_id):
        self.codes, self.token_status, self.info_client_id, self.requests = codes or {}, token_status, info_client_id, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/token":
            form = parse_qs(request.content.decode())
            grant = form["grant_type"][0]
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "server_error"})
            if grant == "refresh_token":
                if form["refresh_token"][0] != "good-refresh":
                    return httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"})
                return httpx.Response(200, json={"access_token": "new-access", "refresh_token": "new-refresh",
                                                 "expires_in": 3600, "token_type": "bearer"})
            code = form["code"][0]
            if code not in self.codes:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Code has expired"})
            return httpx.Response(200, json={"access_token": f"access-{code}", "refresh_token": "r",
                                             "expires_in": 31536000, "token_type": "bearer"})
        if request.url.path == "/info":
            code = request.headers["Authorization"].removeprefix("OAuth access-")
            return httpx.Response(200, json={**self.codes[code], "client_id": self.info_client_id, "psuid": "p"})
        return httpx.Response(404)


def profile(uid=None, login="ivan", email="ivan@yandex.ru"):
    return {"id": uid or f"9{next(_uid):09d}", "login": login, "default_email": email}


def http(fake):
    return httpx.Client(transport=httpx.MockTransport(fake))


OFFER = {"offer": "2026-10-01"}


def login(rw, fake, code="c1", state="s", expected="s", accepted=OFFER):
    return sign_in(rw, http(fake), APP, code=code, state=state, expected_state=expected, now=NOW, accepted=accepted)


def test_authorize_url():
    q = parse_qs(urlparse(authorize_url(APP, "st4te")).query)
    assert {k: v[0] for k, v in q.items()} == {"response_type": "code", "client_id": "login-client",
                                              "redirect_uri": "https://app.test/auth/callback",
                                              "scope": "login:info login:email", "state": "st4te"}


def test_new_user_is_created_with_identity_and_session(rw):
    p = profile()
    out = login(rw, FakeYandex({"c1": p}))
    assert out.created
    assert rw.execute("SELECT u.email, i.login FROM users u JOIN yandex_identities i ON i.user_id = u.id "
                      "WHERE i.yandex_uid = %s", (p["id"],)).fetchone() == ("ivan@yandex.ru", "ivan")
    # в БД — хэш сессии, не сам токен; срок — 30 дней
    assert one(rw, "SELECT expires_at FROM sessions WHERE token_hash = %s",
               hashlib.sha256(out.session_token.encode()).digest()) == NOW + timedelta(days=30)


def test_same_yandex_id_is_same_user_even_with_other_login(rw):
    p = profile()
    first = login(rw, FakeYandex({"c1": p}))
    again = login(rw, FakeYandex({"c2": {**p, "login": "ivan-renamed"}}), code="c2")
    assert (again.user_id, again.created) == (first.user_id, False)       # связь — по id, не по login
    assert again.session_token != first.session_token                     # каждый вход — новая сессия


def test_different_yandex_id_is_different_user(rw):
    a = login(rw, FakeYandex({"c1": profile(login="same")}))
    b = login(rw, FakeYandex({"c1": profile(login="same")}))
    assert a.user_id != b.user_id


def test_state_mismatch_stops_before_calling_yandex(rw):
    fake = FakeYandex({"c1": profile()})
    for state, expected in (("forged", "s"), ("s", "")):
        with pytest.raises(LoginError, match="state_mismatch"):
            login(rw, fake, state=state, expected=expected)
    assert fake.requests == []


def test_invalid_code_requires_reauthorization(rw):
    with pytest.raises(ReauthorizationRequired, match="invalid_grant"):
        login(rw, FakeYandex({}), code="expired")


def test_token_of_other_app_is_rejected_and_nothing_created(rw):
    p = profile()
    with pytest.raises(LoginError, match="foreign_token"):
        login(rw, FakeYandex({"c1": p}, info_client_id="someone-else"))
    assert one(rw, "SELECT count(*) FROM yandex_identities WHERE yandex_uid = %s", p["id"]) == 0


def test_deactivated_user_cannot_sign_in(rw):
    p = profile()
    user_id = login(rw, FakeYandex({"c1": p})).user_id
    rw.execute("UPDATE users SET status = 'deactivated', deactivated_at = now() WHERE id = %s", (user_id,))
    with pytest.raises(LoginError, match="user_deactivated"):
        login(rw, FakeYandex({"c1": p}))


def test_new_user_without_email_is_rejected(rw):
    with pytest.raises(LoginError, match="email_missing"):
        login(rw, FakeYandex({"c1": profile(email=None)}))


def test_yandex_unavailable_is_retryable_code(rw):
    with pytest.raises(OAuthError, match="yandex_unavailable"):
        login(rw, FakeYandex({"c1": profile()}, token_status=503))


# --- Обновление токена (общий слой; хранение токенов подключений — в следующем срезе) ------------

def test_refresh_returns_new_pair():
    t = refresh(http(FakeYandex()), APP, "good-refresh", NOW)
    assert (t.access_token, t.refresh_token, t.expires_at) == ("new-access", "new-refresh", NOW + timedelta(hours=1))


def test_invalid_refresh_requires_reauthorization():
    with pytest.raises(ReauthorizationRequired):
        refresh(http(FakeYandex()), APP, "revoked-refresh", NOW)


def test_config_from_env_and_secret_not_in_repr():
    env = {"YANDEX_LOGIN_CLIENT_ID": "id", "YANDEX_LOGIN_CLIENT_SECRET": "s3cr3t",
           "YANDEX_LOGIN_REDIRECT_URI": "https://app.test/cb"}
    app = OAuthApp.from_env("YANDEX_LOGIN", SCOPES, env)
    assert app.client_secret == "s3cr3t" and "s3cr3t" not in repr(app)
    with pytest.raises(RuntimeError, match="YANDEX_LOGIN_CLIENT_SECRET"):
        OAuthApp.from_env("YANDEX_LOGIN", SCOPES, {k: v for k, v in env.items() if "SECRET" not in k})


def test_token_response_without_access_token_is_oauth_error():
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"error_description": "?"})))
    with pytest.raises(OAuthError, match="bad_response"):
        refresh(http, APP, "good-refresh", NOW)


# --- Принятие оферты и согласий: доказательство — на операторе (ч. 3 ст. 9 152-ФЗ) ----------------

def acceptances(rw, user_id):
    return rw.execute("SELECT document, version, accepted_at FROM legal_acceptances WHERE user_id = %s ORDER BY document",
                      (user_id,)).fetchall()


def test_new_user_without_accepted_offer_is_not_created(rw):
    p = profile()
    with pytest.raises(LoginError, match="terms_not_accepted"):
        login(rw, FakeYandex({"c1": p}), accepted={})
    assert one(rw, "SELECT count(*) FROM yandex_identities WHERE yandex_uid = %s", p["id"]) == 0


def test_acceptance_is_recorded_with_version_and_time_each_document_separately(rw):
    out = login(rw, FakeYandex({"c1": profile()}), accepted={**OFFER, "marketing": "2026-10-01"})
    assert acceptances(rw, out.user_id) == [("marketing", "2026-10-01", NOW), ("offer", "2026-10-01", NOW)]


def test_existing_user_signs_in_without_new_acceptance(rw):
    p = profile()
    first = login(rw, FakeYandex({"c1": p}))
    again = login(rw, FakeYandex({"c2": p}), code="c2", accepted={})
    assert again.user_id == first.user_id and len(acceptances(rw, first.user_id)) == 1


@pytest.mark.parametrize("accepted", [{"offer": ""}, {"offer": "v1; DROP"}, {"unknown_doc": "2026-10-01", **OFFER}])
def test_unknown_document_or_bad_version_is_rejected(rw, accepted):
    with pytest.raises(LoginError, match="terms_not_accepted"):
        login(rw, FakeYandex({"c1": profile()}), accepted=accepted)


def test_acceptance_cannot_be_rewritten(rw):
    out = login(rw, FakeYandex({"c1": profile()}))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # и триггер append-only — второй барьер
        rw.execute("UPDATE legal_acceptances SET version = 'other' WHERE user_id = %s", (out.user_id,))
