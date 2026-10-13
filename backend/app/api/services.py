"""Внешние зависимости маршрутов: OAuth-приложения Яндекса, HTTP-клиент, ключи токенов, отправитель SMS, капча.

create_app(**services) подставляет свои (тесты — MockTransport, фейковый SMS); остальные создаются из окружения при
первом обращении — приложение без YANDEX_API_* стартует, падает только маршрут, которому они нужны."""

from fastapi import Request

from app.auth.login import login_app
from app.auth.phone import PhoneAuthConfig, SmsSendError
from app.auth.tokens import EnvKeys
from app.auth.yandex_oauth import OAuthApp
from app.sources.http import api_client

API_SCOPES = ("direct:api", "metrika:read")


class NoSmsProvider:
    """Реального провайдера нет (HOLD): отправка «не удалась», в журнале — sms_failed. Ответ клиенту тот же."""

    def send(self, phone_e164: str, text: str) -> None:
        raise SmsSendError("no provider")


class NoCaptcha:
    def verify(self, token: str, ip: str) -> bool:
        return False


FACTORIES = {
    "login_app": login_app,
    "api_app": lambda: OAuthApp.from_env("YANDEX_API", API_SCOPES),
    "http": lambda: api_client("yandex_oauth"),
    "token_keys": EnvKeys,
    "phone_config": PhoneAuthConfig.from_env,
    "sms_sender": NoSmsProvider,
    "captcha": NoCaptcha,
}


def service(request: Request, name: str):
    services = request.app.state.services
    if name not in services:
        services[name] = FACTORIES[name]()
    return services[name]
