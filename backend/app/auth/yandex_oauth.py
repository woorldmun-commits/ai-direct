"""Общий OAuth-слой Яндекса (oauth.yandex.ru) для двух приложений с разными client_id:
- вход — приложение Яндекс ID (права login:*), только идентификация пользователя;
- API — Директ и Метрика (direct:api, metrika:read), токены подключений.
Тип приложения в Яндексе после создания не меняется, а API-приложение не может получить права login:* — поэтому
приложений два, а код обмена и обновления токена — один. Секреты — только из переменных окружения.

Ошибки — коды без текста сервера (как last_error в БД): invalid_grant → ReauthorizationRequired (код или refresh-токен
недействителен/отозван — нужен новый вход через Яндекс), сеть и 5xx → yandex_unavailable (можно повторить)."""

import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
TOKEN_URL = "https://oauth.yandex.ru/token"
TIMEOUT = httpx.Timeout(10.0)


class OAuthError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ReauthorizationRequired(OAuthError):
    """Код авторизации или refresh-токен больше не действует: пользователь должен снова пройти OAuth."""


@dataclass(frozen=True)
class OAuthApp:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str
    scopes: tuple[str, ...]

    @classmethod
    def from_env(cls, prefix: str, scopes: tuple[str, ...], env: Mapping[str, str] = os.environ) -> "OAuthApp":
        """prefix: YANDEX_LOGIN (приложение входа) или YANDEX_API (Директ + Метрика)."""
        names = [f"{prefix}_{k}" for k in ("CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI")]
        if missing := [n for n in names if not env.get(n)]:
            raise RuntimeError(f"не заданы переменные окружения: {', '.join(missing)}")
        return cls(*(env[n] for n in names), scopes=scopes)


@dataclass(frozen=True)
class Tokens:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    expires_at: datetime


def new_state() -> str:
    """Одноразовый state против CSRF на callback: хранится у вызывающего (cookie) и сверяется при возврате."""
    return secrets.token_urlsafe(32)


def authorize_url(app: OAuthApp, state: str) -> str:
    return AUTHORIZE_URL + "?" + urlencode({"response_type": "code", "client_id": app.client_id,
                                            "redirect_uri": app.redirect_uri, "scope": " ".join(app.scopes),
                                            "state": state})


def exchange_code(http: httpx.Client, app: OAuthApp, code: str, now: datetime) -> Tokens:
    return _token(http, app, {"grant_type": "authorization_code", "code": code}, now)


def refresh(http: httpx.Client, app: OAuthApp, refresh_token: str, now: datetime) -> Tokens:
    """Яндекс выдаёт новую пару: сохранять нужно оба токена, старый refresh больше не использовать."""
    return _token(http, app, {"grant_type": "refresh_token", "refresh_token": refresh_token}, now)


def _token(http: httpx.Client, app: OAuthApp, data: dict, now: datetime) -> Tokens:
    try:
        r = http.post(TOKEN_URL, data={**data, "client_id": app.client_id, "client_secret": app.client_secret},
                      timeout=TIMEOUT)
    except httpx.TransportError:
        raise OAuthError("yandex_unavailable") from None
    if r.status_code == 200:
        try:
            body = r.json()
            access, refresh_token = body["access_token"], body.get("refresh_token")
            expires = int(body["expires_in"])
            if (not isinstance(access, str) or not access or len(access) > 16384 or expires <= 0
                    or (refresh_token is not None and (not isinstance(refresh_token, str) or not refresh_token
                                                       or len(refresh_token) > 16384))):
                raise ValueError
            return Tokens(access, refresh_token, now + timedelta(seconds=expires))
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
            raise OAuthError("bad_response") from None
    if r.status_code >= 500:
        raise OAuthError("yandex_unavailable")
    code = _error_code(r)
    if code == "invalid_grant":
        raise ReauthorizationRequired(code)
    raise OAuthError(code)  # invalid_client и т. п. — ошибка конфигурации приложения, повтор не поможет


def _error_code(r: httpx.Response) -> str:
    try:
        body = r.json()
        code = body.get("error", "") if isinstance(body, dict) else ""
    except ValueError:
        code = ""
    return code if isinstance(code, str) and re.fullmatch(r"[a-z_]+", code) else f"http_{r.status_code}"
