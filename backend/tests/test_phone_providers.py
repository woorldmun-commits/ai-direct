"""Real provider adapters with in-process transports: no network, SMS or secrets."""

import httpx
import pytest

from app.auth import providers
from app.auth.integrations import IntegrationServices
from app.auth.yandex_oauth import OAuthApp, OAuthError


@pytest.mark.parametrize(
    "status,body,allowed",
    [
        (200, {"status": "ok", "host": "app.example:8443"}, True),
        (200, {"status": "ok", "host": "evil.example"}, False),
        (200, {"status": "ok", "host": ""}, False),
        (200, {"status": "ok"}, False),
        (200, {"status": "failed", "host": "app.example:8443"}, False),
        (503, {"status": "ok", "host": "app.example:8443"}, False),
        (200, [], False),
    ],
)
def test_captcha_canonical_host_and_fail_closed(monkeypatch, status, body, allowed):
    client_type = httpx.Client

    def reply(request):
        assert str(request.url) == "https://smartcaptcha.cloud.yandex.ru/validate"
        return httpx.Response(status, json=body)

    monkeypatch.setattr(providers.httpx, "Client", lambda **kwargs: client_type(transport=httpx.MockTransport(reply)))
    captcha = providers.SmartCaptcha("server-secret", frozenset({"app.example:8443"}))
    assert captcha.verify("one-time-token", "127.0.0.1") is allowed


@pytest.mark.parametrize("result", [None, [], "bad", {}, {"Clients": None}])
def test_direct_discovery_rejects_malformed_container(result):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"result": result}))
    ) as http:
        services = IntegrationServices(OAuthApp("id", "secret", "https://example", ()), None, http)
        with pytest.raises(OAuthError):
            services.discover("yandex_direct", "test-token")


def test_metrika_discovery_does_not_require_direct_or_invent_login():
    def reply(request):
        assert request.url.host == "api-metrika.yandex.net"
        return httpx.Response(200, json={"counters": []})

    with httpx.Client(transport=httpx.MockTransport(reply)) as http:
        services = IntegrationServices(OAuthApp("id", "secret", "https://example", ()), None, http)
        result = services.discover("yandex_metrika", "test-token")
        assert result["login"] is None and result["counters"] == []
