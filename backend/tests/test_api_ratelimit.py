"""Лимит частоты (in-memory) и адрес клиента: X-Forwarded-For — только от доверенного прокси, IPv6 — по /64;
настройки: в production — только https-источники."""

import ipaddress

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.api.ratelimit import RateLimitMiddleware, bucket, client_ip, network_key
from app.api.settings import Settings, SettingsError
from test_api_support import settings

PROXY = frozenset({ipaddress.ip_network("10.0.0.0/8")})


@pytest.mark.parametrize("peer, forwarded, expected", [
    ("203.0.113.5", [], "203.0.113.5"),
    ("203.0.113.5", ["1.1.1.1"], "203.0.113.5"),               # не прокси: заголовок клиента не слушаем
    ("10.0.0.2", ["1.1.1.1"], "1.1.1.1"),
    ("10.0.0.2", ["6.6.6.6, 1.1.1.1"], "1.1.1.1"),             # левую часть цепочки пишет клиент
    ("10.0.0.2", ["6.6.6.6, 1.1.1.1, 10.0.0.9"], "1.1.1.1"),   # пропускаем свои прокси справа
    ("10.0.0.2", ["junk"], "10.0.0.2"),
    ("10.0.0.2", [], "10.0.0.2"),
    ("testclient", [], None),
])
def test_client_ip(peer, forwarded, expected):
    assert client_ip(peer, forwarded, PROXY) == expected


def test_ipv6_aggregated_by_64():
    a, b = network_key("2001:db8:1:2::1"), network_key("2001:db8:1:2:ffff::9")
    assert a == b == "2001:db8:1:2::/64"
    assert network_key("2001:db8:1:3::1") != a
    assert network_key("::ffff:1.2.3.4") == "1.2.3.4" and network_key("1.2.3.4") == "1.2.3.4"


@pytest.mark.parametrize("path, name", [
    ("/api/v1/auth/code/request", "auth"), ("/api/v1/auth/yandex/callback", "auth"),
    ("/api/v1/integrations/yandex_direct/callback", "auth"), ("/api/v1/workspaces/ws_1/today", "expensive"),
    ("/api/v1/workspaces/ws_1/recommendations/rec_1/actions", "expensive"),
    ("/api/v1/workspaces/ws_1/integrations/yandex_direct/connect", "expensive"),
    ("/api/v1/me", None), ("/api/v1/health", None)])
def test_buckets(path, name):
    assert bucket(path) == name


async def ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_limit_per_address_and_window():
    clock = [0.0]
    app = RateLimitMiddleware(ok, limits={"auth": 2, "expensive": 5}, clock=lambda: clock[0])
    one = TestClient(app, client=("2001:db8::1", 1))
    same_net = TestClient(app, client=("2001:db8::2", 1))
    other = TestClient(app, client=("198.51.100.1", 1))
    assert [one.get("/api/v1/auth/x").status_code for _ in range(2)] == [200, 200]
    r = same_net.get("/api/v1/auth/x")
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and r.headers["retry-after"] == "60"
    assert other.get("/api/v1/auth/x").status_code == 200
    assert one.get("/api/v1/me").status_code == 200  # вне лимитируемых путей
    clock[0] = 61
    assert one.get("/api/v1/auth/x").status_code == 200  # новое окно


def test_clients_behind_trusted_proxy_get_separate_buckets():
    """Все запросы приходят с адреса прокси (Caddy/Next): без доверия к X-Forwarded-For один клиент
    исчерпал бы лимит /auth/* за всех."""
    app = RateLimitMiddleware(ok, trusted=PROXY, limits={"auth": 2, "expensive": 5})
    proxy = TestClient(app, client=("10.0.0.2", 1))

    def call(ip):
        return proxy.get("/api/v1/auth/x", headers={"x-forwarded-for": ip}).status_code

    assert [call("203.0.113.1") for _ in range(3)] == [200, 200, 429]
    assert [call("203.0.113.2") for _ in range(2)] == [200, 200]  # другой клиент за тем же прокси не заблокирован


def test_429_through_app_has_request_id_and_security_headers(db):
    app = create_app(settings(db))
    with TestClient(app, base_url="https://testserver", client=("198.51.100.7", 1)) as c:
        responses = [c.get("/api/v1/auth/sessions") for _ in range(21)]
    assert [r.status_code for r in responses] == [401] * 20 + [429]
    r = responses[-1]
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"] and r.headers["retry-after"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_production_requires_https_origins():
    base = {"API_DATABASE_URL": "postgresql://x", "API_ENV": "production"}
    with pytest.raises(SettingsError):
        Settings.from_env({**base, "API_ALLOWED_ORIGINS": "http://app.example.test"})
    s = Settings.from_env({**base, "API_ALLOWED_ORIGINS": "https://app.example.test",
                           "API_TRUSTED_PROXIES": "10.0.0.0/8, 192.0.2.1"})
    assert s.production and ipaddress.ip_address("10.1.2.3") in next(iter(
        n for n in s.trusted_proxies if n.prefixlen == 8))
    assert not Settings.from_env({**base, "API_ENV": "dev", "API_ALLOWED_ORIGINS": "http://localhost:3000"}).production
    with pytest.raises(SettingsError):
        Settings.from_env({**base, "API_ALLOWED_ORIGINS": "https://a.test", "API_TRUSTED_PROXIES": "nope"})
