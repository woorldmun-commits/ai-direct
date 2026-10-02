"""Граница запроса: заголовки безопасности на любом ответе (и на ошибках), X-Request-Id, лимит тела, 500 без деталей,
/health без секретов, настройки из окружения."""

import uuid

import pytest

from app.api import create_app
from app.api.settings import Settings, SettingsError
from test_api_support import ORIGIN, api, client_for, cookie, session, settings, world, ws  # noqa: F401

SECURITY = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
}


def assert_secure(r):
    for name, expected in SECURITY.items():
        assert r.headers.get(name) == expected, (name, r.status_code)
    uuid.UUID(r.headers["x-request-id"])


def test_security_headers_on_success_and_every_error(api, rw, world):
    token = session(rw, world["viewer"])
    responses = [
        api.get("/api/v1/health"),                                                          # 200
        api.get("/api/v1/me", headers=cookie(token)),                                       # 200
        api.get("/api/v1/me"),                                                              # 401
        api.get(f"/api/v1/workspaces/{ws(world, 'b1')}/recommendations", headers=cookie(token)),  # 404
        api.get(f"/api/v1/workspaces/{ws(world, 'a1')}/members", headers=cookie(token)),    # 403 forbidden_role
        api.post("/api/v1/me", headers={"Origin": "https://evil.example"}),                 # 403 csrf
        api.post("/api/v1/me", headers={"Origin": ORIGIN}),                                 # 405
        api.get("/api/v1/nowhere"),                                                         # 404 маршрута
    ]
    assert [r.status_code for r in responses] == [200, 200, 401, 404, 403, 403, 405, 404]
    for r in responses:
        assert_secure(r)
        assert "strict-transport-security" not in r.headers  # HSTS — только за флагом окружения


def test_hsts_behind_flag(db):
    with client_for(create_app(settings(db, hsts=True))) as c:
        r = c.get("/api/v1/health")
    assert r.headers["strict-transport-security"].startswith("max-age=")


def test_request_id_echoes_client_uuid_only(api):
    rid = str(uuid.uuid4())
    r = api.get("/api/v1/me", headers={"X-Request-Id": rid})
    assert r.headers["x-request-id"] == rid == r.json()["error"]["request_id"]
    r = api.get("/api/v1/me", headers={"X-Request-Id": "<script>alert(1)</script>"})
    assert r.headers["x-request-id"] != "<script>alert(1)</script>"
    uuid.UUID(r.headers["x-request-id"])


def test_error_format_is_uniform(api):
    r = api.get("/api/v1/nowhere")
    assert set(r.json()) == {"error"}
    assert set(r.json()["error"]) == {"code", "message", "request_id"}
    assert r.headers["content-type"].startswith("application/json")


def test_body_size_limit(db):
    with client_for(create_app(settings(db, max_body_bytes=100))) as c:
        r = c.post("/api/v1/me", headers={"Origin": ORIGIN}, content=b"x" * 101)
        assert r.status_code == 413
        assert r.json()["error"]["code"] == "invalid_request" and r.json()["error"]["reason"] == "payload_too_large"
        assert_secure(r)
        r = c.post("/api/v1/me", headers={"Origin": ORIGIN}, content=b"x" * 100)
        assert r.status_code == 405


def test_unhandled_error_is_500_without_details(db):
    app = create_app(settings(db))

    @app.get("/api/v1/boom")
    def boom():
        raise RuntimeError("secret detail: password=hunter2")

    with client_for(app) as c:
        r = c.get("/api/v1/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal" and "hunter2" not in r.text and "Traceback" not in r.text
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]
    assert_secure(r)


def test_health_has_no_secrets(api):
    r = api.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert "postgres" not in r.text and "app_rw" not in r.text


def test_settings_from_env():
    s = Settings.from_env({"API_DATABASE_URL": "postgresql://app_rw@db/x",
                           "API_ALLOWED_ORIGINS": "https://App.example.test, https://admin.example.test",
                           "API_HSTS": "1"})
    assert s.allowed_origins == {"https://app.example.test", "https://admin.example.test"} and s.hsts
    assert "app_rw@db" not in repr(s)  # строка подключения (с паролем) не попадает в repr и логи


@pytest.mark.parametrize("env", [
    {"API_ALLOWED_ORIGINS": "https://app.example.test"},                                    # нет БД
    {"API_DATABASE_URL": "postgresql://x"},                                                 # нет allowlist
    {"API_DATABASE_URL": "postgresql://x", "API_ALLOWED_ORIGINS": "https://a.test/path"},   # не origin
    {"API_DATABASE_URL": "postgresql://x", "API_ALLOWED_ORIGINS": "*"},
])
def test_settings_refuse_unsafe_config(env):
    with pytest.raises(SettingsError):
        Settings.from_env(env)
