"""Configured production adapters; no development fallback and no plaintext logging."""

import hashlib
import hmac
import os
from urllib.parse import urlsplit
from dataclasses import dataclass, field

import httpx

from app.auth.phone import PhoneAuthConfig, SmsSendError


class ProviderNotConfigured(Exception):
    pass


@dataclass
class SmsRu:
    api_id: str = field(repr=False)

    def send(self, phone_e164: str, text: str) -> None:
        try:
            with httpx.Client(timeout=10) as http:
                response = http.post(
                    "https://sms.ru/sms/send", data={"api_id": self.api_id, "to": phone_e164, "msg": text, "json": "1"}
                )
                body = response.json()
                items = body.get("sms", {})
                if response.status_code != 200 or body.get("status") != "OK" or not items:
                    raise SmsSendError()
                if any(item.get("status") != "OK" for item in items.values()):
                    raise SmsSendError()
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            raise SmsSendError() from None


@dataclass
class SmartCaptcha:
    secret: str = field(repr=False)
    allowed_hosts: frozenset[str] = frozenset()

    def verify(self, token: str, ip: str) -> bool:
        try:
            with httpx.Client(timeout=5) as http:
                response = http.post(
                    "https://smartcaptcha.cloud.yandex.ru/validate",
                    data={"secret": self.secret, "token": token, "ip": ip},
                )
                body = response.json()
                return (
                    response.status_code == 200
                    and body.get("status") == "ok"
                    and body.get("host", "").lower() in self.allowed_hosts
                )
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return False


@dataclass
class PhoneServices:
    config: PhoneAuthConfig
    sender: object
    captcha: object
    identity_key: bytes = field(repr=False)

    def identity_hash(self, phone: str) -> bytes:
        return hmac.new(self.identity_key, phone.encode(), hashlib.sha256).digest()

    @classmethod
    def from_env(cls, allowed_origins=()):
        config = PhoneAuthConfig.from_env()
        if not config.enabled:
            raise ProviderNotConfigured()
        key = os.environ.get("PHONE_IDENTITY_HMAC_KEY", "").encode()
        sms = os.environ.get("SMS_RU_API_ID", "")
        captcha = os.environ.get("SMARTCAPTCHA_SERVER_KEY", "")
        hosts = frozenset(urlsplit(origin).netloc.lower() for origin in allowed_origins)
        if len(key) < 32 or not sms or not captcha or not hosts:
            raise ProviderNotConfigured()
        return cls(config, SmsRu(sms), SmartCaptcha(captcha, hosts), key)
