"""Маршруты входа по SMS (API_CONTRACT §11): за флагом sms_login (по умолчанию выключен), одинаковый 202, 429 с
Retry-After, 401 invalid_code; завершения входа нет (нет связи номер → пользователь) — 501."""

import itertools
import re

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.auth.phone import PhoneAuthConfig
from test_api_support import ORIGIN, settings
from test_phone_auth import CONFIG, FakeCaptcha, FakeSms, phone

H = {"Origin": ORIGIN}
_ips = itertools.count(1)


def client(db, sms=None, config=CONFIG):
    app = create_app(settings(db), phone_config=config, sms_sender=sms or FakeSms(), captcha=FakeCaptcha())
    return TestClient(app, base_url="https://testserver", client=(f"192.0.2.{next(_ips)}", 1),
                      raise_server_exceptions=False)


def test_routes_absent_without_flag(db, monkeypatch):
    monkeypatch.delenv("SMS_LOGIN", raising=False)
    with client(db) as c:
        assert c.post("/api/v1/auth/code/request", json={"phone": phone()}, headers=H).status_code == 404


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv("SMS_LOGIN", "1")


def test_module_switch_still_applies(db, flag_on):
    with client(db, config=PhoneAuthConfig(enabled=False, hmac_key=b"")) as c:
        assert c.post("/api/v1/auth/code/request", json={"phone": phone()}, headers=H).status_code == 404


def test_request_verify_flow(db, flag_on):
    sms = FakeSms()
    number = phone()
    with client(db, sms) as c:
        r = c.post("/api/v1/auth/code/request", json={"phone": number}, headers=H)
        assert r.status_code == 202 and r.json() == {}
        assert c.post("/api/v1/auth/code/request", json={"phone": phone()}, headers=H).json() == {}
        again = c.post("/api/v1/auth/code/request", json={"phone": number}, headers=H)
        assert again.status_code == 429 and int(again.headers["retry-after"]) > 0
        assert again.json()["error"]["code"] == "rate_limited"
        wrong = c.post("/api/v1/auth/code/verify", json={"phone": number, "code": "000000"}, headers=H)
        assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_code"
        ok = c.post("/api/v1/auth/code/verify", json={"phone": number, "code": sms_code(sms, number)}, headers=H)
        assert ok.status_code == 501 and ok.json()["error"]["reason"] == "phone_identity_missing"
        assert "set-cookie" not in ok.headers


def sms_code(sms, number):
    return re.search(r"\d{6}", next(t for p, t in sms.sent if p == number)).group()


@pytest.mark.parametrize("body", [{"phone": "+380441234567"}, {"phone": "+79123456789", "x": 1}, {}])
def test_bad_input_is_400(db, flag_on, body):
    with client(db) as c:
        assert c.post("/api/v1/auth/code/request", json=body, headers=H).status_code == 400


def test_without_origin_is_csrf(db, flag_on):
    with client(db) as c:
        assert c.post("/api/v1/auth/code/request", json={"phone": phone()}).status_code == 403
